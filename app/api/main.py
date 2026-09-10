"""FastAPI request boundary (doc §3.1, §4). Async, typed. Employee
identity comes from the corporate OIDC provider in production; the POC
accepts it directly in the request body behind a placeholder auth
dependency (see get_current_employee) that is the single place to wire
in real OIDC token verification later.
"""
from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.graph.run_request import handle_question, stream_question
from app.models.schemas import ChartType
from app.observability.logging_setup import configure_logging
from app.tools.workbook import build_excel_workbook

configure_logging()

app = FastAPI(title="Portfolio Intelligence Agent")

# The Next.js dev server origin. Add production origins here once deployed —
# this is the one place CORS is configured.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# In-memory holder for the last result per session, so the download
# endpoint can build the workbook without re-running the whole graph.
# A production build persists this keyed by request_id instead.
_LAST_RESULT_BY_SESSION: dict[str, dict] = {}


class EmployeeIdentity(BaseModel):
    employee_id: str
    role: str
    employee_region: str | None = None
    employee_branch: str | None = None


class AskRequest(BaseModel):
    session_id: str
    question: str
    identity: EmployeeIdentity


def get_current_employee(identity: EmployeeIdentity) -> EmployeeIdentity:
    """Placeholder for OIDC token verification (doc §4: 'Employee
    identity determines access-scope filter. No standalone user store.').
    Wire this to validate a bearer token against the corporate IdP and
    derive `identity` from verified claims, not client-supplied fields.
    """
    return identity


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest) -> dict:
    identity = get_current_employee(request.identity)
    result = handle_question(
        question=request.question,
        session_id=request.session_id,
        employee_id=identity.employee_id,
        role=identity.role,
        employee_region=identity.employee_region,
        employee_branch=identity.employee_branch,
    )

    _LAST_RESULT_BY_SESSION[request.session_id] = {**result, "question": request.question}

    query_result = result.get("query_result")
    response = {k: v for k, v in result.items() if k != "query_result"}
    if query_result is not None:
        response["row_count"] = len(query_result)
        response["preview_rows"] = query_result.head(20).to_dict(orient="records")
    return response


@app.post("/ask/stream")
async def ask_stream(request: AskRequest) -> StreamingResponse:
    """Server-Sent Events version of /ask for the Next.js UI: emits one
    `data:` line per pipeline stage as it actually starts/finishes
    (backed by stream_question's LangGraph event stream), then a final
    event with the complete answer. A plain request/response can't show
    live per-stage progress; this is what drives the animated step
    timeline in the frontend instead of a single opaque spinner.
    """
    identity = get_current_employee(request.identity)

    async def event_source():
        final_result: dict = {}
        async for event in stream_question(
            question=request.question,
            session_id=request.session_id,
            employee_id=identity.employee_id,
            role=identity.role,
            employee_region=identity.employee_region,
            employee_branch=identity.employee_branch,
        ):
            if event["kind"] == "final":
                final_result = event["result"]
            yield f"data: {json.dumps(_json_safe(event))}\n\n"

        _LAST_RESULT_BY_SESSION[request.session_id] = {**final_result, "question": request.question}

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/download/{session_id}")
def download_workbook(session_id: str):
    result = _LAST_RESULT_BY_SESSION.get(session_id)
    if result is None or result.get("query_result") is None:
        raise HTTPException(status_code=404, detail="No downloadable result for this session.")

    chart_spec = result.get("chart_spec")
    if chart_spec is None or chart_spec.chart_type == ChartType.kpi_callout:
        raise HTTPException(status_code=400, detail="This result has no chartable dashboard to export.")

    workbook_bytes = build_excel_workbook(
        data=result["query_result"],
        spec=chart_spec,
        question=result.get("question", "(see audit log for original question)"),
        generated_sql=result.get("final_sql", ""),
        employee_id="unknown",
        snapshot_months=[],
        signals=result.get("signals"),
    )

    return StreamingResponse(
        io.BytesIO(workbook_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="analysis_{session_id}.xlsx"'},
    )


def _json_safe(value: Any) -> Any:
    """Recursively converts pydantic models, DataFrames, and NaN/NaT into
    plain JSON-serializable structures for the SSE payload.
    """
    if isinstance(value, pd.DataFrame):
        return {"__type": "dataframe", "records": json.loads(value.to_json(orient="records", date_format="iso"))}
    if isinstance(value, BaseModel):
        return json.loads(value.model_dump_json())
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value
