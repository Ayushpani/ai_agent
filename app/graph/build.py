"""LangGraph state machine wiring (doc §3.1, §3.2): Router -> SQL
Generator -> Validate/Execute -> Tools -> Analyst -> Narrator -> Chart.
Explicit graph of nodes/edges — auditable, testable, no free-form
autonomy: the LLM never decides what happens next, the graph does.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.nodes import (
    analyst_node,
    chart_node,
    execute_query_node,
    narrator_node,
    router_node,
    sql_generator_node,
    tools_node,
)
from app.graph.state import GraphState


def _after_router(state: GraphState) -> str:
    if state.get("needs_disambiguation"):
        return "disambiguate"
    return "generate_sql"


def _after_execute(state: GraphState) -> str:
    if state.get("error"):
        return "handled_error"
    return "run_tools"


def _disambiguate_node(state: GraphState) -> dict:
    return {"narration": state["disambiguation_message"]}


def _error_node(state: GraphState) -> dict:
    return {"narration": f"I couldn't answer that: {state['error']}"}


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("route", router_node)
    graph.add_node("disambiguate", _disambiguate_node)
    graph.add_node("generate_sql", sql_generator_node)
    graph.add_node("execute", execute_query_node)
    graph.add_node("handled_error", _error_node)
    graph.add_node("run_tools", tools_node)
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
        "run_tools": "run_tools",
    })
    graph.add_edge("handled_error", END)
    graph.add_edge("run_tools", "analyze")
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
