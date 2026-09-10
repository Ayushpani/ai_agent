"""package_signals (doc §7.5) — combines everything upstream into one
structured JSON, the ONLY thing the Analyst prompt ever sees. This
guarantees LLM reasoning happens over an audited, structured channel
rather than raw rows.
"""
from __future__ import annotations

from typing import Any

from app.models.schemas import (
    DataQualityFlag,
    DecompositionEntry,
    ForecastResult,
    Intent,
    PeriodChange,
    SignalsPackage,
    ZScoreResult,
)


def package_signals(
    question: str,
    intent: Intent,
    query_result_summary: dict[str, Any],
    period_change: PeriodChange | None = None,
    yoy_change: PeriodChange | None = None,
    zscore: ZScoreResult | None = None,
    decomposition: list[DecompositionEntry] | None = None,
    concentration_index: float | None = None,
    forecast: ForecastResult | None = None,
    data_quality_flags: list[DataQualityFlag] | None = None,
) -> SignalsPackage:
    return SignalsPackage(
        question=question,
        intent=intent,
        query_result_summary=query_result_summary,
        period_change=period_change,
        yoy_change=yoy_change,
        zscore=zscore,
        decomposition=decomposition or [],
        concentration_index=concentration_index,
        forecast=forecast,
        data_quality_flags=data_quality_flags or [],
    )
