"""Seed the local curated store with synthetic monthly snapshots.

Doc §9.3: demo and develop against synthetic data until the client's
DPDP/InfoSec sign-off and the providers' data-retention confirmations
are in hand.

    python scripts/seed_synthetic_data.py               # 6 months, 2000 loans each
    python scripts/seed_synthetic_data.py --months 12 --loans 5000
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.pipeline import run_ingestion_from_dataframe  # noqa: E402
from ingestion.synthetic_data import generate_synthetic_mis  # noqa: E402
from ingestion.write_parquet import curated_root  # noqa: E402


def month_sequence(count: int, end_year: int = 2026, end_month: int = 8) -> list[str]:
    months = []
    year, month = end_year, end_month
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--loans", type=int, default=2000)
    parser.add_argument("--keep", action="store_true", help="Keep any existing partitions.")
    args = parser.parse_args()

    root = curated_root()
    if not args.keep and root.exists():
        shutil.rmtree(root)
        print(f"cleared {root}")

    for i, month in enumerate(month_sequence(args.months)):
        run_ingestion_from_dataframe(
            generate_synthetic_mis(n_loans=args.loans, seed=i), month, overwrite=True
        )
        print(f"  wrote snapshot_month={month}  ({args.loans} loans)")

    print(f"\nSeeded {args.months} monthly snapshots into {root}")


if __name__ == "__main__":
    main()
