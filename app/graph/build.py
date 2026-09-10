"""LangGraph state machine wiring (doc §3.1, §3.2), extended with the
deep-research branch.

Standard depth:
    Router -> SQL Generator -> Execute -> Tools -> Analyst -> Narrator -> Chart

A statement that fails validation or execution goes Execute -> Repair SQL
-> Execute once, with the engine's error handed back to the generator,
before the turn is failed with a readable message.

Deep depth adds a planned investigation round between the tools and the
write-up:
    ... -> Tools -> Plan research -> Run probes -> Synthesise -> Narrator -> Chart

Explicit graph of nodes/edges either way — auditable, testable, no
free-form autonomy. The LLM proposes which probes are worth running; it
never decides what happens next, the graph does, and it never writes the
probe SQL (see app/tools/probes.py for why).
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.nodes import (
    MAX_SQL_REPAIR_ATTEMPTS,
    analyst_node,
    chart_node,
    execute_query_node,
    narrator_node,
    repair_sql_node,
    router_node,
    sql_generator_node,
    tools_node,
)
from app.graph.research_nodes import (
    plan_research_node,
    run_probes_node,
    should_go_deep,
    synthesis_node,
)
from app.graph.state import GraphState


def _after_router(state: GraphState) -> str:
    if state.get("needs_disambiguation"):
        return "disambiguate"
    return "generate_sql"


def _after_execute(state: GraphState) -> str:
    if not state.get("error"):
        return "run_tools"
    # sql_error_detail is set only for failures a second attempt could
    # plausibly fix (engine/validator errors, an unreadable response) —
    # not for the model correctly declaring the schema can't answer.
    if state.get("sql_error_detail") and (
        state.get("sql_repair_attempts", 0) < MAX_SQL_REPAIR_ATTEMPTS
    ):
        return "repair_sql"
    return "handled_error"


def _after_tools(state: GraphState) -> str:
    return "plan_research" if should_go_deep(state) else "analyze"


def _after_plan(state: GraphState) -> str:
    plan = state.get("research_plan")
    if plan is not None and plan.should_go_deeper and plan.probes:
        return "run_probes"
    # The planner declined to deepen — fall back to the single-result
    # analyst rather than synthesising over an empty panel set.
    return "analyze"


def _disambiguate_node(state: GraphState) -> dict:
    return {"narration": state["disambiguation_message"]}


def _error_node(state: GraphState) -> dict:
    """Terminal, readable failure. The raw engine/validator text is kept
    (it is what makes a failure diagnosable in the audit log and on
    screen) but framed so a business user knows whether to rephrase or
    to escalate, rather than being handed a bare DuckDB exception.
    """
    detail = state.get("error") or "unknown error"
    if detail.startswith("needs_disambiguation"):
        lead = "I need one more detail before I can answer that."
    elif detail.startswith("insufficient_schema"):
        lead = (
            "I couldn't answer that from the columns available to you. "
            "The portfolio extract doesn't carry what the question needs:"
        )
    else:
        lead = (
            "I couldn't answer that. I wrote a query for it, and it failed "
            "twice against the data, so I'd rather stop than show you a "
            "number I can't stand behind. Try naming the metric and period "
            "more explicitly. Technical detail:"
        )
    return {"narration": f"{lead} {detail}".strip()}


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("route", router_node)
    graph.add_node("disambiguate", _disambiguate_node)
    graph.add_node("generate_sql", sql_generator_node)
    graph.add_node("execute", execute_query_node)
    graph.add_node("repair_sql", repair_sql_node)
    graph.add_node("handled_error", _error_node)
    graph.add_node("run_tools", tools_node)
    graph.add_node("plan_research", plan_research_node)
    graph.add_node("run_probes", run_probes_node)
    graph.add_node("synthesize", synthesis_node)
    graph.add_node("analyze", analyst_node)
    graph.add_node("narrate", narrator_node)
    graph.add_node("chart", chart_node)

    graph.set_entry_point("route")
    graph.add_conditional_edges("route", _after_router, {
        "disambiguate": "disambiguate",
        "generate_sql": "generate_sql",
    })
    graph.add_edge("disambiguate", END)
    graph.add_edge("generate_sql", "execute")
    graph.add_conditional_edges("execute", _after_execute, {
        "handled_error": "handled_error",
        "repair_sql": "repair_sql",
        "run_tools": "run_tools",
    })
    graph.add_edge("repair_sql", "execute")
    graph.add_edge("handled_error", END)

    graph.add_conditional_edges("run_tools", _after_tools, {
        "plan_research": "plan_research",
        "analyze": "analyze",
    })
    graph.add_conditional_edges("plan_research", _after_plan, {
        "run_probes": "run_probes",
        "analyze": "analyze",
    })
    graph.add_edge("run_probes", "synthesize")
    graph.add_edge("synthesize", "narrate")
    graph.add_edge("analyze", "narrate")
    graph.add_edge("narrate", "chart")
    graph.add_edge("chart", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
