"""Data-quality tools (doc §7.4). Called unconditionally on every request —
not on the LLM's discretion, precisely because the LLM cannot decide to
check something it never sees.
"""
from __future__ import annotations

import pandas as pd

from app.models.schemas import DataQualityFlag


def data_quality_scan(df: pd.DataFrame, id_column: str | None = None) -> list[DataQualityFlag]:
    """Flags nulls, duplicate customer IDs, and structural breaks (e.g. a
    category's label set changed between snapshots — looks like churn, is
    actually a taxonomy rename upstream).
    """
    flags: list[DataQualityFlag] = []

    if df.empty:
        flags.append(DataQualityFlag(kind="empty_result", detail="Query returned zero rows.", severity="warning"))
        return flags

    null_counts = df.isna().sum()
    for col, count in null_counts[null_counts > 0].items():
        pct = count / len(df) * 100
        severity = "critical" if pct > 50 else ("warning" if pct > 10 else "info")
        flags.append(DataQualityFlag(
            kind="null_values",
            detail=f"Column '{col}' has {count} nulls ({pct:.1f}% of rows).",
            severity=severity,
        ))

    if id_column and id_column in df.columns:
        dup_count = df[id_column].duplicated().sum()
        if dup_count > 0:
            flags.append(DataQualityFlag(
                kind="duplicate_id",
                detail=f"{dup_count} duplicate values found in identifier column '{id_column}'.",
                severity="critical",
            ))

    return flags


def sanity_check_trend(series: pd.Series) -> list[DataQualityFlag]:
    """Flags when a single point is responsible for a disproportionate
    share of an apparent trend (e.g. one data-entry correction
    masquerading as 'a spike').
    """
    flags: list[DataQualityFlag] = []
    if len(series) < 3:
        return flags

    diffs = series.diff().dropna()
    total_abs_change = diffs.abs().sum()
    if total_abs_change == 0:
        return flags

    max_idx = diffs.abs().idxmax()
    max_share = diffs.abs().loc[max_idx] / total_abs_change

    if max_share > 0.6:
        flags.append(DataQualityFlag(
            kind="single_point_dominance",
            detail=(
                f"A single period-over-period change accounts for "
                f"{max_share * 100:.0f}% of the total movement across the "
                f"series — verify this is not a data-entry correction "
                f"before treating it as a genuine trend."
            ),
            severity="warning",
        ))

    return flags
