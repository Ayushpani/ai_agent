"""build_excel_workbook (doc §7.5, §8.1) — the only mature Python library
that writes native Excel chart objects from scratch is XlsxWriter, which
is what makes this a real analytical deliverable (editable charts) rather
than a screenshot.
"""
from __future__ import annotations

import io
import re
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
    panels: list | None = None,
    narration: str | None = None,
) -> bytes:
    """Cover + Dashboard + Data (+Signals, +Forecast) sheets, plus one
    sheet per deep-research analysis panel. Same chart-type decision as
    the inline chat chart, so the two can't disagree. The Dashboard is
    the sheet that opens active — it's the deliverable; Cover is
    provenance, not the headline.
    """
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    fmt = _build_formats(wb)
    panels = panels or []

    _write_cover_sheet(wb, fmt, question, generated_sql, employee_id, snapshot_months, narration)
    export_df = data.drop(columns=[c for c in EXCLUDED_EXPORT_COLUMNS if c in data.columns])
    dashboard_ws = _write_dashboard_sheet(wb, fmt, export_df, spec, signals, question, panels)
    _write_data_sheet(wb, fmt, export_df)

    for i, panel in enumerate(panels):
        _write_panel_sheet(wb, fmt, panel, i)

    if signals is not None:
        _write_signals_sheet(wb, fmt, signals)

    if forecast_df is not None:
        _write_forecast_sheet(wb, fmt, forecast_df, signals)

    dashboard_ws.activate()
    wb.close()
    return buf.getvalue()


def _panel_sheet_names(panel, index: int) -> tuple[str, str]:
    """Excel sheet names cap at 31 chars and can't contain []:*?/\\ —
    derive a safe, unique pair (chart sheet, data sheet) per panel."""
    safe = re.sub(r"[\[\]:*?/\\]", "", panel.title)[:18].strip() or f"Panel {index + 1}"
    return f"{index + 1}. {safe}"[:31], f"{index + 1}. {safe} data"[:31]


def _write_panel_sheet(wb, fmt, panel, index: int) -> None:
    """One sheet per analysis panel: its chart, its reason for existing,
    its deterministic headline, and the rows behind it — so a reader can
    audit any panel without leaving Excel."""
    chart_name, data_name = _panel_sheet_names(panel, index)
    df = pd.DataFrame(panel.records)

    data_ws = wb.add_worksheet(data_name)
    if not df.empty:
        for col_idx, col_name in enumerate(df.columns):
            data_ws.write(0, col_idx, col_name, fmt["header"])
            data_ws.set_column(col_idx, col_idx, 18)
        for row_idx, row in enumerate(df.itertuples(index=False), start=1):
            for col_idx, value in enumerate(row):
                data_ws.write(row_idx, col_idx, _excel_safe(value), _format_for_value(fmt, value))

    ws = wb.add_worksheet(chart_name)
    ws.hide_gridlines(2)
    ws.set_column("A:A", 3)
    ws.set_column("B:R", 12)
    ws.merge_range("B2:R2", panel.title, fmt["title"])
    ws.merge_range("B3:R3", panel.rationale, fmt["subtitle"])

    if panel.error:
        ws.write(5, 1, f"This panel could not be produced: {panel.error}", fmt["wrap"])
        return

    if panel.headline:
        ws.merge_range("B5:R5", panel.headline, fmt["label_bold"])

    if not df.empty:
        chart = _native_chart_for_spec(wb, panel.chart_spec, df, data_name)
        if chart is not None:
            chart.set_size({"width": 720, "height": 360})
            ws.insert_chart(7, 1, chart)


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


def _write_cover_sheet(
    wb, fmt, question, generated_sql, employee_id, snapshot_months, narration=None
) -> None:
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

    if narration:
        ws.write(r, 0, "Answer", fmt["label_bold"])
        ws.set_row(r, 90)
        ws.write(r, 1, narration, fmt["wrap"])
        r += 2

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


def _write_dashboard_sheet(
    wb, fmt, df: pd.DataFrame, spec: ChartSpec, signals, question: str, panels: list | None = None
):
    ws = wb.add_worksheet("Dashboard")
    ws.hide_gridlines(2)
    ws.set_column("A:A", 3)
    ws.set_column("B:R", 12)

    ws.merge_range("B2:R2", question, fmt["title"])
    row_after_title = 4

    kpi_col = _write_kpi_strip(ws, fmt, signals, start_row=row_after_title, start_col=1)

    chart_row = kpi_col["next_row"] + 1
    ws.merge_range(chart_row, 1, chart_row, 9, "Headline", fmt["section_header"])

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

    if panels:
        _write_panel_index(ws, fmt, panels, start_row=chart_row + 24)

    return ws


def _write_panel_index(ws, fmt, panels: list, start_row: int) -> None:
    """A contents table on the Dashboard listing every deep-research
    panel, its reason for being run, and its computed headline — so the
    workbook reads as one analysis rather than a pile of loose sheets."""
    ws.merge_range(start_row, 1, start_row, 9, "Further analysis", fmt["section_header"])
    ws.write_row(start_row + 2, 1, ["Sheet", "Panel", "Why it was run", "What it shows"], fmt["header"])
    ws.set_column(2, 2, 24)
    ws.set_column(3, 3, 44)
    ws.set_column(4, 4, 52)

    for i, panel in enumerate(panels):
        chart_name, _ = _panel_sheet_names(panel, i)
        row = start_row + 3 + i
        ws.write(row, 1, chart_name)
        ws.write(row, 2, panel.title)
        ws.write(row, 3, panel.rationale, fmt["wrap"])
        ws.write(row, 4, panel.error or panel.headline or "", fmt["wrap"])


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


_SERIES_COLORS = ["#1F4E79", "#3D7AB5", "#7BA7D1", "#B7CDE3", "#164060", "#4F90C7", "#95B9DC"]


def _native_chart_for_spec(wb, spec: ChartSpec, df: pd.DataFrame, data_sheet: str):
    if spec.x_field not in df.columns:
        return None

    chart_type_map = {
        ChartType.line: "line",
        ChartType.multi_line: "line",
        ChartType.bar: "column",
        ChartType.grouped_bar: "column",
        ChartType.area: "area",
        ChartType.pie: "pie",
        ChartType.scatter: "scatter",
    }
    xl_type = chart_type_map.get(spec.chart_type)
    if xl_type is None:
        return None

    chart = wb.add_chart({"type": xl_type})
    columns = list(df.columns)
    n_rows = len(df)
    x_col_idx = columns.index(spec.x_field)

    if spec.chart_type is ChartType.grouped_bar and spec.value_fields:
        for i, field in enumerate(spec.value_fields):
            if field not in columns:
                continue
            col_idx = columns.index(field)
            chart.add_series({
                "categories": [data_sheet, 1, x_col_idx, n_rows, x_col_idx],
                "values": [data_sheet, 1, col_idx, n_rows, col_idx],
                "name": field,
                "fill": {"color": _SERIES_COLORS[i % len(_SERIES_COLORS)]},
            })
        title = " vs ".join(spec.value_fields)

    elif spec.chart_type is ChartType.multi_line and spec.series_field in columns:
        # The long-format rows carry one column of series labels; Excel
        # needs one series per label, so pivot before charting. The
        # pivoted block is written to the right of the raw rows on the
        # same data sheet, and the chart points at that block.
        return _multi_line_chart(wb, spec, df, data_sheet, chart)

    else:
        y_field = spec.y_field if spec.y_field in columns else None
        if y_field is None:
            return None
        y_col_idx = columns.index(y_field)
        chart.add_series({
            "categories": [data_sheet, 1, x_col_idx, n_rows, x_col_idx],
            "values": [data_sheet, 1, y_col_idx, n_rows, y_col_idx],
            "name": y_field,
            "line": {"color": _ACCENT, "width": 2.5, **({"dash_type": "dash"} if spec.forecast_forced else {})},
            "fill": {"color": _ACCENT},
        })
        title = y_field

    chart.set_title({"name": title, "name_font": {"size": 12, "color": _ACCENT}})
    chart.set_legend({"position": "bottom"})
    chart.set_style(10)
    chart.set_x_axis({"num_font": {"size": 9}})
    chart.set_y_axis({"num_font": {"size": 9}, "major_gridlines": {"visible": True, "line": {"color": "#E8E8E8"}}})
    return chart


def _multi_line_chart(wb, spec: ChartSpec, df: pd.DataFrame, data_sheet: str, chart):
    """XlsxWriter charts read contiguous cell ranges, so a long-format
    (period, segment, value) result has to be pivoted to one column per
    segment before it can be plotted as several lines.
    """
    pivot = df.pivot_table(
        index=spec.x_field, columns=spec.series_field, values=spec.y_field, aggfunc="sum"
    ).reset_index()

    # Park the pivoted block well clear of the raw rows on the same sheet.
    start_col = len(df.columns) + 2
    ws = None
    for worksheet in wb.worksheets():
        if worksheet.get_name() == data_sheet:
            ws = worksheet
            break
    if ws is None:
        return None

    for col_idx, col_name in enumerate(pivot.columns):
        ws.write(0, start_col + col_idx, str(col_name))
        for row_idx, value in enumerate(pivot[col_name], start=1):
            ws.write(row_idx, start_col + col_idx, _excel_safe(value))

    n_rows = len(pivot)
    for i, series_name in enumerate(pivot.columns[1:], start=1):
        chart.add_series({
            "categories": [data_sheet, 1, start_col, n_rows, start_col],
            "values": [data_sheet, 1, start_col + i, n_rows, start_col + i],
            "name": str(series_name),
            "line": {"color": _SERIES_COLORS[(i - 1) % len(_SERIES_COLORS)], "width": 2.25},
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
