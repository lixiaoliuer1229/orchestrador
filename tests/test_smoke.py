"""Smoke tests that don't require live LLM keys."""
from src.graphs.state_schema import BaseAgentState
from src.graphs.hello_graph import build_hello_graph
from src.tools.example_tools import add_numbers, get_current_time


def test_state_schema_accepts_partial_input() -> None:
    state: BaseAgentState = {"messages": [], "turn_count": 0}
    assert state["turn_count"] == 0


def test_hello_graph_compiles() -> None:
    graph = build_hello_graph()
    assert graph is not None


def test_add_numbers_tool() -> None:
    assert add_numbers.invoke({"a": 2, "b": 3}) == 5


def test_get_current_time_tool() -> None:
    iso = get_current_time.invoke({})
    assert "T" in iso