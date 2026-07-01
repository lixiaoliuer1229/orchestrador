"""The smallest possible LangGraph — useful as a smoke test."""
from langgraph.graph import END, StateGraph

from src.graphs.state_schema import BaseAgentState
from src.utils.llm import get_anthropic_llm
from src.utils.logger import logger


def call_llm(state: BaseAgentState) -> BaseAgentState:
    """Single LLM node — echoes the latest user message with a friendly reply."""
    messages = state.get("messages", [])
    llm = get_anthropic_llm()
    response = llm.invoke(messages)
    logger.info("hello_graph produced a response")
    return {
        "messages": [response],
        "turn_count": state.get("turn_count", 0) + 1,
    }


def build_hello_graph():
    """Build and compile the minimal graph."""
    graph = StateGraph(BaseAgentState)
    graph.add_node("chatbot", call_llm)
    graph.set_entry_point("chatbot")
    graph.add_edge("chatbot", END)
    return graph.compile()


hello_graph = build_hello_graph()