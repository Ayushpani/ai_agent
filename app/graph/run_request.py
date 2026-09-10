"""Top-level entry points used by the FastAPI route and the Chainlit UI:
invoke the graph for one employee question, write the audit record, and
return a plain result object. Keeps interface code free of graph internals.

Two entry points:
  - handle_question: synchronous, single-shot (used by the API).
  - stream_question: async generator that yields a live event per graph
    node as it starts/finishes (used by the Chainlit UI to drive
    real-time "thinking" steps rather than a single opaque wait).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator

from app.graph.build import get_graph
from app.models.schemas import AccessScope, AuditLogRecord
from app.observability.audit_log import write_audit_record
from app.observability.logging_setup import get_logger

logger = get_logger()

# Node names that correspond to a real pipeline stage worth surfacing to
# the employee — internal LangGraph routing/wrapper nodes are filtered out.
GRAPH_NODE_NAMES = {
    "route", "disambiguate", "generate_sql", "execute",
    "handled_error", "run_tools", "analyze", "narrate", "chart",
}


def _build_result(result: dict) -> dict[str, Any]:
    return {
        "narration": result.get("narration"),
        "chart_spec": result.get("chart_spec"),
        "query_result": result.get("query_result"),
        "signals": result.get("signals"),
        "error": result.get("error"),
        "final_sql": result.get("final_sql"),
    }


def _write_audit(
    result: dict, question: str, session_id: str, employee_id: str, error: str | None = None,
) -> None:
    write_audit_record(AuditLogRecord(
        timestamp=datetime.now(timezone.utc),
        employee_id=employee_id, session_id=session_id, question=question,
        router_output=result.get("router_output"),
        generated_sql_raw=result.get("sql_output").sql if result.get("sql_output") else None,
        generated_sql_final=result.get("final_sql"),
        tool_sequence=result.get("tool_sequence", []),
        model_ids_used=result.get("model_ids_used", {}),
        latency_ms_per_stage=result.get("latency_ms_per_stage", {}),
        narration_output=result.get("narration"),
        error=error or result.get("error"),
    ))


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
        _write_audit({}, question, session_id, employee_id, error=str(e))
        return {
            "narration": "Something went wrong answering that question. The team has been notified.",
            "error": str(e),
        }

    _write_audit(result, question, session_id, employee_id)
    return _build_result(result)


async def stream_question(
    question: str,
    session_id: str,
    employee_id: str,
    role: str,
    employee_region: str | None = None,
    employee_branch: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yields one event per pipeline stage in real time:

        {"kind": "stage_start", "stage": "route"}
        {"kind": "stage_end", "stage": "route", "update": {...}}
        {"kind": "final", "result": {...}}

    Backed by LangGraph's astream_events, which fires on_chain_start /
    on_chain_end as each node actually begins and completes — this is
    genuine live progress, not a replay of the final state.
    """
    scope = AccessScope(
        employee_id=employee_id, role=role,
        employee_region=employee_region, employee_branch=employee_branch,
    )
    graph = get_graph()
    initial_state = {"question": question, "session_id": session_id, "access_scope": scope}

    final_state: dict = {}

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            name = event.get("name")
            if name not in GRAPH_NODE_NAMES:
                continue

            if event["event"] == "on_chain_start":
                yield {"kind": "stage_start", "stage": name}
            elif event["event"] == "on_chain_end":
                update = event.get("data", {}).get("output") or {}
                final_state.update(update)
                yield {"kind": "stage_end", "stage": name, "update": update}
    except Exception as e:
        logger.error("graph_stream_failed", error=str(e), session_id=session_id)
        _write_audit(final_state, question, session_id, employee_id, error=str(e))
        yield {
            "kind": "final",
            "result": {
                "narration": "Something went wrong answering that question. The team has been notified.",
                "error": str(e),
            },
        }
        return

    _write_audit(final_state, question, session_id, employee_id)
    yield {"kind": "final", "result": _build_result(final_state)}
