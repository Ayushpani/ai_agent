import shutil
from pathlib import Path

import pytest

from ingestion.pipeline import run_ingestion_from_dataframe
from ingestion.synthetic_data import generate_synthetic_mis

CURATED_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "curated"


@pytest.fixture(scope="session", autouse=True)
def synthetic_snapshots():
    """One-time ingestion of 6 synthetic monthly snapshots for the whole
    integration suite, so trend/forecast paths have real partitions to
    query against DuckDB.
    """
    shutil.rmtree(CURATED_ROOT, ignore_errors=True)
    months = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
    for i, month in enumerate(months):
        df = generate_synthetic_mis(n_loans=300, seed=i)
        run_ingestion_from_dataframe(df, month)
    yield
    shutil.rmtree(CURATED_ROOT, ignore_errors=True)
