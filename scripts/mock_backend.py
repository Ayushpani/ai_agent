"""Run the real FastAPI app with the LLM stages mocked.

Lets you exercise the full UI — including deep research — without API
keys or free-tier quota. Every non-LLM layer (SQL validation, access
scoping, DuckDB execution, the statistical tools, workbook build) runs
for real; only the model calls are replaced with canned responses.

    python scripts/mock_backend.py            # then open the web UI
    python scripts/mock_backend.py --slow     # simulate model latency

Mocked calls return instantly, which makes the whole pipeline finish in
about 0.2s — too fast to see, let alone develop against, any of the
streaming UI states. --slow adds a per-stage delay in the same ballpark
as a real free-tier call so the live step timeline behaves as it will in
production.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
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


# Roughly what each stage costs against a free-tier endpoint, so the
# streaming UI is exercised under realistic timing rather than instantly.
SLOW_STAGE_SECONDS = {
    "router": 0.9,
    "sql_generator": 2.4,
    "research_planner": 2.0,
    "analyst": 1.8,
    "synthesis": 2.6,
    "narrator": 1.6,
}


def build_fake_call_stage(slow: bool):
    def fake_call_stage(stage, system_prompt, user_content, temperature=0.0, max_tokens=1024):
        if slow:
            time.sleep(SLOW_STAGE_SECONDS.get(stage, 1.0))
        return RESPONSES[stage]

    return fake_call_stage


def preflight() -> list[str]:
    """Warn about the one thing that makes this server start fine and then
    fail every question: no ingested snapshots to query."""
    from app.tools.data import curated_root

    root = curated_root()
    partitions = sorted(root.glob("snapshot_month=*")) if root.exists() else []
    if partitions:
        return [f"Data:     {len(partitions)} monthly snapshots in {root}"]
    return [
        f"Data:     NONE FOUND in {root}",
        "          Queries will fail until you seed it:",
        "            python scripts/seed_synthetic_data.py",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slow", action="store_true", help="Simulate free-tier model latency.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    lines = [
        "",
        "  Portfolio Intelligence Agent — mock backend",
        "",
        f"  API:      http://localhost:{args.port}",
        "  Models:   mocked (no API keys, no free-tier quota used)",
        f"  Latency:  {'simulated per stage' if args.slow else 'none — pass --slow to see streaming states'}",
    ]
    lines += [f"  {line}" for line in preflight()]
    lines += [
        "",
        "  Start the web UI in another terminal:",
        "    cd web && npm run dev",
        "",
        "  Ctrl+C to stop.",
        "",
    ]
    # uvicorn runs at log_level=warning to keep per-request noise down,
    # which also suppresses its own "Uvicorn running on ..." banner — so
    # without this the server starts and prints nothing at all, which
    # reads exactly like a hang.
    print("\n".join(lines), flush=True)

    fake_call_stage = build_fake_call_stage(args.slow)

    with (
        patch("app.graph.nodes.call_stage", side_effect=fake_call_stage),
        patch("app.graph.research_nodes.call_stage", side_effect=fake_call_stage),
    ):
        uvicorn.run("app.api.main:app", host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
