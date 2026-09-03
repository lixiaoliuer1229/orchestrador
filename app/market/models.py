"""Provider-independent, point-in-time market data contracts."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any

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
    ETF = "etf"
    INDEX = "index"


class Currency(StrEnum):
    CNY = "CNY"
    USD = "USD"


class InstrumentState(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELISTED = "delisted"


class Instrument(BaseModel):
    instrument_id: str
    symbol: str
    exchange: Exchange
    market: Market
    currency: Currency
    asset_type: AssetType = AssetType.EQUITY
    name: str | None = None
    qlib_code: str | None = None
    listing_date: date | None = None
    delisting_date: date | None = None
    state: InstrumentState = InstrumentState.ACTIVE
    industry: str | None = None
    sector: str | None = None
    timezone: str = "UTC"
    lot_size: int = Field(default=1, ge=1)
    settlement_days: int = Field(default=0, ge=0, le=3)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_lifecycle(self):
        if (
            self.listing_date
            and self.delisting_date
            and self.delisting_date < self.listing_date
        ):
            raise ValueError("delisting_date cannot be before listing_date")
        return self


class TradingDay(BaseModel):
    exchange: Exchange
    trade_date: date
    is_open: bool
    opens_at: time | None = None
    closes_at: time | None = None
    timezone: str
    note: str | None = None

    @model_validator(mode="after")
    def valid_session(self):
        if self.is_open and (self.opens_at is None or self.closes_at is None):
            raise ValueError("open trading days require open and close times")
        if self.opens_at and self.closes_at and self.opens_at >= self.closes_at:
            raise ValueError("opens_at must be before closes_at")
        return self


class DailyBar(BaseModel):
    instrument_id: str
    trade_date: date
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    prev_close: Decimal | None = Field(default=None, gt=0)
    volume: Decimal = Field(ge=0)
    turnover: Decimal = Field(ge=0)
    adjustment_factor: Decimal = Field(default=Decimal("1"), gt=0)
    suspended: bool = False
    limit_up: Decimal | None = Field(default=None, gt=0)
    limit_down: Decimal | None = Field(default=None, gt=0)
    provider: str = Field(min_length=1, max_length=64)
    ingested_at: datetime
    ingestion_run_id: str


class ActionType(StrEnum):
    CASH_DIVIDEND = "cash_dividend"
    STOCK_DIVIDEND = "stock_dividend"
    SPLIT = "split"
    RIGHTS = "rights"


class CorporateAction(BaseModel):
    action_id: str
    instrument_id: str
    action_type: ActionType
    announced_at: datetime
    record_date: date | None = None
    ex_date: date
    cash_amount: Decimal | None = Field(default=None, ge=0)
    ratio: Decimal | None = Field(default=None, gt=0)
    currency: Currency | None = None
    source_id: str | None = None
    provider: str = Field(min_length=1, max_length=64)
    ingestion_run_id: str


class InstrumentStatus(BaseModel):
    instrument_id: str
    trade_date: date
    suspended: bool = False
    is_st: bool = False
    is_star_st: bool = False
    can_buy: bool = True
    can_sell: bool = True
    reason: str | None = None
    provider: str = Field(min_length=1, max_length=64)
    ingestion_run_id: str


class FinancialFact(BaseModel):
    fact_id: str
    instrument_id: str
    metric: str = Field(min_length=1, max_length=128)
    report_period: date
    announced_at: datetime
    value: Decimal
    unit: str = Field(min_length=1, max_length=32)
    currency: Currency | None = None
    restatement: int = Field(default=0, ge=0)
    source_id: str | None = None
    provider: str = Field(min_length=1, max_length=64)
    ingestion_run_id: str


class IngestionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestionRun(BaseModel):
    ingestion_run_id: str
    provider: str
    dataset: str
    market: Market
    data_start: date | None = None
    data_end: date | None = None
    version: str
    status: IngestionStatus = IngestionStatus.RUNNING
    started_at: datetime
    completed_at: datetime | None = None
    received_count: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    error: str | None = None


class IssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class QualityIssue(BaseModel):
    issue_id: str
    ingestion_run_id: str
    severity: IssueSeverity
    code: str
    entity_type: str
    entity_key: str
    message: str
    rejected: bool
    observed: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
