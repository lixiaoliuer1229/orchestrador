"""LangGraph state for the research workflow."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.graphs.research.models import Report, SearchFailure, SearchPlan, Source


class ResearchState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    query: str
    plan: SearchPlan
    sources: list[Source]
    failures: list[SearchFailure]
    report: Report
