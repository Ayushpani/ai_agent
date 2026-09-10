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

# A restrained, professional palette — one accent color, used consistently
# for headers, chart series, and KPI cards, rather than default Excel gray.
_ACCENT = "#1F4E79"
_ACCENT_LIGHT = "#DCE6F1"
_TEXT_MUTED = "#595959"


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
    """Cover + Dashboard + Data (+Signals, +Forecast) sheets. Same
    chart-type decision as the inline chat chart, so they cannot disagree.
    The Dashboard is the sheet that opens active — it's the deliverable;
    Cover is provenance, not the headline.
    """
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    fmt = _build_formats(wb)

    _write_cover_sheet(wb, fmt, question, generated_sql, employee_id, snapshot_months)
    export_df = data.drop(columns=[c for c in EXCLUDED_EXPORT_COLUMNS if c in data.columns])
    dashboard_ws = _write_dashboard_sheet(wb, fmt, export_df, spec, signals, question)
    _write_data_sheet(wb, fmt, export_df)

    if signals is not None:
        _write_signals_sheet(wb, fmt, signals)

    if forecast_df is not None:
        _write_forecast_sheet(wb, fmt, forecast_df, signals)

    dashboard_ws.activate()
    wb.close()
    return buf.getvalue()


def _build_formats(wb) -> dict:
    return {
        "title": wb.add_format({"bold": True, "font_size": 18, "font_color": _ACCENT}),
        "subtitle": wb.add_format({"italic": True, "font_size": 10, "font_color": _TEXT_MUTED}),
        "label_bold": wb.add_format({"bold": True, "valign": "top"}),
        "wrap": wb.add_format({"text_wrap": True, "valign": "top"}),
        "mono_wrap": wb.add_format({"font_name": "Consolas", "font_size": 9, "text_wrap": True, "valign": "top"}),
        "header": wb.add_format({
            "bold": True, "bg_color": _ACCENT, "font_color": "white",
            "border": 1, "align": "center", "valign": "vcenter",
        }),
        "kpi_label": wb.add_format({
            "font_size": 10, "font_color": "white", "bg_color": _ACCENT,
            "align": "center", "valign": "vcenter", "bold": True,
        }),
        "kpi_value": wb.add_format({
            "font_size": 20, "bold": True, "font_color": _ACCENT,
            "bg_color": _ACCENT_LIGHT, "align": "center", "valign": "vcenter",
            "border": 1, "border_color": _ACCENT,
        }),
        "number": wb.add_format({"num_format": "#,##0.00"}),
        "pct": wb.add_format({"num_format": "+0.0%;-0.0%"}),
        "date": wb.add_format({"num_format": "yyyy-mm-dd"}),
        "section_header": wb.add_format({
            "bold": True, "font_size": 12, "font_color": "white",
            "bg_color": _ACCENT, "indent": 1,
        }),
    }


def _write_cover_sheet(wb, fmt, question, generated_sql, employee_id, snapshot_months) -> None:
    ws = wb.add_worksheet("Cover")
    ws.hide_gridlines(2)
    ws.set_column("A:A", 22)
    ws.set_column("B:B", 100)

    ws.merge_range("A1:B1", "Portfolio Intelligence Agent — Analysis Provenance", fmt["title"])
    ws.merge_range("A2:B2", "Every figure in this workbook traces to the SQL statement below — none originates from a language-model token.", fmt["subtitle"])

    rows = [
        ("Question asked", question),
        ("Snapshot months covered", ", ".join(snapshot_months) or "(see Data sheet)"),
        ("Generated at (UTC)", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
        ("Employee ID", employee_id),
    ]
    r = 4
    for label, value in rows:
        ws.write(r, 0, label, fmt["label_bold"])
        ws.write(r, 1, value, fmt["wrap"])
        r += 1

    ws.write(r, 0, "Generated SQL", fmt["label_bold"])
    ws.set_row(r, 90)
    ws.write(r, 1, generated_sql, fmt["mono_wrap"])
    r += 2

    ws.write(r, 0, "Disclaimer", fmt["label_bold"])
    ws.write(r, 1, (
        "Figures are computed deterministically by SQL and statistical tools. "
        "PII columns (customer name/ID, UCID, loan agreement number) are "
        "excluded from this export by default."
    ), fmt["wrap"])


def _write_data_sheet(wb, fmt, df: pd.DataFrame) -> None:
    ws = wb.add_worksheet("Data")
    ws.freeze_panes(1, 0)
    for col_idx, col_name in enumerate(df.columns):
        ws.write(0, col_idx, col_name, fmt["header"])
        width = max(12, min(28, int(df[col_name].astype(str).str.len().max() or 12) + 2))
        ws.set_column(col_idx, col_idx, width)
    for row_idx, row in enumerate(df.itertuples(index=False), start=1):
        for col_idx, value in enumerate(row):
            ws.write(row_idx, col_idx, _excel_safe(value), _format_for_value(fmt, value))
    ws.autofilter(0, 0, len(df), max(len(df.columns) - 1, 0))


def _write_dashboard_sheet(wb, fmt, df: pd.DataFrame, spec: ChartSpec, signals, question: str):
    ws = wb.add_worksheet("Dashboard")
    ws.hide_gridlines(2)
    ws.set_column("A:A", 3)
    ws.set_column("B:R", 12)

    ws.merge_range("B2:R2", question, fmt["title"])
    row_after_title = 4

    kpi_col = _write_kpi_strip(ws, fmt, signals, start_row=row_after_title, start_col=1)

    chart_row = kpi_col["next_row"] + 1
    ws.merge_range(chart_row, 1, chart_row, 9, "Trend", fmt["section_header"])

    if spec.chart_type == ChartType.kpi_callout:
        _write_kpi_callout_body(ws, fmt, df, chart_row + 2)
    else:
        chart = _native_chart_for_spec(wb, spec, df, "Data")
        if chart is not None:
            chart.set_size({"width": 720, "height": 380})
            ws.insert_chart(chart_row + 2, 1, chart)

    if signals and signals.decomposition:
        decomp_col = 11
        ws.merge_range(chart_row, decomp_col, chart_row, decomp_col + 4, "Top contributors to change", fmt["section_header"])
        _write_decomposition_table(ws, fmt, signals.decomposition, chart_row + 2, decomp_col)

    return ws


def _write_kpi_strip(ws, fmt, signals: SignalsPackage | None, start_row: int, start_col: int) -> dict:
    """A row of KPI cards — the at-a-glance summary a real BI dashboard
    leads with, instead of burying the headline numbers in a side column."""
    cards: list[tuple[str, str]] = []

    if signals and signals.period_change:
        cards.append(("Period change", f"{signals.period_change.pct_change:+.1f}%"))
    if signals and signals.yoy_change:
        cards.append(("YoY change", f"{signals.yoy_change.pct_change:+.1f}%"))
    if signals and signals.zscore:
        cards.append((f"Z-score ({signals.zscore.bucket})", f"{signals.zscore.value:.2f}"))
    if signals and signals.concentration_index is not None:
        cards.append(("Concentration (HHI)", f"{signals.concentration_index:.3f}"))
    if signals and signals.forecast and signals.forecast.feasible:
        cards.append(("Forecast MAPE", f"{signals.forecast.backtest_mape:.1f}%"))
    if signals and signals.data_quality_flags:
        cards.append(("Data-quality flags", str(len(signals.data_quality_flags))))

    if not cards:
        cards = [("Status", "No signals computed")]

    card_width = 3
    for i, (label, value) in enumerate(cards):
        c0 = start_col + i * (card_width + 1)
        c1 = c0 + card_width - 1
        ws.merge_range(start_row, c0, start_row, c1, label, fmt["kpi_label"])
        ws.merge_range(start_row + 1, c0, start_row + 2, c1, value, fmt["kpi_value"])

    return {"next_row": start_row + 3}


def _write_kpi_callout_body(ws, fmt, df: pd.DataFrame, row: int) -> None:
    ws.write(row, 1, "Single-value result — no chart is forced on one number.", fmt["subtitle"])
    if not df.empty:
        first_col = df.columns[0]
        ws.write(row + 2, 1, first_col, fmt["kpi_label"])
        ws.write(row + 3, 1, _excel_safe(df.iloc[0][first_col]), fmt["kpi_value"])


def _write_decomposition_table(ws, fmt, decomposition, row: int, col: int) -> None:
    ws.write(row, col, "Sub-segment", fmt["header"])
    ws.write(row, col + 1, "Share of change", fmt["header"])
    for i, entry in enumerate(decomposition[:10], start=1):
        ws.write(row + i, col, entry.sub_segment)
        ws.write(row + i, col + 1, entry.share_of_change, fmt["pct"])


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
        "line": {"color": _ACCENT, "width": 2.5, **({"dash_type": "dash"} if spec.forecast_forced else {})},
        "fill": {"color": _ACCENT},
    })
    chart.set_title({"name": spec.y_field or "Result", "name_font": {"size": 12, "color": _ACCENT}})
    chart.set_legend({"position": "bottom"})
    chart.set_style(10)
    chart.set_x_axis({"num_font": {"size": 9}})
    chart.set_y_axis({"num_font": {"size": 9}, "major_gridlines": {"visible": True, "line": {"color": "#E8E8E8"}}})
    return chart


def _write_signals_sheet(wb, fmt, signals: SignalsPackage) -> None:
    ws = wb.add_worksheet("Signals")
    ws.set_column("A:A", 32)
    ws.set_column("B:B", 24)
    ws.write_row(0, 0, ["Signal", "Value"], fmt["header"])
    row = 1

    def _put(label: str, value: Any) -> None:
        nonlocal row
        ws.write(row, 0, label)
        ws.write(row, 1, str(value))
        row += 1

    if signals.period_change:
        _put("Period change (%)", f"{signals.period_change.pct_change:+.2f}%")
        _put("Period change (absolute)", signals.period_change.absolute_change)
    if signals.yoy_change:
        _put("YoY change (%)", f"{signals.yoy_change.pct_change:+.2f}%")
    if signals.zscore:
        _put("Z-score", signals.zscore.value)
        _put("Z-score bucket", signals.zscore.bucket)
    if signals.concentration_index is not None:
        _put("Concentration index (HHI)", signals.concentration_index)
    for entry in signals.decomposition:
        _put(f"Decomposition: {entry.sub_segment}", f"{entry.share_of_change:.2%}")
    for flag in signals.data_quality_flags:
        _put(f"DQ flag [{flag.severity}] {flag.kind}", flag.detail)


def _write_forecast_sheet(wb, fmt, forecast_df: pd.DataFrame, signals) -> None:
    ws = wb.add_worksheet("Forecast")
    for col_idx, col_name in enumerate(forecast_df.columns):
        ws.write(0, col_idx, col_name, fmt["header"])
    for row_idx, row in enumerate(forecast_df.itertuples(index=False), start=1):
        for col_idx, value in enumerate(row):
            ws.write(row_idx, col_idx, _excel_safe(value))

    if signals and signals.forecast:
        note_row = len(forecast_df) + 2
        ws.write(note_row, 0, f"Model used: {signals.forecast.model_used}")
        ws.write(note_row + 1, 0, f"Backtest MAPE: {signals.forecast.backtest_mape:.2f}%")


def _format_for_value(fmt: dict, value: Any):
    if isinstance(value, (pd.Timestamp,)):
        return fmt["date"]
    if isinstance(value, float):
        return fmt["number"]
    return None


def _excel_safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.to_pydatetime()
    return value
