"""FastAPI request boundary (doc §3.1, §4). Async, typed. Employee
identity comes from the corporate OIDC provider in production; the POC
accepts it directly in the request body behind a placeholder auth
dependency (see get_current_employee) that is the single place to wire
in real OIDC token verification later.
"""
from __future__ import annotations

import io

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.graph.run_request import handle_question
from app.models.schemas import ChartType
from app.observability.logging_setup import configure_logging
from app.tools.workbook import build_excel_workbook

configure_logging()

app = FastAPI(title="Portfolio Intelligence Agent")

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

    _LAST_RESULT_BY_SESSION[request.session_id] = result

    query_result = result.get("query_result")
    response = {k: v for k, v in result.items() if k != "query_result"}
    if query_result is not None:
        response["row_count"] = len(query_result)
        response["preview_rows"] = query_result.head(20).to_dict(orient="records")
    return response


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
        question="(see audit log for original question)",
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
