"""The self-repair round: a statement that fails validation or execution
gets one more attempt with the engine's own error fed back, before the
turn fails with a readable message.

Motivated by two real failures. A free model wrote
`CAST('month' AS DATE)` — the router's `time_grain` value leaked into
the SQL as if it were a column — and the resulting DuckDB Conversion
Error propagated out of the node as an unhandled exception, taking down
the whole request rather than becoming an answerable state.
"""
import json
from unittest.mock import patch

import pytest

from app.graph.build import build_graph
from app.models.schemas import AccessScope

ROUTER_JSON = {
    "intent": "trend", "requires_chart": True, "requires_forecast": False,
    "time_grain": "month", "entities": ["STATE"],
    "ambiguous_aggregation_level": False, "ambiguity_reason": None,
}

GOOD_SQL = (
    "SELECT snapshot_month, SUM(PRINCIPAL_OS) AS pos FROM main "
    "WHERE {ACCESS_SCOPE_FILTER} GROUP BY snapshot_month ORDER BY snapshot_month"
)
# The exact shape that broke in production: time_grain used as a value.
BAD_SQL = (
    "SELECT CAST('month' AS DATE) AS month, SUM(PRINCIPAL_OS) AS pos "
    "FROM main WHERE {ACCESS_SCOPE_FILTER} GROUP BY 1"
)


def _run(sql_responses: list[str]):
    """Serves each sql_generator call the next response in the list."""
    remaining = list(sql_responses)
    calls: list[str] = []

    def fake_call_stage(stage, system_prompt, user_content, temperature=0.0, max_tokens=1024):
        calls.append(user_content if stage == "sql_generator" else stage)
        if stage == "router":
            return json.dumps(ROUTER_JSON)
        if stage == "sql_generator":
            return remaining.pop(0)
        if stage == "analyst":
            return "- Notable."
        return "Answer."

    with patch("app.graph.nodes.call_stage", side_effect=fake_call_stage):
        result = build_graph().invoke({
            "question": "trend of POS",
            "session_id": "repair",
            "access_scope": AccessScope(employee_id="E1", role="admin"),
        })
    return result, calls


def test_a_failing_query_is_repaired_and_the_turn_succeeds():
    result, calls = _run([BAD_SQL, GOOD_SQL])

    assert result["error"] is None
    assert result["query_result"] is not None and not result["query_result"].empty
    assert result["sql_repair_attempts"] == 1
    assert "repair_sql" in result["tool_sequence"]


def test_the_repair_prompt_carries_the_failed_sql_and_the_engine_error():
    _, calls = _run([BAD_SQL, GOOD_SQL])
    # calls[0] is the router; the two sql_generator prompts follow.
    repair_context = calls[2]

    assert "CAST('month' AS DATE)" in repair_context
    assert "FAILED" in repair_context
    # The engine's own words, not a generic "something went wrong".
    assert "Error" in repair_context


def test_a_query_that_fails_twice_ends_in_a_readable_message_not_a_traceback():
    result, _ = _run([BAD_SQL, BAD_SQL])

    assert result["error"]
    assert result["sql_repair_attempts"] == 1  # one repair, then it stops
    assert result["narration"].startswith("I couldn't answer that.")
    assert result.get("query_result") is None or result["query_result"].empty


def test_only_one_repair_is_attempted():
    """Three bad statements must not mean three extra model calls — the
    attempt cap is what keeps a broken model from looping on free quota."""
    remaining = [BAD_SQL, BAD_SQL, BAD_SQL]
    sql_calls = 0

    def fake_call_stage(stage, system_prompt, user_content, temperature=0.0, max_tokens=1024):
        nonlocal sql_calls
        if stage == "router":
            return json.dumps(ROUTER_JSON)
        if stage == "sql_generator":
            sql_calls += 1
            return remaining.pop(0)
        return "Answer."

    with patch("app.graph.nodes.call_stage", side_effect=fake_call_stage):
        build_graph().invoke({
            "question": "trend of POS",
            "session_id": "repair-cap",
            "access_scope": AccessScope(employee_id="E1", role="admin"),
        })

    assert sql_calls == 2


def test_a_declared_insufficient_schema_is_not_retried():
    """The model saying the schema can't answer is a correct answer, not
    a failure — retrying it only invites an invented column name."""
    refusal = '{"error": "insufficient_schema", "missing": "customer_income"}'
    result, _ = _run([refusal])

    assert result.get("sql_repair_attempts", 0) == 0
    assert "repair_sql" not in result.get("tool_sequence", [])
    assert "insufficient_schema" in result["error"]


def test_an_unreadable_response_is_retried():
    """A reasoning model cut off before its final answer produces no SQL
    at all — that is worth one more attempt."""
    reasoning_dump = "Here's a thinking process:\n1. Analyze the question. Th"
    result, _ = _run([reasoning_dump, GOOD_SQL])

    assert result["error"] is None
    assert result["sql_repair_attempts"] == 1
