from typing import Annotated

from dotenv import load_dotenv
from typing_extensions import TypedDict
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.constants import START
from langchain_anthropic import ChatAnthropic
import os

# 加载环境变量
load_dotenv(override=True)

class State(TypedDict):
    messages: Annotated[list, add_messages]

graph_builder = StateGraph(State)

model_name = os.getenv('ANTHROPIC_MODEL')
api_key = os.getenv('ANTHROPIC_API_KEY')
base_url = os.getenv('ANTHROPIC_BASE_URL') or None

model = ChatAnthropic(
        model_name=os.getenv('ANTHROPIC_MODEL'),
        api_key=os.getenv('ANTHROPIC_API_KEY'),
        base_url=os.getenv('ANTHROPIC_BASE_URL') or None,
    )

def chatbot(state: State):
    return {"messages": [model.invoke(state["messages"])]}

# 添加节点
graph_builder.add_node("chatbot", chatbot)

# 添加边
graph_builder.add_edge(START, "chatbot")

graph = graph_builder.compile()



messages_list = [
    HumanMessage(content="你好，我叫大模型真好玩，好久不见。"),
    AIMessage(content="你好呀！我是苍老师，是一名女演员。很高兴认识你！"),
    HumanMessage(content="请问，你还记得我叫什么名字么？"),
]
final_state = graph.invoke({"messages": messages_list})
print(final_state['messages'])