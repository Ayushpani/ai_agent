"""End-to-end golden-question suite (doc §13.3 tests/integration/) run
against the graph with the LLM stages mocked out — this exercises the
real deterministic path (ingestion -> DuckDB -> tools -> chart) without
depending on live free-tier LLM availability in CI.
"""
import json
from unittest.mock import patch

import pytest

from app.graph.build import build_graph
from app.models.schemas import AccessScope, ChartType


def _mock_responses(router_json: dict, sql: str, analyst: str = "- Notable.", narration: str = "Answer."):
    def fake_call_stage(stage, system_prompt, user_content, temperature=0.0, max_tokens=1024):
        return {
            "router": json.dumps(router_json),
            "sql_generator": sql,
            "analyst": analyst,
            "narrator": narration,
        }[stage]
    return fake_call_stage


def test_trend_question_end_to_end():
    router_json = {
        "intent": "trend", "requires_chart": True, "requires_forecast": False,
        "time_grain": "month", "entities": ["STATE"],
        "ambiguous_aggregation_level": False, "ambiguity_reason": None,
    }
    sql = ("SELECT snapshot_month, SUM(PRINCIPAL_OS) AS pos FROM main "
           "WHERE STATE='Maharashtra' AND {ACCESS_SCOPE_FILTER} "
           "GROUP BY snapshot_month ORDER BY snapshot_month")

    with patch("app.graph.nodes.call_stage", side_effect=_mock_responses(router_json, sql)):
        graph = build_graph()
        result = graph.invoke({
            "question": "trend of POS in Maharashtra",
            "session_id": "s1",
            "access_scope": AccessScope(employee_id="E1", role="admin"),
        })

    assert result["error"] is None
    assert result["chart_spec"].chart_type == ChartType.line
    assert result["signals"].period_change is not None
    assert result["narration"]


def test_forced_disambiguation_short_circuits_before_sql():
    router_json = {
        "intent": "aggregation", "requires_chart": False, "requires_forecast": False,
        "time_grain": "none", "entities": ["AUM"],
        "ambiguous_aggregation_level": True, "ambiguity_reason": "AUM level not stated",
    }

    def fake_call_stage(stage, *a, **kw):
        if stage != "router":
            pytest.fail(f"stage '{stage}' must not run when disambiguation is required")
        return json.dumps(router_json)

    with patch("app.graph.nodes.call_stage", side_effect=fake_call_stage):
        graph = build_graph()
        result = graph.invoke({
            "question": "our 90+ AUM in Maharashtra",
            "session_id": "s2",
            "access_scope": AccessScope(employee_id="E1", role="admin"),
        })

    assert "LAN" in result["narration"] and "UCIC" in result["narration"]


def test_region_manager_scope_restricts_rows():
    """A regional manager's query is scoped to their region regardless of
    what the LLM produced (doc §9.2)."""
    router_json = {
        "intent": "aggregation", "requires_chart": False, "requires_forecast": False,
        "time_grain": "none", "entities": [],
        "ambiguous_aggregation_level": False, "ambiguity_reason": None,
    }
    # Deliberately un-scoped by state — the LLM "forgot" to filter by region.
    sql = "SELECT REGION, SUM(PRINCIPAL_OS) AS pos FROM main WHERE {ACCESS_SCOPE_FILTER} GROUP BY REGION"

    with patch("app.graph.nodes.call_stage", side_effect=_mock_responses(router_json, sql)):
        graph = build_graph()
        result = graph.invoke({
            "question": "POS by region",
            "session_id": "s3",
            "access_scope": AccessScope(employee_id="E1", role="region_manager", employee_region="North"),
        })

    assert result["error"] is None
    regions = set(result["query_result"]["REGION"])
    assert regions == {"North"}


def test_lookup_intent_skips_analyst_step():
    router_json = {
        "intent": "lookup", "requires_chart": False, "requires_forecast": False,
        "time_grain": "none", "entities": [],
        "ambiguous_aggregation_level": False, "ambiguity_reason": None,
    }
    sql = "SELECT COUNT(*) AS n FROM main WHERE {ACCESS_SCOPE_FILTER}"

    calls = []

    def fake_call_stage(stage, *a, **kw):
        calls.append(stage)
        return _mock_responses(router_json, sql)(stage, *a, **kw)

    with patch("app.graph.nodes.call_stage", side_effect=fake_call_stage):
        graph = build_graph()
        graph.invoke({
            "question": "how many active loans",
            "session_id": "s4",
            "access_scope": AccessScope(employee_id="E1", role="admin"),
        })

    assert "analyst" not in calls
