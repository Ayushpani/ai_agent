"""Chart-type decision (doc §7.5, §8.2) — a deterministic decision tree,
never an LLM call. The same decision drives both the inline Plotly chart
and the Excel dashboard sheet, so they cannot disagree.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go

from app.models.schemas import ChartSpec, ChartType

MAX_PIE_CATEGORIES = 7
MAX_BAR_CATEGORIES = 15


@dataclass
class QueryShape:
    has_time_dimension: bool
    category_column: str | None
    category_cardinality: int
    metric_columns: list[str]
    is_composition: bool  # values sum to a meaningful whole
    has_forecast: bool
    is_single_scalar: bool
    time_column: str | None = None


def choose_chart_type(shape: QueryShape) -> ChartSpec:
    """Time + continuous -> line. Low-cardinality category (<15) + metric
    -> bar. Composition <7 categories -> pie (a 20-slice pie is unreadable,
    so above 7 falls back to bar). Two continuous, no time/category ->
    scatter. Forecast present -> line forced, actuals solid, forecast
    dashed. Single number -> KPI callout, no chart (forcing a chart onto
    one number is dishonest).
    """
    if shape.is_single_scalar:
        return ChartSpec(chart_type=ChartType.kpi_callout)

    if shape.has_forecast:
        return ChartSpec(
            chart_type=ChartType.line,
            x_field=shape.time_column,
            y_field=shape.metric_columns[0] if shape.metric_columns else None,
            forecast_forced=True,
        )

    if shape.has_time_dimension:
        return ChartSpec(
            chart_type=ChartType.line,
            x_field=shape.time_column,
            y_field=shape.metric_columns[0] if shape.metric_columns else None,
        )

    if shape.is_composition and shape.category_cardinality < MAX_PIE_CATEGORIES:
        return ChartSpec(
            chart_type=ChartType.pie,
            series_field=shape.category_column,
            y_field=shape.metric_columns[0] if shape.metric_columns else None,
        )

    if shape.category_column and shape.category_cardinality < MAX_BAR_CATEGORIES:
        return ChartSpec(
            chart_type=ChartType.bar,
            x_field=shape.category_column,
            y_field=shape.metric_columns[0] if shape.metric_columns else None,
        )

    # Composition with too many categories, or any other categorical case,
    # substitutes a bar chart rather than an unreadable pie/scatter.
    if shape.category_column:
        return ChartSpec(
            chart_type=ChartType.bar,
            x_field=shape.category_column,
            y_field=shape.metric_columns[0] if shape.metric_columns else None,
        )

    if len(shape.metric_columns) >= 2:
        return ChartSpec(
            chart_type=ChartType.scatter,
            x_field=shape.metric_columns[0],
            y_field=shape.metric_columns[1],
        )

    return ChartSpec(chart_type=ChartType.kpi_callout)


def render_inline_chart(data: pd.DataFrame, spec: ChartSpec) -> go.Figure:
    """Plotly figure for the Chainlit chat surface."""
    if spec.chart_type == ChartType.line:
        fig = go.Figure()
        if spec.forecast_forced and "is_forecast" in data.columns:
            actual = data[~data["is_forecast"]]
            forecast_part = data[data["is_forecast"]]
            fig.add_trace(go.Scatter(
                x=actual[spec.x_field], y=actual[spec.y_field],
                mode="lines+markers", name="Actual", line=dict(dash="solid"),
            ))
            fig.add_trace(go.Scatter(
                x=forecast_part[spec.x_field], y=forecast_part[spec.y_field],
                mode="lines+markers", name="Forecast", line=dict(dash="dash"),
            ))
            if "interval_low" in data.columns and "interval_high" in data.columns:
                fig.add_trace(go.Scatter(
                    x=pd.concat([forecast_part[spec.x_field], forecast_part[spec.x_field][::-1]]),
                    y=pd.concat([forecast_part["interval_high"], forecast_part["interval_low"][::-1]]),
                    fill="toself", fillcolor="rgba(31,111,235,0.15)",
                    line=dict(color="rgba(255,255,255,0)"), name="80% interval", showlegend=True,
                ))
        else:
            fig.add_trace(go.Scatter(x=data[spec.x_field], y=data[spec.y_field], mode="lines+markers"))
        return fig

    if spec.chart_type == ChartType.bar:
        return go.Figure(go.Bar(x=data[spec.x_field], y=data[spec.y_field]))

    if spec.chart_type == ChartType.pie:
        return go.Figure(go.Pie(labels=data[spec.series_field], values=data[spec.y_field]))

    if spec.chart_type == ChartType.scatter:
        return go.Figure(go.Scatter(x=data[spec.x_field], y=data[spec.y_field], mode="markers"))

    raise ValueError(f"render_inline_chart called with non-chart spec: {spec.chart_type}")
