"""The agent's LangGraph workflow.

::

    parse_spec ──(valid)──▶ plan_tests ─▶ generate_tests ─▶ execute_tests
        │                                                        │
        └──(invalid)──▶ explain_error ─▶ END          validate ◀─┘
                                                          │
                                                   build_report ─▶ END

State is the typed :class:`~app.models.state.AgentState` Pydantic model.
The parse step has a conditional edge: on spec errors the run is routed to
an error-explanation node instead of continuing.
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.models.state import AgentState
from app.nodes.error_explainer import explain_error_node
from app.nodes.executor import execute_tests_node
from app.nodes.reporter import build_report_node
from app.nodes.spec_parser import parse_spec_node
from app.nodes.test_generator import generate_tests_node
from app.nodes.test_planner import plan_tests_node
from app.nodes.validator import validate_node


def route_after_parse(state: AgentState) -> Literal["plan_tests", "explain_error"]:
    """Conditional edge: continue only if the spec parsed cleanly."""
    return "explain_error" if state.spec_error else "plan_tests"


def build_workflow() -> CompiledStateGraph:
    """Assemble and compile the agent's StateGraph."""
    graph = StateGraph(AgentState)

    graph.add_node("parse_spec", parse_spec_node)
    graph.add_node("plan_tests", plan_tests_node)
    graph.add_node("generate_tests", generate_tests_node)
    graph.add_node("execute_tests", execute_tests_node)
    graph.add_node("validate", validate_node)
    graph.add_node("build_report", build_report_node)
    graph.add_node("explain_error", explain_error_node)

    graph.set_entry_point("parse_spec")
    graph.add_conditional_edges(
        "parse_spec",
        route_after_parse,
        {"plan_tests": "plan_tests", "explain_error": "explain_error"},
    )
    graph.add_edge("plan_tests", "generate_tests")
    graph.add_edge("generate_tests", "execute_tests")
    graph.add_edge("execute_tests", "validate")
    graph.add_edge("validate", "build_report")
    graph.add_edge("build_report", END)
    graph.add_edge("explain_error", END)

    return graph.compile()


def run_workflow(state: AgentState) -> AgentState:
    """Invoke the compiled workflow and return the final state."""
    final = build_workflow().invoke(state)
    return AgentState.model_validate(final)
