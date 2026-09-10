"""Chainlit chat UI (doc §4, §3.2 interface layer). Streaming, file
attachments, and thread history come free from Chainlit — this module
just wires the chat turn to the graph and renders the result.

Run with: chainlit run app/ui/chainlit_app.py
"""
from __future__ import annotations

import uuid

import chainlit as cl

from app.graph.run_request import handle_question
from app.models.schemas import ChartType
from app.tools.chart import render_inline_chart


@cl.on_chat_start
async def on_chat_start() -> None:
    cl.user_session.set("session_id", str(uuid.uuid4()))
    # POC identity stand-in for the OIDC-derived identity in production.
    cl.user_session.set("employee_id", "EMP0001")
    cl.user_session.set("role", "admin")
    await cl.Message(
        content=(
            "Ask a question about the loan portfolio — e.g. "
            "\"What is the trend in 90+ AUM in Maharashtra over the last 6 months?\""
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    session_id = cl.user_session.get("session_id")
    employee_id = cl.user_session.get("employee_id")
    role = cl.user_session.get("role")

    result = handle_question(
        question=message.content,
        session_id=session_id,
        employee_id=employee_id,
        role=role,
    )

    elements = []
    actions = []

    chart_spec = result.get("chart_spec")
    query_result = result.get("query_result")
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

    await cl.Message(
        content=result.get("narration") or "No answer produced.",
        elements=elements,
        actions=actions,
    ).send()


@cl.action_callback("download_workbook")
async def on_download_workbook(action: cl.Action) -> None:
    await cl.Message(
        content=(
            "Use GET /download/{session_id} on the API for the workbook "
            "download in this POC build; wiring a direct in-chat file "
            "send is a follow-up once the FastAPI service and Chainlit "
            "app share a session store."
        )
    ).send()
