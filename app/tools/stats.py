"""Statistical tools (doc §7.2). All deterministic; the Analyst model
interprets their outputs but never computes them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from app.models.schemas import DecompositionEntry, PeriodChange, ZScoreResult


def period_change(series: pd.Series, period: int = 1, label: str = "period") -> PeriodChange:
    """Absolute and % change between the latest value and the value
    `period` steps back in a chronologically-sorted series.
    """
    if len(series) < period + 1:
        raise ValueError(f"series has {len(series)} points, need at least {period + 1}")

    latest = float(series.iloc[-1])
    prior = float(series.iloc[-1 - period])
    absolute = latest - prior
    pct = (absolute / prior * 100) if prior != 0 else float("inf")
    return PeriodChange(period_label=label, absolute_change=absolute, pct_change=pct)


def zscore_latest(series: pd.Series) -> ZScoreResult:
    """z-score of the latest value vs. trailing history (all points before
    it). Bucketed by fixed threshold — the bucket is decided by code, not
    the LLM (doc §7.2): |z|<1 normal, 1-2 notable, >2 extreme.
    """
    if len(series) < 2:
        return ZScoreResult(value=0.0, bucket="normal")

    history = series.iloc[:-1]
    latest = float(series.iloc[-1])
    mean = float(history.mean())
    std = float(history.std())

    if std == 0 or np.isnan(std):
        # A perfectly constant history makes any deviation infinitely many
        # standard deviations away, not zero — treat no-deviation as
        # normal but any deviation from a flat history as extreme.
        if latest == mean:
            return ZScoreResult(value=0.0, bucket="normal")
        return ZScoreResult(value=float("inf") if latest > mean else float("-inf"), bucket="extreme")

    z = (latest - mean) / std
    abs_z = abs(z)
    bucket = "extreme" if abs_z > 2 else ("notable" if abs_z > 1 else "normal")
    return ZScoreResult(value=round(z, 3), bucket=bucket)


def decompose(
    base_df: pd.DataFrame, dimension: str, value_col: str, prior_col: str = "prior_value"
) -> list[DecompositionEntry]:
    """Re-queries one level finer; returns each sub-segment's share of the
    total change. Distinguishes 'the region moved' from 'one branch moved
    and dragged the region.'

    Expects base_df to already contain both current (`value_col`) and
    prior-period (`prior_col`) values per `dimension` value.
    """
    df = base_df.copy()
    df["_change"] = df[value_col] - df[prior_col]
    total_change = df["_change"].sum()

    if total_change == 0:
        return [
            DecompositionEntry(sub_segment=str(row[dimension]), share_of_change=0.0)
            for _, row in df.iterrows()
        ]

    entries = [
        DecompositionEntry(
            sub_segment=str(row[dimension]),
            share_of_change=round(float(row["_change"] / total_change), 4),
        )
        for _, row in df.iterrows()
    ]
    return sorted(entries, key=lambda e: abs(e.share_of_change), reverse=True)


def correlation(a: pd.Series, b: pd.Series, method: str = "pearson") -> dict:
    """Pearson/Spearman coefficient + p-value + significant boolean.
    Prevents narration from stating unsupported correlations.
    """
    if method == "pearson":
        coef, p_value = scipy_stats.pearsonr(a, b)
    elif method == "spearman":
        coef, p_value = scipy_stats.spearmanr(a, b)
    else:
        raise ValueError(f"unsupported correlation method: {method}")

    return {
        "coefficient": round(float(coef), 4),
        "p_value": round(float(p_value), 6),
        "significant": bool(p_value < 0.05),
        "method": method,
    }


def distribution_summary(series: pd.Series) -> dict:
    """Mean, median, std, p10/p25/p75/p90, skew."""
    return {
        "mean": float(series.mean()),
        "median": float(series.median()),
        "std": float(series.std()),
        "p10": float(series.quantile(0.10)),
        "p25": float(series.quantile(0.25)),
        "p75": float(series.quantile(0.75)),
        "p90": float(series.quantile(0.90)),
        "skew": float(series.skew()),
    }


def rank_top_n(
    df: pd.DataFrame, group_by: str, metric: str, n: int = 5, ascending: bool = False
) -> pd.DataFrame:
    """Top N by metric with defined tie handling (dense rank, ties share
    a rank and both appear if within n).
    """
    agg = df.groupby(group_by, as_index=False)[metric].sum()
    agg["rank"] = agg[metric].rank(method="dense", ascending=ascending).astype(int)
    agg = agg.sort_values("rank")
    return agg[agg["rank"] <= n].reset_index(drop=True)


def outlier_flags(series: pd.Series, method: str = "iqr") -> pd.Series:
    """Row-level anomaly detection (boolean mask) — distinct from
    time-series anomaly detection (zscore_latest is for that).
    """
    if method != "iqr":
        raise ValueError(f"unsupported outlier method: {method}")

    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return (series < lower) | (series > upper)


def concentration_index(series: pd.Series, method: str = "hhi") -> float:
    """Herfindahl-Hirschman Index or Gini coefficient. A real
    portfolio-concentration risk metric, not generic statistics.
    """
    values = series.astype(float).clip(lower=0)
    total = values.sum()
    if total == 0:
        return 0.0

    if method == "hhi":
        shares = values / total
        return float((shares ** 2).sum())

    if method == "gini":
        sorted_vals = np.sort(values.to_numpy())
        n = len(sorted_vals)
        total_sorted = sorted_vals.sum()
        if total_sorted == 0:
            return 0.0
        index = np.arange(1, n + 1)
        return float((2 * np.sum(index * sorted_vals) - (n + 1) * total_sorted) / (n * total_sorted))

    raise ValueError(f"unsupported concentration method: {method}")
