from typing import (
    Annotated,
    TypedDict,
)

from dotenv import load_dotenv
from langgraph.graph.message import add_messages
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import requests
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END
import os

# 加载环境变量
load_dotenv(override=True)

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

graph_builder = StateGraph(AgentState)

# 定义工具
class WeatherQuery(BaseModel):
    loc: str = Field(description="城市名称")


@tool(args_schema=WeatherQuery)
def get_weather(loc):
    """
        查询即时天气函数
        :param loc: 必要参数，字符串类型，用于表示查询天气的具体城市名称，\
        :return：心知天气 API查询即时天气的结果，具体URL请求地址为："https://api.seniverse.com/v3/weather/now.json"
        返回结果对象类型为解析之后的JSON格式对象，并用字符串形式进行表示，其中包含了全部重要的天气信息
    """
    url = "https://api.seniverse.com/v3/weather/now.json"
    params = {
        "key": os.getenv('WEATHER_API_KEY'),
        "location": loc,
        "language": "zh-Hans",
        "unit": "c",
    }
    response = requests.get(url, params=params)
    temperature = response.json()
    return temperature['results'][0]['now']


model = ChatAnthropic(
        model_name=os.getenv('ANTHROPIC_MODEL'),
        api_key=os.getenv('ANTHROPIC_API_KEY'),
        base_url=os.getenv('ANTHROPIC_BASE_URL') or None,
    )

tools = [get_weather]
model = model.bind_tools(tools)

def call_model(
    state: AgentState,
):
    system_prompt = SystemMessage(
        "你是一个AI助手，可以依据用户提问产生回答，你还具备调用天气函数的能力"
    )
    response = model.invoke([system_prompt] + state["messages"])
    return {"messages": [response]}

tool_node = ToolNode(tools)

def should_continue(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    if not last_message.tool_calls:
        return "end"
    else:
        return "continue"

graph = StateGraph(AgentState)

graph.add_node("agent", call_model)
graph.add_node("tools", tool_node)

graph.add_edge(START, "agent")
graph.add_edge("tools", "agent")
graph.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "tools",
        "end": END,
    },
)

graph = graph.compile()

final_state = graph.invoke({"messages": ["请问上海天气如何?"]})
print(final_state['messages'])