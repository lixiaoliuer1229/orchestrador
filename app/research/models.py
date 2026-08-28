"""Research-domain data contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(StrEnum):
    WEB = "web"
    FILING = "filing"
    NEWS = "news"
    REPORT = "report"
    DATASET = "dataset"


class ClaimType(StrEnum):
    FACT = "fact"
    DERIVED = "derived"
    ESTIMATE = "estimate"
    OPINION = "opinion"
    FORECAST = "forecast"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONFLICTING = "conflicting"
    UNSUPPORTED = "unsupported"
    STALE = "stale"


class SearchItem(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    reason: str = Field(min_length=2, max_length=500)
    topic: Literal["general", "news", "finance"] = "general"


class SearchPlan(BaseModel):
    searches: list[SearchItem] = Field(min_length=1, max_length=7)


class SourceDocument(BaseModel):
    source_id: str
    canonical_url: HttpUrl
    title: str
    publisher: str | None = None
    source_type: SourceType = SourceType.WEB
    published_at: datetime | None = None
    retrieved_at: datetime
    content: str
    content_hash: str
    language: str | None = None
    market: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    queries: list[str] = Field(default_factory=list)
    score: float | None = None


class SearchFailure(BaseModel):
    query: str
    error: str


class EvidenceDraft(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    source_id: str
    excerpt: str = Field(min_length=1, max_length=4_000)
    normalized_value: str | None = None
    unit: str | None = None
    currency: str | None = None
    data_period: str | None = None
    confidence: float = Field(ge=0, le=1)
    location: dict[str, Any] = Field(default_factory=dict)


class ClaimDraft(BaseModel):
    statement: str = Field(min_length=1, max_length=4_000)
    claim_type: ClaimType
    evidence_keys: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class Extraction(BaseModel):
    evidence: list[EvidenceDraft] = Field(default_factory=list, max_length=100)
    claims: list[ClaimDraft] = Field(default_factory=list, max_length=100)


class Evidence(BaseModel):
    evidence_id: str
    run_id: str
    source_id: str
    excerpt: str
    normalized_value: str | None = None
    unit: str | None = None
    currency: str | None = None
    data_period: str | None = None
    extraction_method: str = "llm_verified_excerpt"
    confidence: float = Field(ge=0, le=1)
    location: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    claim_id: str
    run_id: str
    statement: str
    claim_type: ClaimType
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    verification_status: VerificationStatus
    invalidation_reason: str | None = None


class Report(BaseModel):
    short_summary: str
    markdown_report: str
    follow_up_questions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)


class ResearchRun(BaseModel):
    run_id: str
    query: str
    graph_version: str
    model: str
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime
    completed_at: datetime | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    plan: SearchPlan | None = None
    report: Report | None = None
    failures: list[SearchFailure] = Field(default_factory=list)
    error: str | None = None


class RunDetail(BaseModel):
    run: ResearchRun
    sources: list[SourceDocument] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
