"""Cross-market instrument and investment-signal contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Market(StrEnum):
    CN = "CN"
    US = "US"


class Exchange(StrEnum):
    XSHG = "XSHG"
    XSHE = "XSHE"
    BSE = "BSE"
    XNYS = "XNYS"
    XNAS = "XNAS"
    XASE = "XASE"


class AssetType(StrEnum):
    EQUITY = "equity"


class Currency(StrEnum):
    CNY = "CNY"
    USD = "USD"


class SignalCategory(StrEnum):
    QUALITY = "quality"
    GROWTH = "growth"
    VALUATION = "valuation"
    FINANCIAL_SAFETY = "financial_safety"
    INDUSTRY = "industry"
    CATALYST = "catalyst"
    RISK = "risk"
    SENTIMENT = "sentiment"


class SignalDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class SignalRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class InstrumentDraft(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    exchange: Exchange
    name: str | None = Field(default=None, max_length=256)


class Instrument(BaseModel):
    instrument_id: str
    symbol: str
    exchange: Exchange
    market: Market
    currency: Currency
    asset_type: AssetType = AssetType.EQUITY
    name: str | None = None


class SignalDraft(BaseModel):
    instrument: InstrumentDraft
    category: SignalCategory
    direction: SignalDirection
    strength: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    horizon_days: int = Field(ge=1, le=365)
    rationale: str = Field(min_length=1, max_length=4_000)
    claim_ids: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def neutral_strength(self):
        if self.direction == SignalDirection.NEUTRAL and self.strength != 0:
            raise ValueError("neutral signals must have zero strength")
        return self


class SignalExtraction(BaseModel):
    signals: list[SignalDraft] = Field(default_factory=list, max_length=100)


class SignalRun(BaseModel):
    signal_run_id: str
    research_run_id: str
    graph_version: str
    model: str
    status: SignalRunStatus = SignalRunStatus.RUNNING
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class Signal(BaseModel):
    signal_id: str
    signal_run_id: str
    research_run_id: str
    instrument: Instrument
    category: SignalCategory
    direction: SignalDirection
    strength: float = Field(ge=0, le=1)
    signed_value: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    effective_at: datetime
    expires_at: datetime
    rationale: str
    claim_ids: list[str] = Field(min_length=1)


class SignalRunDetail(BaseModel):
    run: SignalRun
    signals: list[Signal] = Field(default_factory=list)


class SignalDetail(BaseModel):
    signal: Signal
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
