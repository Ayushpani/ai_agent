"""Runs the five deterministic ingestion stages end to end (doc §5.1).

    Excel -> load_excel -> validate_schema -> mask_pii -> melt_monthly_groups -> write_snapshot
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ingestion.load_excel import load_excel, validate_schema
from ingestion.mask import mask_pii
from ingestion.melt import melt_monthly_groups
from ingestion.write_parquet import write_snapshot

logger = logging.getLogger(__name__)


def run_ingestion(
    excel_path: str | Path,
    snapshot_month: str,
    id_column: str = "LOAN_AGREEMENT_NO",
    overwrite: bool = False,
) -> Path:
    df = load_excel(excel_path)

    unexpected = validate_schema(df)
    if unexpected:
        raise ValueError(
            f"Unrecognized columns not in schema_card.yaml and not "
            f"month-suffixed: {unexpected}. Update the schema card or "
            f"confirm these are genuinely new fields before proceeding."
        )

    df = mask_pii(df)
    remainder, long_tables = melt_monthly_groups(df, id_column=id_column)

    for name, table in long_tables.items():
        logger.info("melted group '%s' -> %d rows", name, len(table))

    return write_snapshot(remainder, long_tables, snapshot_month, overwrite=overwrite)


def run_ingestion_from_dataframe(
    df: pd.DataFrame,
    snapshot_month: str,
    id_column: str = "LOAN_AGREEMENT_NO",
    overwrite: bool = False,
) -> Path:
    """Same pipeline, skipping the Excel read — used by the synthetic-data
    demo path and by tests.
    """
    df = mask_pii(df)
    remainder, long_tables = melt_monthly_groups(df, id_column=id_column)
    return write_snapshot(remainder, long_tables, snapshot_month, overwrite=overwrite)
