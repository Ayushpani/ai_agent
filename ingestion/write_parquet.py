"""Stage [5] of the ingestion pipeline (doc §5.1, §5.2): write masked,
melted data to a snapshot_month partition.

Historization model: each monthly extract gets its own immutable partition
(SCD Type-2 by construction, doc §5.2). This module never overwrites or
deletes an existing partition — re-running ingestion for a month that
already exists is treated as an explicit re-export and requires the
caller to pass overwrite=True.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

_REPO_CURATED_ROOT = Path(__file__).resolve().parent.parent / "data" / "curated"


def curated_root() -> Path:
    """Honours the same PORTFOLIO_CURATED_ROOT override the query layer
    uses, so tests can ingest into a temp directory instead of clobbering
    a developer's seeded dataset. Resolved per call, never bound as a
    default argument — a default is evaluated once at import and would
    ignore any later redirection.
    """
    override = os.environ.get("PORTFOLIO_CURATED_ROOT")
    return Path(override) if override else _REPO_CURATED_ROOT


def partition_dir(snapshot_month: str, root: Path | None = None) -> Path:
    """snapshot_month like '2026-08'."""
    root = root or curated_root()
    return root / f"snapshot_month={snapshot_month}"


def write_snapshot(
    main_df: pd.DataFrame,
    long_tables: dict[str, pd.DataFrame],
    snapshot_month: str,
    root: Path | None = None,
    overwrite: bool = False,
) -> Path:
    root = root or curated_root()
    out_dir = partition_dir(snapshot_month, root)

    if out_dir.exists() and not overwrite:
        raise FileExistsError(
            f"Partition {out_dir} already exists. Snapshot partitions are "
            f"immutable by design (doc §5.2) — pass overwrite=True only for "
            f"an explicit correction re-export."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    main_df.to_parquet(out_dir / "main.parquet", index=False)
    for name, long_df in long_tables.items():
        long_df.to_parquet(out_dir / f"{name}.parquet", index=False)

    return out_dir
