"""Chainlit chat UI (doc §4, §3.2 interface layer). Streaming, file
attachments, and thread history come free from Chainlit — this module
wires the chat turn to the graph and renders a live "thinking" trace: a
collapsible, animated step per pipeline stage (Router -> SQL Generator
-> Execute -> Tools -> Analyst -> Narrator -> Chart) that opens when the
stage actually starts and closes when it actually finishes, backed by
LangGraph's real event stream rather than a replay of the final state.

Run with: chainlit run app/ui/chainlit_app.py -w
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

# Chainlit imports this file directly by path (`chainlit run app/ui/...`)
# without adding the project root to sys.path first, so the absolute
# `app.*` imports below fail unless we add it ourselves.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import chainlit as cl

from app.graph.run_request import stream_question
from app.models.schemas import ChartType
from app.tools.chart import render_inline_chart
from app.tools.workbook import build_excel_workbook

STAGE_LABELS = {
    "route": "Classifying the question",
    "disambiguate": "Needs clarification",
    "generate_sql": "Generating SQL",
    "execute": "Executing query (DuckDB)",
    "repair_sql": "Correcting the query",
    "handled_error": "Could not proceed",
    "run_tools": "Running analytical tools",
    "plan_research": "Planning deeper analysis",
    "run_probes": "Investigating the data",
    "synthesize": "Synthesising across panels",
    "analyze": "Analyst reasoning",
    "narrate": "Writing the answer",
    "chart": "Choosing chart type",
}

# In-memory holder so the download action can rebuild the workbook
# without re-running the graph. Keyed by session_id.
_LAST_RESULT_BY_SESSION: dict[str, dict] = {}


@cl.on_chat_start
async def on_chat_start() -> None:
    cl.user_session.set("session_id", str(uuid.uuid4()))
    # POC identity stand-in for the OIDC-derived identity in production.
    cl.user_session.set("employee_id", "EMP0001")
    cl.user_session.set("role", "admin")
    await cl.Message(
        content=(
            "**Portfolio Intelligence Agent** — ask a question about the loan portfolio.\n\n"
            "e.g. *\"What is the trend in 90+ AUM in Maharashtra over the last 6 months?\"*"
        )
    ).send()


def _summarize_stage(stage: str, update: dict) -> str:
    """Short, human-readable content for a completed step — enough to see
    what the pipeline actually did without dumping raw internals.
    """
    if stage == "route":
        router = update.get("router_output")
        return f"Intent: `{router.intent.value}`" if router else ""
    if stage == "generate_sql":
        sql_output = update.get("sql_output")
        if sql_output and sql_output.sql:
            return f"```sql\n{sql_output.sql}\n```"
        if sql_output and sql_output.error:
            return f"Refused: `{sql_output.error.error}`"
        return ""
    if stage == "execute":
        df = update.get("query_result")
        return f"{len(df)} rows returned." if df is not None else update.get("error", "")
    if stage == "run_tools":
        signals = update.get("signals")
        if not signals:
            return ""
        parts = []
        if signals.period_change:
            parts.append(f"period change {signals.period_change.pct_change:+.1f}%")
        if signals.zscore:
            parts.append(f"z-score {signals.zscore.value:.2f} ({signals.zscore.bucket})")
        if signals.data_quality_flags:
            parts.append(f"{len(signals.data_quality_flags)} data-quality flag(s)")
        return "; ".join(parts) or "No notable signals."
    if stage == "analyze":
        findings = update.get("analyst_output")
        if findings and findings.findings:
            return "\n".join(f"- {f.text}" for f in findings.findings)
        return "Skipped (lookup question)."
    if stage == "chart":
        spec = update.get("chart_spec")
        return f"Chart type: `{spec.chart_type.value}`" if spec else ""
    return ""


@cl.on_message
async def on_message(message: cl.Message) -> None:
    session_id = cl.user_session.get("session_id")
    employee_id = cl.user_session.get("employee_id")
    role = cl.user_session.get("role")

    open_steps: dict[str, cl.Step] = {}
    final_result: dict = {}

    async for event in stream_question(
        question=message.content, session_id=session_id, employee_id=employee_id, role=role,
    ):
        if event["kind"] == "stage_start":
            stage = event["stage"]
            step = cl.Step(name=STAGE_LABELS.get(stage, stage), type="tool")
            await step.send()
            open_steps[stage] = step

        elif event["kind"] == "stage_end":
            stage = event["stage"]
            step = open_steps.pop(stage, None)
            if step is not None:
                step.output = _summarize_stage(stage, event["update"])
                await step.update()

        elif event["kind"] == "final":
            final_result = event["result"]

    # Any step that never got a matching end (an exception mid-stage) —
    # close it out rather than leaving a spinner running forever.
    for step in open_steps.values():
        step.output = "Did not complete."
        await step.update()

    _LAST_RESULT_BY_SESSION[session_id] = final_result

    elements = []
    actions = []

    chart_spec = final_result.get("chart_spec")
    query_result = final_result.get("query_result")
    if chart_spec is not None and query_result is not None and chart_spec.chart_type != ChartType.kpi_callout:
        try:
            fig = render_inline_chart(query_result, chart_spec)
            elements.append(cl.Plotly(name="chart", figure=fig, display="inline"))
        except Exception:
            pass  # inline chart is best-effort; the narration still stands alone

        actions.append(cl.Action(
            name="download_workbook",
            payload={"session_id": session_id},
            label="Download analysis workbook",
        ))

    content = final_result.get("narration") or "No answer produced."
    if final_result.get("error"):
        content = f"{content}\n\n_({final_result['error']})_"

    await cl.Message(content=content, elements=elements, actions=actions).send()


@cl.action_callback("download_workbook")
async def on_download_workbook(action: cl.Action) -> None:
    session_id = action.payload.get("session_id")
    result = _LAST_RESULT_BY_SESSION.get(session_id)

    if not result or result.get("query_result") is None or result.get("chart_spec") is None:
        await cl.Message(content="No downloadable result for this session anymore.").send()
        return

    workbook_bytes = build_excel_workbook(
        data=result["query_result"],
        spec=result["chart_spec"],
        question="(see chat history above)",
        generated_sql=result.get("final_sql", ""),
        employee_id=cl.user_session.get("employee_id"),
        snapshot_months=[],
        signals=result.get("signals"),
    )

    file_element = cl.File(
        name="portfolio_analysis.xlsx",
        content=workbook_bytes,
        display="inline",
    )
    await cl.Message(content="Here's your analysis workbook.", elements=[file_element]).send()
