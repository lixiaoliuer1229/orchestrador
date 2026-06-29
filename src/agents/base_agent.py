"""Reusable ReAct-style agent factory."""
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.graphs.state_schema import BaseAgentState
from src.tools.example_tools import DEFAULT_TOOLS
from src.utils.llm import get_openai_llm


def should_continue(state: BaseAgentState) -> str:
    """If the last message has tool calls, route to tools; otherwise end."""
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


def build_react_agent(tools=None, llm=None):
    """Construct a ReAct agent graph (model -> tools -> model -> ...)."""
    tools = tools or DEFAULT_TOOLS
    llm = llm or get_openai_llm()
    model_with_tools = llm.bind_tools(tools)

    def call_model(state: BaseAgentState) -> BaseAgentState:
        response = model_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(BaseAgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")
    return graph.compile()


__all__ = ["build_react_agent"]