"""build_excel_workbook (doc §7.5, §8.1) — the only mature Python library
that writes native Excel chart objects from scratch is XlsxWriter, which
is what makes this a real analytical deliverable (editable charts) rather
than a screenshot.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import pandas as pd
import xlsxwriter

from app.models.schemas import ChartSpec, ChartType, SignalsPackage

EXCLUDED_EXPORT_COLUMNS = {"LOAN_AGREEMENT_NO", "UCID", "CUSTOMER_ID", "CUSTOMERNAME"}


def build_excel_workbook(
    data: pd.DataFrame,
    spec: ChartSpec,
    question: str,
    generated_sql: str,
    employee_id: str,
    snapshot_months: list[str],
    signals: SignalsPackage | None = None,
    forecast_df: pd.DataFrame | None = None,
) -> bytes:
    """Cover + Data + Dashboard (+Signals, +Forecast) sheets. Same
    chart-type decision as the inline chat chart, so they cannot disagree.
    """
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})

    bold = wb.add_format({"bold": True})
    header_fmt = wb.add_format({"bold": True, "bg_color": "#F6F8FA", "border": 1})
    pct_fmt = wb.add_format({"num_format": "0.00%"})
    inr_fmt = wb.add_format({"num_format": "#,##0.00"})

    _write_cover_sheet(wb, bold, question, generated_sql, employee_id, snapshot_months)
    export_df = data.drop(columns=[c for c in EXCLUDED_EXPORT_COLUMNS if c in data.columns])
    _write_data_sheet(wb, header_fmt, export_df)
    _write_dashboard_sheet(wb, header_fmt, export_df, spec, signals)

    if signals is not None:
        _write_signals_sheet(wb, header_fmt, signals)

    if forecast_df is not None:
        _write_forecast_sheet(wb, header_fmt, forecast_df, signals)

    wb.close()
    return buf.getvalue()


def _write_cover_sheet(wb, bold, question, generated_sql, employee_id, snapshot_months) -> None:
    ws = wb.add_worksheet("Cover")
    ws.set_column("A:A", 22)
    ws.set_column("B:B", 90)
    rows = [
        ("Question asked", question),
        ("Generated SQL", generated_sql),
        ("Snapshot months covered", ", ".join(snapshot_months)),
        ("Generated at (UTC)", datetime.utcnow().isoformat()),
        ("Employee ID", employee_id),
        ("Disclaimer", "Figures are computed deterministically by SQL/statistical "
                        "tools. No number in this workbook originates from a "
                        "language-model token. PII columns are excluded by default."),
    ]
    for i, (label, value) in enumerate(rows):
        ws.write(i, 0, label, bold)
        ws.write(i, 1, value)


def _write_data_sheet(wb, header_fmt, df: pd.DataFrame) -> None:
    ws = wb.add_worksheet("Data")
    for col_idx, col_name in enumerate(df.columns):
        ws.write(0, col_idx, col_name, header_fmt)
    for row_idx, row in enumerate(df.itertuples(index=False), start=1):
        for col_idx, value in enumerate(row):
            ws.write(row_idx, col_idx, _excel_safe(value))
    ws.autofilter(0, 0, len(df), max(len(df.columns) - 1, 0))


def _write_dashboard_sheet(wb, header_fmt, df: pd.DataFrame, spec: ChartSpec, signals) -> None:
    ws = wb.add_worksheet("Dashboard")
    ws.write(0, 0, "Analytical Dashboard", header_fmt)

    if spec.chart_type == ChartType.kpi_callout:
        _write_kpi_callout(ws, df, signals)
        return

    data_ws_name = "Data"
    chart = _native_chart_for_spec(wb, spec, df, data_ws_name)
    if chart is not None:
        ws.insert_chart("A3", chart, {"x_scale": 1.6, "y_scale": 1.4})

    if signals and signals.period_change:
        ws.write(1, 6, "Period change (%)")
        ws.write(2, 6, signals.period_change.pct_change)
    if signals and signals.zscore:
        ws.write(3, 6, "Z-score")
        ws.write(4, 6, signals.zscore.value)


def _write_kpi_callout(ws, df: pd.DataFrame, signals) -> None:
    ws.write(2, 0, "Single-value result — no chart forced on one number.")
    if not df.empty:
        first_col = df.columns[0]
        ws.write(4, 0, first_col)
        ws.write(4, 1, _excel_safe(df.iloc[0][first_col]))


def _native_chart_for_spec(wb, spec: ChartSpec, df: pd.DataFrame, data_sheet: str):
    if spec.x_field not in df.columns or (spec.y_field and spec.y_field not in df.columns):
        return None

    n_rows = len(df)
    x_col_idx = list(df.columns).index(spec.x_field)
    y_col_idx = list(df.columns).index(spec.y_field) if spec.y_field else x_col_idx + 1

    chart_type_map = {
        ChartType.line: "line",
        ChartType.bar: "column",
        ChartType.pie: "pie",
        ChartType.scatter: "scatter",
    }
    xl_type = chart_type_map.get(spec.chart_type)
    if xl_type is None:
        return None

    chart = wb.add_chart({"type": xl_type})
    chart.add_series({
        "categories": [data_sheet, 1, x_col_idx, n_rows, x_col_idx],
        "values": [data_sheet, 1, y_col_idx, n_rows, y_col_idx],
        "name": spec.y_field,
        **({"line": {"dash_type": "dash"}} if spec.forecast_forced else {}),
    })
    chart.set_title({"name": spec.y_field or "Result"})
    return chart


def _write_signals_sheet(wb, header_fmt, signals: SignalsPackage) -> None:
    ws = wb.add_worksheet("Signals")
    ws.write_row(0, 0, ["Signal", "Value"], header_fmt)
    row = 1

    def _put(label: str, value: Any) -> None:
        nonlocal row
        ws.write(row, 0, label)
        ws.write(row, 1, str(value))
        row += 1

    if signals.period_change:
        _put("Period change (%)", signals.period_change.pct_change)
        _put("Period change (absolute)", signals.period_change.absolute_change)
    if signals.yoy_change:
        _put("YoY change (%)", signals.yoy_change.pct_change)
    if signals.zscore:
        _put("Z-score", signals.zscore.value)
        _put("Z-score bucket", signals.zscore.bucket)
    if signals.concentration_index is not None:
        _put("Concentration index (HHI)", signals.concentration_index)
    for entry in signals.decomposition:
        _put(f"Decomposition: {entry.sub_segment}", f"{entry.share_of_change:.2%}")
    for flag in signals.data_quality_flags:
        _put(f"DQ flag [{flag.severity}] {flag.kind}", flag.detail)


def _write_forecast_sheet(wb, header_fmt, forecast_df: pd.DataFrame, signals) -> None:
    ws = wb.add_worksheet("Forecast")
    for col_idx, col_name in enumerate(forecast_df.columns):
        ws.write(0, col_idx, col_name, header_fmt)
    for row_idx, row in enumerate(forecast_df.itertuples(index=False), start=1):
        for col_idx, value in enumerate(row):
            ws.write(row_idx, col_idx, _excel_safe(value))

    if signals and signals.forecast:
        note_row = len(forecast_df) + 2
        ws.write(note_row, 0, f"Model used: {signals.forecast.model_used}")
        ws.write(note_row + 1, 0, f"Backtest MAPE: {signals.forecast.backtest_mape:.2f}%")


def _excel_safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.to_pydatetime()
    return value
