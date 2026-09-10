"""Graph node implementations. Every node here does exactly one job in
doc §3.2's End-to-End Request Flow. LLM calls happen ONLY in
router_node, sql_generator_node, analyst_node, narrator_node — every
other node is deterministic Python (doc §7: 'Tool sequence is fixed per
intent').

Note on LangGraph state mutation: a node's return value is the ONLY
thing LangGraph merges into global state — mutating the `state` dict
argument in place is silently discarded. StageTracer below exists so
tool_sequence/latency accumulate correctly across nodes without that
foot-gun.
"""
from __future__ import annotations

import json
import time

from app.graph.llm_output import extract_json_object
from app.graph.model_router import call_stage
from app.graph.state import GraphState
from app.models.schemas import (
    AnalystOutput,
    DataQualityFlag,
    ForecastResult,
    Intent,
    RouterOutput,
    SQLGeneratorError,
    SQLGeneratorOutput,
)
from app.prompts import load_prompt
from app.security.sql_validator import extract_sql_statement
from app.tools.chart import QueryShape, choose_chart_type
from app.tools.data import get_schema_card, run_sql
from app.tools.dq import data_quality_scan, sanity_check_trend
from app.tools.forecast import forecast, forecast_feasibility
from app.tools.signal_boundary import package_signals
from app.tools.stats import concentration_index, period_change, zscore_latest


class StageTracer:
    """Accumulates tool_sequence + latency for one node's return dict,
    seeded from the existing state so entries from earlier nodes survive.
    """

    def __init__(self, state: GraphState):
        self.tool_sequence: list[str] = list(state.get("tool_sequence", []))
        self.latency_ms_per_stage: dict[str, float] = dict(state.get("latency_ms_per_stage", {}))

    def run(self, stage: str, fn, *args, **kwargs):
        start = time.time()
        result = fn(*args, **kwargs)
        self.latency_ms_per_stage[stage] = (time.time() - start) * 1000
        self.tool_sequence.append(stage)
        return result

    def mark(self, stage: str) -> None:
        self.tool_sequence.append(stage)

    def as_update(self) -> dict:
        return {
            "tool_sequence": self.tool_sequence,
            "latency_ms_per_stage": self.latency_ms_per_stage,
        }


def _with_model_id(state: GraphState, stage: str, model_id: str) -> dict:
    return {"model_ids_used": {**state.get("model_ids_used", {}), stage: model_id}}


def router_node(state: GraphState) -> dict:
    raw = call_stage("router", load_prompt("router"), state["question"])
    parsed = extract_json_object(raw)
    if parsed is None:
        raise ValueError(
            f"Router response contained no parseable JSON object "
            f"(model may be a reasoning variant that never reached its "
            f"final answer): {raw[:300]!r}"
        )
    router_output = RouterOutput.model_validate(parsed)

    update: dict = {
        "router_output": router_output,
        "needs_disambiguation": router_output.ambiguous_aggregation_level,
        **_with_model_id(state, "router", "stage:router"),
    }
    if router_output.ambiguous_aggregation_level:
        metric = next(
            (e for e in router_output.entities if e.upper() in {"AUM", "AUF", "POS"}),
            "AUM/AUF/POS",
        )
        update["disambiguation_message"] = load_prompt("disambiguation").format(metric=metric)
    return update


def sql_generator_node(state: GraphState) -> dict:
    role = state["access_scope"].role
    schema_card = get_schema_card(role=role)
    context = (
        f"Question: {state['question']}\n"
        f"Intent metadata: {state['router_output'].model_dump_json()}\n"
        f"Schema card: {json.dumps(schema_card)}\n"
    )
    # Reasoning-style free models spend a large chunk of their budget on a
    # chain-of-thought preamble before emitting the actual SQL — 1024
    # tokens (the default) can get cut off before they ever reach it.
    raw = call_stage("sql_generator", load_prompt("sql_generator"), context, max_tokens=3072)
    raw_stripped = raw.strip()

    error_payload = extract_json_object(raw_stripped)
    if error_payload is not None and "error" in error_payload:
        sql_output = SQLGeneratorOutput(error=SQLGeneratorError.model_validate(error_payload))
    else:
        extracted_sql = extract_sql_statement(raw_stripped)
        if extracted_sql is None:
            sql_output = SQLGeneratorOutput(
                error=SQLGeneratorError(
                    error="insufficient_schema",
                    missing=(
                        "model response contained no parseable SQL statement "
                        "with the required {ACCESS_SCOPE_FILTER} placeholder "
                        "(model may be a reasoning variant that never reached "
                        "its final answer within the token budget)"
                    ),
                )
            )
        else:
            sql_output = SQLGeneratorOutput(sql=extracted_sql)

    return {
        "sql_output": sql_output,
        **_with_model_id(state, "sql_generator", "stage:sql_generator"),
    }


def execute_query_node(state: GraphState) -> dict:
    tracer = StageTracer(state)
    sql_output = state["sql_output"]
    if sql_output.error is not None:
        return {
            "error": f"{sql_output.error.error}: {sql_output.error.missing or ''}".strip(),
            **tracer.as_update(),
        }

    df = tracer.run("run_sql", run_sql, sql_output.sql, state["access_scope"])
    return {"query_result": df, "final_sql": sql_output.sql, "error": None, **tracer.as_update()}


def tools_node(state: GraphState) -> dict:
    """Fixed tool sequence per intent (doc §7.6). This POC implementation
    covers the common shape of a query result with one time/category
    column and one numeric metric column; a production build would
    thread the SQL Generator's declared output schema through to select
    the right columns unambiguously rather than inferring by dtype.
    """
    tracer = StageTracer(state)
    df = state["query_result"]
    intent = state["router_output"].intent

    dq_flags: list[DataQualityFlag] = tracer.run("data_quality_scan", data_quality_scan, df)

    numeric_cols = [c for c in df.columns if df[c].dtype.kind in "fi"]
    time_cols = [c for c in df.columns if "month" in c.lower() or "date" in c.lower()]
    metric_col = numeric_cols[0] if numeric_cols else None

    period_chg = None
    yoy_chg = None
    zscore_result = None
    decomposition: list = []
    concentration = None
    forecast_result: ForecastResult | None = None

    if metric_col and time_cols:
        series = df.sort_values(time_cols[0])[metric_col].reset_index(drop=True)

        if len(series) >= 2:
            period_chg = tracer.run("period_change", period_change, series, 1, "period")
        if len(series) >= 13:
            yoy_chg = period_change(series, 12, "YoY")
        if len(series) >= 2:
            zscore_result = tracer.run("zscore_latest", zscore_latest, series)

        dq_flags += tracer.run("sanity_check_trend", sanity_check_trend, series)

        if intent == Intent.forecast:
            feasible, reason = forecast_feasibility(series)
            if feasible:
                forecast_result = tracer.run("forecast", forecast, series, 3)
            else:
                forecast_result = ForecastResult(
                    horizon=3, point_forecast=[], interval_low=[], interval_high=[],
                    model_used="none", backtest_mape=float("nan"),
                    feasible=False, feasibility_reason=reason,
                )

    non_metric_cols = [c for c in df.columns if c not in numeric_cols and c not in time_cols]
    if metric_col and non_metric_cols and len(df) > 1:
        concentration = tracer.run(
            "concentration_index", concentration_index, df.groupby(non_metric_cols[0])[metric_col].sum()
        )

    signals = package_signals(
        question=state["question"],
        intent=intent,
        query_result_summary={"row_count": len(df), "columns": list(df.columns)},
        period_change=period_chg,
        yoy_change=yoy_chg,
        zscore=zscore_result,
        decomposition=decomposition,
        concentration_index=concentration,
        forecast=forecast_result,
        data_quality_flags=dq_flags,
    )
    tracer.mark("package_signals")
    return {"signals": signals, **tracer.as_update()}


def analyst_node(state: GraphState) -> dict:
    """Skipped for 'lookup' intent (doc §7.6: forcing analyst rigor onto a
    single-fact question manufactures insight that does not exist).
    """
    if state["router_output"].intent == Intent.lookup:
        return {"analyst_output": AnalystOutput(findings=[])}

    context = (
        f"Question: {state['question']}\n"
        f"Query result: {state['query_result'].to_dict(orient='records')[:20]}\n"
        f"Signals JSON: {state['signals'].model_dump_json()}\n"
    )
    raw = call_stage("analyst", load_prompt("analyst"), context, max_tokens=1024)

    from app.models.schemas import AnalystFinding
    findings = [
        AnalystFinding(text=line.strip("- ").strip())
        for line in raw.splitlines() if line.strip()
    ]

    return {
        "analyst_output": AnalystOutput(findings=findings),
        **_with_model_id(state, "analyst", "stage:analyst"),
    }


def narrator_node(state: GraphState) -> dict:
    findings_text = "\n".join(f"- {f.text}" for f in state["analyst_output"].findings)
    context = f"Question: {state['question']}\nFindings:\n{findings_text}"
    prose = call_stage("narrator", load_prompt("narrator"), context, max_tokens=512)

    return {
        "narration": prose,
        **_with_model_id(state, "narrator", "stage:narrator"),
    }


def chart_node(state: GraphState) -> dict:
    tracer = StageTracer(state)
    df = state["query_result"]
    numeric_cols = [c for c in df.columns if df[c].dtype.kind in "fi"]
    time_cols = [c for c in df.columns if "month" in c.lower() or "date" in c.lower()]
    category_cols = [c for c in df.columns if c not in numeric_cols and c not in time_cols]

    signals = state.get("signals")
    has_forecast = bool(signals and signals.forecast and signals.forecast.feasible)

    shape = QueryShape(
        has_time_dimension=bool(time_cols),
        category_column=category_cols[0] if category_cols else None,
        category_cardinality=df[category_cols[0]].nunique() if category_cols else 0,
        metric_columns=numeric_cols,
        is_composition=False,
        has_forecast=has_forecast,
        is_single_scalar=(len(df) == 1 and len(df.columns) <= 2),
        time_column=time_cols[0] if time_cols else None,
    )
    spec = choose_chart_type(shape)
    tracer.mark("choose_chart_type")
    return {"chart_spec": spec, **tracer.as_update()}
