"""00_quickstart — drop into Jupyter with: %run examples/00_quickstart.py"""
from langchain_core.messages import HumanMessage

from src.graphs.hello_graph import hello_graph

state = {"messages": [HumanMessage(content="Hello, LangGraph!")], "turn_count": 0}
result = hello_graph.invoke(state)
print(result["messages"][-1].content)