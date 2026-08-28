"""LangGraph state for the research workflow."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.research.models import (
    Claim,
    Evidence,
    Report,
    SearchFailure,
    SearchPlan,
    SourceDocument,
)


class ResearchState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    query: str
    run_id: str
    plan: SearchPlan
    sources: list[SourceDocument]
    failures: list[SearchFailure]
    evidence: list[Evidence]
    claims: list[Claim]
    report: Report
