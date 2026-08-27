"""Structured inputs and outputs for web research."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class SearchItem(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    reason: str = Field(min_length=2, max_length=500)
    topic: Literal["general", "news", "finance"] = "general"


class SearchPlan(BaseModel):
    searches: list[SearchItem] = Field(min_length=1, max_length=7)


class Source(BaseModel):
    source_id: str
    query: str
    title: str
    url: HttpUrl
    content: str
    score: float | None = None
    retrieved_at: datetime


class SearchFailure(BaseModel):
    query: str
    error: str


class Report(BaseModel):
    short_summary: str
    markdown_report: str
    follow_up_questions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
