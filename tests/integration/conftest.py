import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def synthetic_snapshots():
    """Six synthetic monthly snapshots for the whole integration suite,
    ingested into a temp directory rather than the repo's data/curated.

    The env var is set BEFORE importing the ingestion/query modules so
    both resolve the redirected root. Earlier this fixture wrote to (and
    on teardown deleted) the real curated store, which silently wiped
    whatever dataset the developer had seeded for manual testing.
    """
    with tempfile.TemporaryDirectory(prefix="portfolio-test-curated-") as tmp:
        previous = os.environ.get("PORTFOLIO_CURATED_ROOT")
        os.environ["PORTFOLIO_CURATED_ROOT"] = tmp

        from ingestion.pipeline import run_ingestion_from_dataframe
        from ingestion.synthetic_data import generate_synthetic_mis

        months = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
        for i, month in enumerate(months):
            run_ingestion_from_dataframe(
                generate_synthetic_mis(n_loans=300, seed=i), month, overwrite=True
            )

        try:
            yield Path(tmp)
        finally:
            if previous is None:
                os.environ.pop("PORTFOLIO_CURATED_ROOT", None)
            else:
                os.environ["PORTFOLIO_CURATED_ROOT"] = previous
