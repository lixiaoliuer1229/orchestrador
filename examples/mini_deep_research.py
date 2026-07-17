"""A minimal, standalone model setup for learning purposes."""
import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

load_dotenv(override=True)

anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL")
anthropic_model = os.getenv("ANTHROPIC_MODEL")


if not anthropic_api_key:
    raise ValueError("ANTHROPIC_API_KEY is not set. Add it to the project's .env file.")

model = ChatAnthropic(
    model=anthropic_model,
    api_key=anthropic_api_key,
    base_url=anthropic_base_url or None,
)

PLANNER_INSTRUCTIONS = (
    "You are a helpful research assistant, Given a query, come up with a set of web searches "
    "to perform to best answer the query, Output between 5 and 7 terms to query for."
)

planner_prompt = ChatPromptTemplate.from_messages([
    ("system", PLANNER_INSTRUCTIONS),
    ("human",  "{query}")
])

class WebSearchItem(BaseModel):
    query: str
    "The search term to use for the web search."
    "用于网络搜索的关键词"

    reason: str
    "You reasoning for why this search is important to the query."
    "为什么这个搜索对于解答该问题很重要的理由"

class WebSearchPlan(BaseModel):
    searches: list[WebSearchItem]
    "A list of web searches to perform to best answer the query"
    "为了尽可能全面回答该问题而需要执行的网页搜索列表"
