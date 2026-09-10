"""LangGraph state — an explicit, typed record of everything a request
accumulates as it flows through the graph (doc §4: 'auditable, testable,
no free-form autonomy'). Every field here is either LLM-produced-and-
validated, or deterministic-tool output.
"""
from __future__ import annotations

from typing import Any, TypedDict

import pandas as pd

from app.models.schemas import (
    AccessScope,
    AnalysisPanel,
    AnalystOutput,
    ChartSpec,
    ResearchDepth,
    ResearchPlan,
    RouterOutput,
    SignalsPackage,
    SQLGeneratorOutput,
)


class GraphState(TypedDict, total=False):
    # Request context
    question: str
    session_id: str
    access_scope: AccessScope
    research_depth: ResearchDepth

    # Reasoning layer outputs
    router_output: RouterOutput
    needs_disambiguation: bool
    disambiguation_message: str
    sql_output: SQLGeneratorOutput
    final_sql: str
    # Set when a generated statement failed validation or execution, and
    # fed back to the generator by repair_sql_node. Counted so a model
    # that cannot fix itself fails the turn instead of looping.
    sql_error_detail: str
    sql_repair_attempts: int

    # Query execution
    query_result: pd.DataFrame

    # Tool layer outputs
    signals: SignalsPackage
    analyst_output: AnalystOutput
    narration: str
    chart_spec: ChartSpec

    # Deep-research layer
    research_plan: ResearchPlan
    panels: list[AnalysisPanel]

    # Audit
    tool_sequence: list[str]
    model_ids_used: dict[str, str]
    latency_ms_per_stage: dict[str, float]
    error: str | None
    workbook_bytes: bytes | None
    extra: dict[str, Any]
