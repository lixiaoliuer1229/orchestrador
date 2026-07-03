"""Run the smallest LangGraph end-to-end."""
from langchain_core.messages import HumanMessage

from src.graphs.hello_graph import hello_graph  # noqa: E402

def main() -> None:

    state = {"messages": [HumanMessage(content="用一句话介绍你自己。")], "turn_count": 0}
    result = hello_graph.invoke(state)
    print("🤖", result["messages"][-1].content)


if __name__ == "__main__":
    main()