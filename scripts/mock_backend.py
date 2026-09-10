"""Run the real FastAPI app with the LLM stages mocked.

Lets you exercise the full UI — including deep research — without API
keys or free-tier quota. Every non-LLM layer (SQL validation, access
scoping, DuckDB execution, the statistical tools, workbook build) runs
for real; only the four model calls are replaced with canned responses.

    python scripts/mock_backend.py            # then open the web UI
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

ROUTER = {
    "intent": "trend", "requires_chart": True, "requires_forecast": False,
    "time_grain": "month", "entities": ["AUM", "STATE"],
    "ambiguous_aggregation_level": False, "ambiguity_reason": None,
}

SQL = (
    "SELECT snapshot_month, SUM(AUM_90PLUS_FINANCE_OWNSHARE) AS finance_ownshare_90plus_aum "
    "FROM main WHERE STATE='Maharashtra' AND {ACCESS_SCOPE_FILTER} "
    "GROUP BY snapshot_month ORDER BY snapshot_month"
)

PLAN = {
    "should_go_deeper": True,
    "reasoning": "The headline trend does not show whether the movement is broad-based or concentrated.",
    "probes": [
        {"probe_type": "decompose_by", "title": "Exposure by branch", "rationale": "Establishes whether the latest position sits with a few branches or is spread across the network.", "metric": "AUM_90PLUS_LAN", "dimension": "BRANCH_NAME", "top_n": 6},
        {"probe_type": "trend_by_segment", "title": "Regional trends", "rationale": "Shows whether regions moved together or offset each other over the window.", "metric": "PRINCIPAL_OS", "dimension": "REGION", "top_n": 4},
        {"probe_type": "period_comparison", "title": "Product shift", "rationale": "Compares first and latest month by product to locate what actually changed.", "metric": "PRINCIPAL_OS", "dimension": "PRODUCT", "top_n": 5},
        {"probe_type": "related_metric", "title": "30+ context", "rationale": "Places the headline alongside an earlier-stage delinquency measure.", "metric": "AUM_30PLUS_LAN"},
    ],
}

SYNTHESIS = (
    "- 90+ own-share AUM in Maharashtra moved +8.4% over the window, a z-score of 1.8 which is "
    "notable but short of extreme.\n"
    "- The branch breakdown shows exposure is not broad-based: the top branch alone carries a "
    "fifth of the shown total, with a concentration index of 0.20.\n"
    "- Regional trends and the product comparison point the same direction, so the movement is a "
    "continuation rather than a reversal.\n"
    "- The 30+ series does not show a matching build-up, which argues the 90+ move is ageing of "
    "existing delinquency rather than fresh inflow.\n"
    "- Worth asking: is the leading branch's concentration a book-mix artefact or a collections gap?"
)

NARRATION = (
    "Finance-level, own-share 90+ AUM in Maharashtra rose 8.4% over the last six months. At a "
    "z-score of 1.8 that is a notable move rather than an extreme one, and the direction is "
    "consistent across the period.\n\n"
    "The branch breakdown argues against reading this as broad-based deterioration: the largest "
    "branch alone accounts for roughly a fifth of the shown exposure, and the concentration index "
    "of 0.20 puts most of the movement in a handful of names. The regional and product views point "
    "the same way, so this looks like a continuation of an existing trend rather than a turn.\n\n"
    "The 30+ series shows no matching build-up, which suggests ageing of existing delinquency "
    "rather than fresh inflow. The question that follows is whether the leading branch reflects "
    "book mix or a collections gap."
)

RESPONSES = {
    "router": json.dumps(ROUTER),
    "sql_generator": SQL,
    "research_planner": json.dumps(PLAN),
    "analyst": "- The series moved +8.4% with a z-score of 1.8.\n- No data-quality flags were raised.",
    "synthesis": SYNTHESIS,
    "narrator": NARRATION,
}


def fake_call_stage(stage, system_prompt, user_content, temperature=0.0, max_tokens=1024):
    return RESPONSES[stage]


if __name__ == "__main__":
    with (
        patch("app.graph.nodes.call_stage", side_effect=fake_call_stage),
        patch("app.graph.research_nodes.call_stage", side_effect=fake_call_stage),
    ):
        uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, log_level="warning")
