"""Production conversational agent without external action tools."""

from langchain.agents import create_agent

from app.model_config import create_chat_model


TOOLS = []


def create_graph(model_name: str | None = None):
    return create_agent(model=create_chat_model(model_name), tools=TOOLS)


graph = create_graph()
