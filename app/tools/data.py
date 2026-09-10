"""Data-access tools (doc §7.1) — the only path from a validated SQL string
to actual rows. All deterministic Python; never an LLM call.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from app.models.schemas import AccessScope, SnapshotInfo
from app.security.access_scope import resolve_denied_columns, substitute_access_scope
from app.security.sql_validator import validate_and_prepare

DEFAULT_CURATED_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "curated"
SCHEMA_CARD_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "schema_card.yaml"

# Env-var indirection so the test suite can point at a temp directory
# instead of the developer's seeded dataset. Resolved per call, not
# bound as a default argument — a default is evaluated once at import
# and would ignore any later redirection.
CURATED_ROOT_ENV_VAR = "PORTFOLIO_CURATED_ROOT"


def curated_root() -> Path:
    override = os.environ.get(CURATED_ROOT_ENV_VAR)
    return Path(override) if override else DEFAULT_CURATED_ROOT


def get_snapshot_inventory(root: Path | None = None) -> list[SnapshotInfo]:
    """Which snapshots exist, row counts, date ranges. Feeds the
    forecast-feasibility gate (a forecast needs enough historical points).
    """
    root = root or curated_root()
    if not root.exists():
        return []

    infos: list[SnapshotInfo] = []
    for part_dir in sorted(root.glob("snapshot_month=*")):
        month = part_dir.name.split("=", 1)[1]
        main_path = part_dir / "main.parquet"
        if not main_path.exists():
            continue
        df = pd.read_parquet(main_path, columns=None)
        infos.append(SnapshotInfo(snapshot_month=month, row_count=len(df)))
    return infos


@lru_cache(maxsize=1)
def _load_schema_card_raw() -> dict:
    with open(SCHEMA_CARD_PATH) as f:
        return yaml.safe_load(f)


def get_schema_card(role: str | None = None) -> dict:
    """Column names, types, and glossary references — what grounds SQL
    generation. Never real rows. Columns pending SME sign-off and columns
    denied to the caller's role are excluded (doc §2.1.2, §9.2).
    """
    card = _load_schema_card_raw()
    pending = set(card.get("pending_sme_definition_columns", []))
    denied = set(resolve_denied_columns(role)) if role else set()

    filtered_domains = {}
    for domain_name, domain in card.get("domains", {}).items():
        if domain.get("access_restricted") and role not in domain.get("allowed_roles", []):
            continue
        cols = [
            c for c in domain["columns"]
            if c["name"] not in pending
            and c.get("status") != "pending_sme_definition"
            and c["name"] not in denied
        ]
        if cols:
            filtered_domains[domain_name] = {**domain, "columns": cols}

    return {"domains": filtered_domains}


def _register_snapshots(con: duckdb.DuckDBPyConnection, root: Path | None = None) -> None:
    """Registers a UNION-ALL view named `main` across every snapshot_month
    partition's main.parquet, with snapshot_month exposed as a column
    (doc §5.2: trend queries glob across partitions with one SQL statement).
    """
    root = root or curated_root()
    # .as_posix(), not str(): on Windows str() yields backslashes, and the
    # glob/read_parquet path is safer with forward slashes (DuckDB accepts
    # them on every platform).
    pattern = (root / "snapshot_month=*" / "main.parquet").as_posix()
    con.execute(f"""
        CREATE OR REPLACE VIEW main AS
        SELECT *, regexp_extract(filename, 'snapshot_month=([0-9]{{4}}-[0-9]{{2}})', 1) AS snapshot_month
        FROM read_parquet('{pattern}', filename=true, hive_partitioning=false)
    """)

    for aux_name, glob_name in [
        ("bounce_history", "bounce"),
        ("irac_history", "irac_lan_level"),
    ]:
        aux_pattern = (root / "snapshot_month=*" / f"{glob_name}.parquet").as_posix()
        if list(root.glob(f"snapshot_month=*/{glob_name}.parquet")):
            con.execute(f"""
                CREATE OR REPLACE VIEW {aux_name} AS
                SELECT *, regexp_extract(filename, 'snapshot_month=([0-9]{{4}}-[0-9]{{2}})', 1) AS snapshot_month
                FROM read_parquet('{aux_pattern}', filename=true, hive_partitioning=false)
            """)


def run_sql(
    query: str,
    access_scope: AccessScope,
    root: Path | None = None,
) -> pd.DataFrame:
    """Executes validated SELECT via DuckDB. Injects the role-based access
    filter regardless of what the LLM produced (doc §9.2) — validation and
    substitution happen here, not upstream, so this function is the single
    enforcement point no caller can bypass.
    """
    validated = validate_and_prepare(query)
    final_sql = substitute_access_scope(validated.sql, access_scope)

    con = duckdb.connect(":memory:")
    try:
        _register_snapshots(con, root)
        return _execute_with_timeout(con, final_sql, validated.timeout_seconds)
    finally:
        con.close()


def _execute_with_timeout(
    con: duckdb.DuckDBPyConnection, sql: str, timeout_seconds: int
) -> pd.DataFrame:
    """DuckDB's Python API has no native per-query timeout, so the timeout
    is enforced with a watchdog thread that interrupts the connection
    (doc §9.5: 30s default query timeout).
    """
    import threading

    timed_out = threading.Event()

    def _watchdog() -> None:
        if not timed_out.wait(timeout_seconds):
            con.interrupt()
            timed_out.set()

    watchdog = threading.Thread(target=_watchdog, daemon=True)
    watchdog.start()
    try:
        result = con.execute(sql).fetchdf()
    except duckdb.InterruptException as e:
        raise TimeoutError(f"Query exceeded {timeout_seconds}s timeout") from e
    finally:
        timed_out.set()
    return result
