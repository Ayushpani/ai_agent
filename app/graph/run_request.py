"""Top-level entry point used by both the FastAPI route and the Chainlit
UI: invoke the graph for one employee question, write the audit record,
and return a plain result object. Keeps interface code free of graph
internals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.graph.build import get_graph
from app.models.schemas import AccessScope, AuditLogRecord
from app.observability.audit_log import write_audit_record
from app.observability.logging_setup import get_logger

logger = get_logger()


def handle_question(
    question: str,
    session_id: str,
    employee_id: str,
    role: str,
    employee_region: str | None = None,
    employee_branch: str | None = None,
) -> dict[str, Any]:
    scope = AccessScope(
        employee_id=employee_id, role=role,
        employee_region=employee_region, employee_branch=employee_branch,
    )
    graph = get_graph()

    initial_state = {"question": question, "session_id": session_id, "access_scope": scope}

    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        logger.error("graph_invocation_failed", error=str(e), session_id=session_id)
        write_audit_record(AuditLogRecord(
            timestamp=datetime.now(timezone.utc),
            employee_id=employee_id, session_id=session_id, question=question,
            error=str(e),
        ))
        return {
            "narration": "Something went wrong answering that question. The team has been notified.",
            "error": str(e),
        }

    router_output = result.get("router_output")
    write_audit_record(AuditLogRecord(
        timestamp=datetime.now(timezone.utc),
        employee_id=employee_id, session_id=session_id, question=question,
        router_output=router_output,
        generated_sql_raw=result.get("sql_output").sql if result.get("sql_output") else None,
        generated_sql_final=result.get("final_sql"),
        tool_sequence=result.get("tool_sequence", []),
        model_ids_used=result.get("model_ids_used", {}),
        latency_ms_per_stage=result.get("latency_ms_per_stage", {}),
        narration_output=result.get("narration"),
        error=result.get("error"),
    ))

    return {
        "narration": result.get("narration"),
        "chart_spec": result.get("chart_spec"),
        "query_result": result.get("query_result"),
        "signals": result.get("signals"),
        "error": result.get("error"),
        "final_sql": result.get("final_sql"),
    }
