r"""Regression guards for how snapshot_month is recovered from the
partition path.

The original implementation extracted it with `snapshot_month=([^/]+)`
against read_parquet's `filename` column. On Linux that is correct; on
Windows the filename is `...\snapshot_month=2026-08\main.parquet`, the
backslash is not the excluded `/`, and every row's snapshot_month came
back as `2026-08\main.parquet` — which then blew up as
`invalid date field format: "2026-08\main.parquet-01"` the moment
anything tried to treat it as a month. Nothing on Linux could see it,
so these tests assert the platform-independent properties directly.
"""
import re
from pathlib import PureWindowsPath

import duckdb
import pytest

from app.tools.data import _register_snapshots, curated_root

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@pytest.fixture
def con(synthetic_snapshots):
    connection = duckdb.connect(":memory:")
    _register_snapshots(connection)
    try:
        yield connection
    finally:
        connection.close()


def test_snapshot_month_is_a_bare_year_month(con):
    months = [row[0] for row in con.execute(
        "SELECT DISTINCT snapshot_month FROM main ORDER BY 1"
    ).fetchall()]

    assert months, "no snapshots registered"
    for month in months:
        assert MONTH_RE.match(month), f"snapshot_month leaked path text: {month!r}"


def test_registered_months_match_the_partition_directories(con):
    on_disk = sorted(
        d.name.split("=", 1)[1] for d in curated_root().glob("snapshot_month=*")
    )
    in_view = [row[0] for row in con.execute(
        "SELECT DISTINCT snapshot_month FROM main ORDER BY 1"
    ).fetchall()]
    assert in_view == on_disk


def test_aux_views_also_carry_a_bare_year_month(con):
    for view in ("irac_history", "bounce_history"):
        months = [row[0] for row in con.execute(
            f"SELECT DISTINCT snapshot_month FROM {view} ORDER BY 1"
        ).fetchall()]
        assert months, f"{view} registered but empty"
        for month in months:
            assert MONTH_RE.match(month), f"{view}.snapshot_month leaked: {month!r}"


def test_extraction_pattern_survives_a_windows_shaped_path(con):
    """The guard that would have caught the original bug from Linux: run
    the same regex the view uses against a filename with backslashes."""
    windows_filename = r"C:\data\curated\snapshot_month=2026-08\main.parquet"
    extracted = con.execute(
        "SELECT regexp_extract(?, 'snapshot_month=([0-9]{4}-[0-9]{2})', 1)",
        [windows_filename],
    ).fetchone()[0]
    assert extracted == "2026-08"


def test_read_parquet_glob_is_built_with_forward_slashes():
    """DuckDB takes forward slashes on every platform; a str()'d Windows
    Path would embed backslashes into the SQL string literal, where they
    also read as escapes."""
    root = PureWindowsPath(r"C:\data\curated")
    pattern = (root / "snapshot_month=*" / "main.parquet").as_posix()
    assert "\\" not in pattern
    assert pattern.endswith("snapshot_month=*/main.parquet")
