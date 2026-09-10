"""Stages [1]-[2] of the ingestion pipeline (doc §5.1): load and schema-validate
the monthly MIS Excel extract.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_excel(path: str | Path, sheet_name: str | int = 0) -> pd.DataFrame:
    """Load the monthly extract, coercing obvious numeric/date columns.

    pandas infers dtypes on read; we additionally strip whitespace from
    column headers since MIS exports are inconsistent about trailing spaces.
    """
    df = pd.read_excel(path, sheet_name=sheet_name)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_canonical_columns() -> set[str]:
    """Flatten schema_card.yaml's declared column names into a set, for
    fail-loud validation of unexpected new columns.
    """
    with open(CONFIG_DIR / "schema_card.yaml") as f:
        card = yaml.safe_load(f)

    names: set[str] = set()
    for domain in card.get("domains", {}).values():
        for col in domain.get("columns", []):
            names.add(col["name"])
    return names


def validate_schema(
    df: pd.DataFrame,
    canonical_columns: set[str] | None = None,
    month_suffixed_prefixes: set[str] | None = None,
) -> list[str]:
    """Fail-loud on unexpected new columns (doc §5.1 stage [2]).

    Month-suffixed columns (auto-detected by the melt module's regex) are
    exempt — new months appended upstream are expected, not an error.
    Returns the list of genuinely unrecognized columns (empty = pass).
    """
    from ingestion.melt import detect_monthly_column_groups

    if canonical_columns is None:
        canonical_columns = load_canonical_columns()

    monthly_groups = detect_monthly_column_groups(list(df.columns))
    monthly_cols = {c for cols in monthly_groups.values() for c in cols}

    unexpected = [
        c for c in df.columns
        if c not in canonical_columns and c not in monthly_cols
    ]
    return unexpected
