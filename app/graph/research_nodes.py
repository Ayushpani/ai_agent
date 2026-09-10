"""Deep-research graph nodes: plan, probe, synthesise.

The headline query has already run by the time these execute. This layer
is what turns a single number into an analysis: the planner proposes a
small set of follow-up investigations from a closed catalog, each is
executed deterministically (app/tools/probes.py) and measured with the
same statistical tools as the headline, and the synthesis step reasons
across all of them at once.

Cost discipline (doc §10.2): a deep run costs one planner call plus one
synthesis call on top of the standard pipeline — the probes themselves
are pure SQL, no LLM. That keeps a "go deeper" request at roughly six
free-tier calls rather than the dozen a free-form agent loop would burn.
"""
from __future__ import annotations

import pandas as pd

from app.graph.llm_output import extract_json_object
from app.graph.model_router import call_stage
from app.graph.state import GraphState
from app.models.schemas import (
    AnalysisPanel,
    AnalystFinding,
    AnalystOutput,
    ChartType,
    Intent,
    ProbeSpec,
    ResearchDepth,
    ResearchPlan,
)
from app.prompts import load_prompt
from app.tools.data import run_sql
from app.tools.dq import data_quality_scan
from app.tools.probes import ProbeBuildError, build_probe_sql, queryable_columns
from app.tools.signal_boundary import package_signals
from app.tools.stats import concentration_index, period_change, zscore_latest

MAX_PROBES = 4
MAX_PANEL_ROWS_TO_MODEL = 15


def should_go_deep(state: GraphState) -> bool:
    """Deep research is opt-in per request, and never applied to a
    single-fact lookup — running four breakdowns against "how many active
    loans do we have" manufactures exactly the insight doc §7.6 warns
    against.
    """
    if state.get("research_depth") != ResearchDepth.deep:
        return False
    if state.get("error"):
        return False
    router_output = state.get("router_output")
    if router_output is not None and router_output.intent == Intent.lookup:
        return False
    return state.get("query_result") is not None


def plan_research_node(state: GraphState) -> dict:
    role = state["access_scope"].role
    columns = sorted(queryable_columns(role))
    signals = state.get("signals")

    context = (
        f"Question: {state['question']}\n"
        f"Intent metadata: {state['router_output'].model_dump_json()}\n"
        f"Headline signals: {signals.model_dump_json() if signals else '{}'}\n"
        f"Available columns for this role: {', '.join(columns)}\n"
    )
    raw = call_stage("research_planner", load_prompt("research_planner"), context, max_tokens=1500)
    parsed = extract_json_object(raw)

    if parsed is None:
        # A planner that produced nothing parseable is not a hard failure —
        # the headline answer still stands, we just don't deepen it.
        return {"research_plan": ResearchPlan(
            should_go_deeper=False,
            reasoning="The research planner returned no parseable plan; answering at headline level.",
        )}

    try:
        plan = ResearchPlan.model_validate(parsed)
    except Exception as e:
        return {"research_plan": ResearchPlan(
            should_go_deeper=False,
            reasoning=f"The research planner's output failed validation ({e}); answering at headline level.",
        )}

    plan.probes = plan.probes[:MAX_PROBES]
    return {"research_plan": plan}


def run_probes_node(state: GraphState) -> dict:
    """Executes each planned probe. A probe that fails to build or run
    becomes a panel carrying its error rather than aborting the request —
    three good panels out of four is a better answer than none.
    """
    plan = state.get("research_plan")
    if plan is None or not plan.should_go_deeper or not plan.probes:
        return {"panels": []}

    role = state["access_scope"].role
    panels: list[AnalysisPanel] = []

    for i, spec in enumerate(plan.probes):
        panels.append(_run_single_probe(spec, i, role, state))

    return {"panels": panels}


def _run_single_probe(spec: ProbeSpec, index: int, role: str, state: GraphState) -> AnalysisPanel:
    panel_id = f"panel-{index + 1}"

    try:
        sql, chart_spec = build_probe_sql(spec, role=role)
    except ProbeBuildError as e:
        return AnalysisPanel(
            panel_id=panel_id, title=spec.title, rationale=spec.rationale,
            probe_type=spec.probe_type,
            chart_spec=_empty_chart(), error=str(e),
        )

    try:
        df = run_sql(sql, state["access_scope"])
    except Exception as e:
        return AnalysisPanel(
            panel_id=panel_id, title=spec.title, rationale=spec.rationale,
            probe_type=spec.probe_type, sql=sql,
            chart_spec=chart_spec, error=f"Query failed: {e}",
        )

    if df.empty:
        return AnalysisPanel(
            panel_id=panel_id, title=spec.title, rationale=spec.rationale,
            probe_type=spec.probe_type, sql=sql, chart_spec=chart_spec,
            error="This breakdown returned no rows.",
        )

    signals = _measure_panel(spec, df, state)
    headline = _panel_headline(spec, df, signals)

    return AnalysisPanel(
        panel_id=panel_id,
        title=spec.title,
        rationale=spec.rationale,
        probe_type=spec.probe_type,
        chart_spec=chart_spec,
        records=_records(df),
        signals=signals,
        sql=sql,
        headline=headline,
    )


def _measure_panel(spec: ProbeSpec, df: pd.DataFrame, state: GraphState):
    """Runs the same deterministic tools over a panel that the headline
    result gets — the panels are analysis, not decoration.
    """
    intent = state["router_output"].intent
    flags = data_quality_scan(df)

    concentration = None
    period_chg = None
    zscore_result = None

    if "value" in df.columns:
        series = df["value"]
        if "period" in df.columns and len(series) >= 2:
            ordered = df.sort_values("period")["value"].reset_index(drop=True)
            # A multi-series panel interleaves segments; period-over-period
            # on that mixed series would be meaningless.
            if "segment" not in df.columns:
                period_chg = period_change(ordered, 1, "period")
                zscore_result = zscore_latest(ordered)
        elif "segment" in df.columns and len(series) >= 2:
            concentration = concentration_index(series)

    return package_signals(
        question=spec.title,
        intent=intent,
        query_result_summary={"row_count": len(df), "columns": list(df.columns)},
        period_change=period_chg,
        zscore=zscore_result,
        concentration_index=concentration,
        data_quality_flags=flags,
    )


def _panel_headline(spec: ProbeSpec, df: pd.DataFrame, signals) -> str | None:
    """One deterministic sentence per panel, computed not generated — it
    is shown under the chart, so it must never drift from the numbers."""
    if signals is None:
        return None

    if signals.concentration_index is not None and "segment" in df.columns:
        top = df.iloc[0]
        total = df["value"].sum()
        share = (top["value"] / total * 100) if total else 0
        return (
            f"{top['segment']} is the largest at {share:.0f}% of the shown total; "
            f"concentration index {signals.concentration_index:.2f}."
        )

    if signals.period_change is not None:
        return (
            f"Latest period moved {signals.period_change.pct_change:+.1f}% "
            f"versus the prior one."
        )

    if {"first_period", "latest_period"}.issubset(df.columns):
        movers = df.assign(delta=df["latest_period"] - df["first_period"]).sort_values(
            "delta", ascending=False
        )
        top = movers.iloc[0]
        return f"{top['segment']} shows the largest increase across the window."

    return None


def synthesis_node(state: GraphState) -> dict:
    """Replaces the single-result analyst step when panels exist: reasons
    across the headline and every panel at once.
    """
    panels = state.get("panels") or []
    signals = state.get("signals")

    panel_blocks = []
    for panel in panels:
        if panel.error:
            panel_blocks.append(f"Panel '{panel.title}' failed: {panel.error}")
            continue
        panel_blocks.append(
            f"Panel '{panel.title}' (reason: {panel.rationale})\n"
            f"  signals: {panel.signals.model_dump_json() if panel.signals else '{}'}\n"
            f"  rows: {panel.records[:MAX_PANEL_ROWS_TO_MODEL]}"
        )

    context = (
        f"Question: {state['question']}\n"
        f"Headline rows: {_records(state['query_result'])[:MAX_PANEL_ROWS_TO_MODEL]}\n"
        f"Headline signals: {signals.model_dump_json() if signals else '{}'}\n\n"
        + "\n\n".join(panel_blocks)
    )

    raw = call_stage("synthesis", load_prompt("synthesis"), context, max_tokens=1500)
    findings = [
        AnalystFinding(text=line.strip("- ").strip())
        for line in raw.splitlines()
        if line.strip()
    ]

    return {
        "analyst_output": AnalystOutput(findings=findings),
        "model_ids_used": {**state.get("model_ids_used", {}), "synthesis": "stage:synthesis"},
    }


def _records(df: pd.DataFrame) -> list[dict]:
    import json

    return json.loads(df.to_json(orient="records", date_format="iso"))


def _empty_chart():
    from app.models.schemas import ChartSpec

    return ChartSpec(chart_type=ChartType.kpi_callout)
