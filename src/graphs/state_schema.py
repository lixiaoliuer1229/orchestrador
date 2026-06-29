"""Shared state schemas used across graphs."""
from operator import add
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage


class BaseAgentState(TypedDict, total=False):
    """The minimal state every agent graph should expose.

    - messages: full message history, appended via the `add` reducer.
    - turn_count: monotonically increasing integer (useful for loop guards).
    """

    messages: Annotated[Sequence[BaseMessage], add]
    turn_count: int


class ResearchState(BaseAgentState, total=False):
    """State used by the research-agent example."""

    question: str
    plan: str
    sources: Annotated[list[str], add]
    final_answer: str