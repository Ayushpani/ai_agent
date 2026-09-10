"""Guards against schema_card.yaml drifting from what ingestion/DuckDB
actually produce. Bitten twice in practice: the card once declared
irac_history.loan_id/level/stage/dpd/npa_reason/npa_date and
bounce_history.bounce_reason/bounce_grouping/tech_non_tech, none of
which ingestion ever wrote — and separately never declared
main.snapshot_month, which does physically exist. Either direction
produces a SQL Generator output DuckDB rejects, since the schema card
is the SQL Generator's only view into what's queryable (doc §7.1).
"""
import duckdb
import pytest

from app.tools.data import _register_snapshots, get_schema_card, CURATED_ROOT


@pytest.fixture(scope="module")
def physical_columns():
    con = duckdb.connect(":memory:")
    _register_snapshots(con, CURATED_ROOT)
    tables = [row[0] for row in con.execute("SHOW TABLES").fetchall()]
    columns = {
        table: {row[1] for row in con.execute(f"PRAGMA table_info('{table}')").fetchall()}
        for table in tables
    }
    con.close()
    return columns


def test_every_documented_column_physically_exists(physical_columns):
    card = get_schema_card(role="admin")
    missing: list[str] = []

    for domain_name, domain in card["domains"].items():
        table = domain["table"]
        if table not in physical_columns:
            missing.append(f"{domain_name}: table '{table}' does not exist at all")
            continue
        for col in domain["columns"]:
            if col["name"] not in physical_columns[table]:
                missing.append(f"{domain_name}: {table}.{col['name']}")

    assert not missing, (
        "schema_card.yaml documents columns that don't physically exist "
        f"— the SQL Generator will write queries against them: {missing}"
    )


def test_snapshot_month_is_documented_on_main(physical_columns):
    """The specific regression: main.snapshot_month exists physically
    (derived from the storage partition at query time) but was never in
    the schema card, so trend queries against `main` had no time column
    to group by and the SQL Generator correctly refused rather than guess."""
    assert "snapshot_month" in physical_columns["main"]

    card = get_schema_card(role="admin")
    main_columns = {
        col["name"]
        for domain in card["domains"].values()
        if domain["table"] == "main"
        for col in domain["columns"]
    }
    assert "snapshot_month" in main_columns
