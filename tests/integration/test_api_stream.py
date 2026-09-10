"""Covers the SSE endpoint the Next.js frontend depends on: every stage
event and the final payload must be plain-JSON-serializable (DataFrames
and pydantic models don't survive `json.dumps` on their own), and the
download endpoint must pick up the session populated by streaming, not
just by the synchronous /ask.
"""
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

_ROUTER_JSON = {
    "intent": "trend", "requires_chart": True, "requires_forecast": False,
    "time_grain": "month", "entities": ["STATE"],
    "ambiguous_aggregation_level": False, "ambiguity_reason": None,
}
_SQL = (
    "SELECT snapshot_month, SUM(PRINCIPAL_OS) AS pos FROM main "
    "WHERE STATE='Maharashtra' AND {ACCESS_SCOPE_FILTER} "
    "GROUP BY snapshot_month ORDER BY snapshot_month"
)


def _fake_call_stage(stage, *a, **kw):
    return {
        "router": json.dumps(_ROUTER_JSON),
        "sql_generator": _SQL,
        "analyst": "- POS trending up.",
        "narrator": "POS has grown steadily.",
    }[stage]


def test_stream_endpoint_emits_ordered_stage_events_and_final_payload():
    with patch("app.graph.nodes.call_stage", side_effect=_fake_call_stage):
        with client.stream("POST", "/ask/stream", json={
            "session_id": "test-stream-1",
            "question": "trend of POS in Maharashtra",
            "identity": {"employee_id": "EMP1", "role": "admin"},
        }) as r:
            assert r.status_code == 200
            events = []
            for line in r.iter_lines():
                if line and line.startswith("data: "):
                    events.append(json.loads(line[len("data: "):]))

    stage_starts = [e["stage"] for e in events if e["kind"] == "stage_start"]
    assert stage_starts == ["route", "generate_sql", "execute", "run_tools", "analyze", "narrate", "chart"]

    final_events = [e for e in events if e["kind"] == "final"]
    assert len(final_events) == 1
    result = final_events[0]["result"]
    assert result["narration"] == "POS has grown steadily."
    assert result["chart_spec"]["chart_type"] == "line"
    assert result["error"] is None


def test_stream_populates_session_for_download_endpoint():
    with patch("app.graph.nodes.call_stage", side_effect=_fake_call_stage):
        with client.stream("POST", "/ask/stream", json={
            "session_id": "test-stream-2",
            "question": "trend of POS in Maharashtra",
            "identity": {"employee_id": "EMP1", "role": "admin"},
        }) as r:
            for _ in r.iter_lines():
                pass

    download = client.get("/download/test-stream-2")
    assert download.status_code == 200
    assert len(download.content) > 0
