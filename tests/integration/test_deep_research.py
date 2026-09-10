"""End-to-end coverage of the deep-research branch: the planner's probes
actually execute, panels carry real measured signals, and the depth
switch genuinely changes the graph's path.
"""
import json
from unittest.mock import patch

import pytest

from app.graph.run_request import handle_question
from app.models.schemas import ResearchDepth

_ROUTER = {
    "intent": "trend", "requires_chart": True, "requires_forecast": False,
    "time_grain": "month", "entities": ["STATE"],
    "ambiguous_aggregation_level": False, "ambiguity_reason": None,
}
_LOOKUP_ROUTER = {**_ROUTER, "intent": "lookup", "requires_chart": False}
_SQL = (
    "SELECT snapshot_month, SUM(PRINCIPAL_OS) AS pos FROM main "
    "WHERE STATE='Maharashtra' AND {ACCESS_SCOPE_FILTER} "
    "GROUP BY snapshot_month ORDER BY snapshot_month"
)
_PLAN = {
    "should_go_deeper": True,
    "reasoning": "Headline does not show attribution.",
    "probes": [
        {"probe_type": "decompose_by", "title": "By branch", "rationale": "where it sits",
         "metric": "PRINCIPAL_OS", "dimension": "BRANCH_NAME", "top_n": 5},
        {"probe_type": "trend_by_segment", "title": "Region trends", "rationale": "who moved",
         "metric": "PRINCIPAL_OS", "dimension": "REGION", "top_n": 4},
    ],
}


def _responses(plan=_PLAN, router=_ROUTER):
    return {
        "router": json.dumps(router),
        "sql_generator": _SQL,
        "research_planner": json.dumps(plan),
        "analyst": "- headline finding",
        "synthesis": "- cross-panel finding",
        "narrator": "Narrated answer.",
    }


def _run(depth, plan=_PLAN, router=_ROUTER):
    responses = _responses(plan, router)

    def fake(stage, *a, **kw):
        return responses[stage]

    with (
        patch("app.graph.nodes.call_stage", side_effect=fake),
        patch("app.graph.research_nodes.call_stage", side_effect=fake),
    ):
        return handle_question("trend of POS", "s", "EMP1", "admin", research_depth=depth)


def test_standard_depth_runs_no_probes():
    result = _run(ResearchDepth.standard)
    assert result["panels"] == []
    assert result["error"] is None
    assert result["narration"] == "Narrated answer."


def test_deep_depth_produces_populated_panels():
    result = _run(ResearchDepth.deep)
    panels = result["panels"]

    assert len(panels) == 2
    assert [p.title for p in panels] == ["By branch", "Region trends"]
    for panel in panels:
        assert panel.error is None
        assert len(panel.records) > 0
        assert panel.sql
        assert panel.signals is not None

    # Chart types come from the probe catalog, not from a model.
    assert panels[0].chart_spec.chart_type.value == "bar"
    assert panels[1].chart_spec.chart_type.value == "multi_line"


def test_panel_headline_is_computed_not_generated():
    """The panel's one-liner must be derived from its own rows, so it
    cannot drift from the numbers beside it."""
    result = _run(ResearchDepth.deep)
    branch_panel = result["panels"][0]

    assert branch_panel.headline is not None
    top_segment = branch_panel.records[0]["segment"]
    assert str(top_segment) in branch_panel.headline


def test_lookup_intent_never_goes_deep():
    """doc §7.6: forcing extra breakdowns onto a single-fact question
    manufactures insight that isn't there."""
    result = _run(ResearchDepth.deep, router=_LOOKUP_ROUTER)
    assert result["panels"] == []


def test_planner_declining_falls_back_to_headline_answer():
    declined = {"should_go_deeper": False, "reasoning": "Nothing more to add.", "probes": []}
    result = _run(ResearchDepth.deep, plan=declined)

    assert result["panels"] == []
    assert result["narration"] == "Narrated answer."
    assert result["error"] is None


def test_probe_naming_an_unknown_column_degrades_to_an_error_panel():
    """One bad probe must not sink the whole request — three good panels
    beat none."""
    plan = {
        "should_go_deeper": True,
        "reasoning": "r",
        "probes": [
            {"probe_type": "decompose_by", "title": "Good", "rationale": "r",
             "metric": "PRINCIPAL_OS", "dimension": "REGION", "top_n": 4},
            {"probe_type": "decompose_by", "title": "Hallucinated", "rationale": "r",
             "metric": "COLUMN_THAT_DOES_NOT_EXIST", "dimension": "REGION", "top_n": 4},
        ],
    }
    result = _run(ResearchDepth.deep, plan=plan)
    panels = result["panels"]

    assert len(panels) == 2
    assert panels[0].error is None and len(panels[0].records) > 0
    assert panels[1].error is not None
    assert result["narration"] == "Narrated answer."


def test_unparseable_plan_does_not_fail_the_request():
    responses = _responses()
    responses["research_planner"] = "I think we should look at branches and regions."

    def fake(stage, *a, **kw):
        return responses[stage]

    with (
        patch("app.graph.nodes.call_stage", side_effect=fake),
        patch("app.graph.research_nodes.call_stage", side_effect=fake),
    ):
        result = handle_question(
            "trend of POS", "s", "EMP1", "admin", research_depth=ResearchDepth.deep
        )

    assert result["error"] is None
    assert result["panels"] == []
    assert result["narration"] == "Narrated answer."


@pytest.mark.parametrize("role,expected_regions", [("admin", 4), ("region_manager", 1)])
def test_probe_results_are_row_scoped_to_the_caller(role, expected_regions):
    responses = _responses()

    def fake(stage, *a, **kw):
        return responses[stage]

    with (
        patch("app.graph.nodes.call_stage", side_effect=fake),
        patch("app.graph.research_nodes.call_stage", side_effect=fake),
    ):
        result = handle_question(
            "trend of POS", "s", "EMP1", role,
            employee_region="North", research_depth=ResearchDepth.deep,
        )

    trend_panel = next(p for p in result["panels"] if p.title == "Region trends")
    segments = {row["segment"] for row in trend_panel.records}
    assert len(segments) == expected_regions
