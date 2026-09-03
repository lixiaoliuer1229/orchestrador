"""Port implemented by concrete market-data vendors."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from app.market.models import (
    CorporateAction,
    DailyBar,
    FinancialFact,
    Instrument,
    InstrumentStatus,
    Market,
    TradingDay,
)


class MarketDataProvider(Protocol):
    """Provider boundary; core code must not depend on a vendor SDK."""

    name: str

    def instruments(self, market: Market, as_of: date) -> list[Instrument]: ...
    def calendar(self, market: Market, start: date, end: date) -> list[TradingDay]: ...
    def daily_bars(
        self, instrument_ids: list[str], start: date, end: date, run_id: str
    ) -> list[DailyBar]: ...
    def corporate_actions(
        self, instrument_ids: list[str], start: date, end: date, run_id: str
    ) -> list[CorporateAction]: ...
    def instrument_status(
        self, instrument_ids: list[str], start: date, end: date, run_id: str
    ) -> list[InstrumentStatus]: ...
    def financial_facts(
        self, instrument_ids: list[str], known_at: datetime, run_id: str
    ) -> list[FinancialFact]: ...
