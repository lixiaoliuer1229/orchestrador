"""Production conversational agent."""

import os

import requests
from langchain.agents import create_agent
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.model_config import create_chat_model


class WeatherQuery(BaseModel):
    location: str = Field(min_length=1, max_length=100, description="城市名称")


@tool(args_schema=WeatherQuery)
def get_weather(location: str) -> dict:
    """查询指定城市的即时天气。"""

    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        return {"error": "weather_not_configured"}
    response = requests.get(
        "https://api.seniverse.com/v3/weather/now.json",
        params={
            "key": api_key,
            "location": location,
            "language": "zh-Hans",
            "unit": "c",
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["results"][0]["now"]


TOOLS = [get_weather]


def create_graph(model_name: str | None = None):
    return create_agent(model=create_chat_model(model_name), tools=TOOLS)


graph = create_graph()
