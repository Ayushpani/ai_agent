"""Wide-to-long melt for monthly-suffixed column groups — stage [4] of the
ingestion pipeline (doc §2.1.1, §5.1).

Several source metrics are stored one column per month (e.g. "Bounce Mar 26")
rather than one row per month. SQL cannot trend that shape. This module
regex-detects those column groups by name and melts them into long tables
BEFORE any query touches the data, so new months appended upstream require
no code change (doc §12: "Melt logic misses a new monthly column group").
"""
from __future__ import annotations

import re

import pandas as pd

# Matches a trailing "Mon YY" token, e.g. "Bounce Mar 26" -> group="Bounce", month="Mar 26"
_MONTH_SUFFIX_RE = re.compile(
    r"^(?P<prefix>.+?)\s+(?P<month>(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s?\d{2})$",
    re.IGNORECASE,
)


def detect_monthly_column_groups(columns: list[str]) -> dict[str, list[str]]:
    """Group column names sharing a common prefix and a trailing month token.

    Returns {prefix: [col1, col2, ...]} for every group with 2+ members —
    a single match is treated as a normal column, not a melt candidate.
    """
    groups: dict[str, list[str]] = {}
    for col in columns:
        m = _MONTH_SUFFIX_RE.match(col.strip())
        if not m:
            continue
        prefix = m.group("prefix").strip()
        groups.setdefault(prefix, []).append(col)
    return {prefix: cols for prefix, cols in groups.items() if len(cols) >= 2}


def _parse_month_token(col: str, prefix: str) -> pd.Timestamp:
    token = col[len(prefix):].strip()
    return pd.to_datetime(token, format="%b %y", errors="coerce")


def melt_monthly_groups(
    df: pd.DataFrame,
    id_column: str,
    groups: dict[str, list[str]] | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Split df into (remainder_wide_df, {group_name: long_df}).

    Each long_df has columns [loan_id, month, value] where `value` is the
    original cell content for that (loan, month) pair. The join key is
    always named `loan_id` regardless of the source id_column's actual
    name, so every long table has a predictable, stable schema — this is
    what config/schema_card.yaml's long_format domains document, and what
    the SQL Generator is grounded on; a mismatch here means it generates
    SQL against a column that doesn't exist. remainder_wide_df is the
    input with the melted columns dropped (still under its original name).
    """
    if groups is None:
        groups = detect_monthly_column_groups(list(df.columns))

    long_tables: dict[str, pd.DataFrame] = {}
    melted_cols: list[str] = []

    for prefix, cols in groups.items():
        sub = df[[id_column] + cols].copy()
        long_df = sub.melt(id_vars=[id_column], value_vars=cols, var_name="_col", value_name="value")
        long_df["month"] = long_df["_col"].apply(lambda c, p=prefix: _parse_month_token(c, p))
        long_df = long_df.drop(columns=["_col"]).dropna(subset=["month"])
        long_df = long_df.rename(columns={id_column: "loan_id"})
        long_tables[_slugify(prefix)] = long_df.reset_index(drop=True)
        melted_cols.extend(cols)

    remainder = df.drop(columns=melted_cols)
    return remainder, long_tables


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
