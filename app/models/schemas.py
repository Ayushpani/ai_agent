"""Pydantic v2 schemas for every LLM output and inter-layer boundary.

Doc §4: 'Every LLM output validated against a schema before it flows to
the next node.' Nothing produced by a model reaches a tool, a chart, or
the employee without passing through one of these.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Intent(str, Enum):
    lookup = "lookup"
    aggregation = "aggregation"
    comparison = "comparison"
    trend = "trend"
    forecast = "forecast"
    anomaly = "anomaly"


class TimeGrain(str, Enum):
    month = "month"
    quarter = "quarter"
    year = "year"
    none = "none"


class RouterOutput(BaseModel):
    """Structured output of the Router / Classifier prompt (doc §6.4.1)."""

    intent: Intent
    requires_chart: bool
    requires_forecast: bool
    time_grain: TimeGrain
    entities: list[str] = Field(default_factory=list)
    ambiguous_aggregation_level: bool = False
    ambiguity_reason: str | None = None

    @model_validator(mode="after")
    def _ambiguity_reason_required_when_ambiguous(self) -> "RouterOutput":
        if self.ambiguous_aggregation_level and not self.ambiguity_reason:
            raise ValueError(
                "ambiguity_reason is required when ambiguous_aggregation_level is true"
            )
        return self


class SQLGeneratorError(BaseModel):
    error: str  # "insufficient_schema" | "needs_disambiguation"
    missing: str | None = None


class SQLGeneratorOutput(BaseModel):
    """Either a single validated SELECT statement, or a typed refusal.
    Exactly one of `sql` / `error` is set.
    """

    sql: str | None = None
    error: SQLGeneratorError | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "SQLGeneratorOutput":
        if bool(self.sql) == bool(self.error):
            raise ValueError("exactly one of sql or error must be set")
        return self


class PeriodChange(BaseModel):
    period_label: str  # e.g. "MoM", "QoQ", "YoY"
    absolute_change: float
    pct_change: float


class ZScoreResult(BaseModel):
    value: float
    bucket: str  # "normal" | "notable" | "extreme" — decided by code, not the LLM


class DecompositionEntry(BaseModel):
    sub_segment: str
    share_of_change: float


class ForecastResult(BaseModel):
    horizon: int
    point_forecast: list[float]
    interval_low: list[float]
    interval_high: list[float]
    model_used: str
    backtest_mape: float
    feasible: bool
    feasibility_reason: str | None = None


class DataQualityFlag(BaseModel):
    kind: str
    detail: str
    severity: str = "info"  # "info" | "warning" | "critical"


class SignalsPackage(BaseModel):
    """The single structured JSON the Analyst prompt ever sees (doc §7.5,
    package_signals). Every number the Analyst can reason over must be
    present here — it receives nothing else.
    """

    question: str
    intent: Intent
    query_result_summary: dict[str, Any] = Field(default_factory=dict)
    period_change: PeriodChange | None = None
    yoy_change: PeriodChange | None = None
    zscore: ZScoreResult | None = None
    decomposition: list[DecompositionEntry] = Field(default_factory=list)
    concentration_index: float | None = None
    forecast: ForecastResult | None = None
    data_quality_flags: list[DataQualityFlag] = Field(default_factory=list)


class AnalystFinding(BaseModel):
    text: str
    cites_figure: bool = True  # post-generation validator (§12 mitigation) sets this


class AnalystOutput(BaseModel):
    findings: list[AnalystFinding]
    follow_up_question: str | None = None


class NarratorOutput(BaseModel):
    prose: str


class ChartType(str, Enum):
    line = "line"
    bar = "bar"
    pie = "pie"
    scatter = "scatter"
    kpi_callout = "kpi_callout"


class ChartSpec(BaseModel):
    chart_type: ChartType
    x_field: str | None = None
    y_field: str | None = None
    series_field: str | None = None
    forecast_forced: bool = False


class AccessScope(BaseModel):
    employee_id: str
    role: str
    employee_region: str | None = None
    employee_branch: str | None = None


class AuditLogRecord(BaseModel):
    timestamp: datetime
    employee_id: str
    session_id: str
    question: str
    router_output: RouterOutput | None = None
    generated_sql_raw: str | None = None
    generated_sql_final: str | None = None
    tool_sequence: list[str] = Field(default_factory=list)
    model_ids_used: dict[str, str] = Field(default_factory=dict)
    latency_ms_per_stage: dict[str, float] = Field(default_factory=dict)
    narration_output: str | None = None
    error: str | None = None


class SnapshotInfo(BaseModel):
    snapshot_month: str
    row_count: int
    min_date: date | None = None
    max_date: date | None = None
