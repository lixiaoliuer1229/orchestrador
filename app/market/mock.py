"""Deterministic synthetic A-share data provider for development."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.market.models import (
    ActionType,
    CorporateAction,
    Currency,
    DailyBar,
    Exchange,
    FinancialFact,
    Instrument,
    InstrumentState,
    InstrumentStatus,
    Market,
    TradingDay,
)

CENT = Decimal("0.01")


def _id(*parts: object) -> str:
    return hashlib.sha256("\0".join(map(str, parts)).encode()).hexdigest()[:24]


def _dates(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


class MockMarketDataProvider:
    """Reproducible synthetic provider; its output must never be treated as real."""

    name = "mock"
    version = "synthetic-cn-v1"

    def __init__(self, *, include_invalid: bool = True):
        self.include_invalid = include_invalid

    def instruments(self, market: Market, as_of: date) -> list[Instrument]:
        if market != Market.CN:
            return []
        definitions = (
            ("600519", Exchange.XSHG, "贵州茅台（模拟）", "食品饮料", Decimal("1500")),
            ("000001", Exchange.XSHE, "平安银行（模拟）", "银行", Decimal("12")),
            ("300750", Exchange.XSHE, "宁德时代（模拟）", "新能源", Decimal("220")),
            ("601318", Exchange.XSHG, "中国平安（模拟）", "保险", Decimal("48")),
            ("430047", Exchange.BSE, "示例北交所（模拟）", "工业", Decimal("18")),
        )
        result = []
        for symbol, exchange, name, industry, _ in definitions:
            prefix = {Exchange.XSHG: "SH", Exchange.XSHE: "SZ", Exchange.BSE: "BJ"}[
                exchange
            ]
            result.append(
                Instrument(
                    instrument_id=f"{exchange.value}:{symbol}",
                    symbol=symbol,
                    exchange=exchange,
                    market=Market.CN,
                    currency=Currency.CNY,
                    name=name,
                    qlib_code=f"{prefix}{symbol}",
                    listing_date=date(2015, 1, 1),
                    state=InstrumentState.ACTIVE,
                    industry=industry,
                    sector="A股模拟股票池",
                    timezone="Asia/Shanghai",
                    lot_size=100,
                    settlement_days=1,
                    metadata={"synthetic": True, "provider_version": self.version},
                )
            )
        return result

    def calendar(self, market: Market, start: date, end: date) -> list[TradingDay]:
        if market != Market.CN:
            return []
        result = []
        for day in _dates(start, end):
            is_open = day.weekday() < 5
            for exchange in (Exchange.XSHG, Exchange.XSHE, Exchange.BSE):
                result.append(
                    TradingDay(
                        exchange=exchange,
                        trade_date=day,
                        is_open=is_open,
                        opens_at=time(9, 30) if is_open else None,
                        closes_at=time(15) if is_open else None,
                        timezone="Asia/Shanghai",
                        note="synthetic weekday calendar",
                    )
                )
        return result

    def daily_bars(
        self, instrument_ids: list[str], start: date, end: date, run_id: str
    ) -> list[DailyBar]:
        bases = {
            "XSHG:600519": Decimal("1500"),
            "XSHE:000001": Decimal("12"),
            "XSHE:300750": Decimal("220"),
            "XSHG:601318": Decimal("48"),
            "BSE:430047": Decimal("18"),
        }
        open_days = [day for day in _dates(start, end) if day.weekday() < 5]
        result: list[DailyBar] = []
        for instrument_id in instrument_ids:
            previous = bases[instrument_id]
            for index, day in enumerate(open_days):
                token = int(
                    hashlib.sha256(f"{instrument_id}:{day}".encode()).hexdigest()[:8],
                    16,
                )
                change = Decimal(token % 401 - 200) / Decimal("10000")
                opening = (previous * (Decimal("1") + change / 2)).quantize(
                    CENT, ROUND_HALF_UP
                )
                closing = (previous * (Decimal("1") + change)).quantize(
                    CENT, ROUND_HALF_UP
                )
                high = (max(opening, closing) * Decimal("1.008")).quantize(
                    CENT, ROUND_HALF_UP
                )
                low = (min(opening, closing) * Decimal("0.992")).quantize(
                    CENT, ROUND_HALF_UP
                )
                suspended = instrument_id == "XSHE:000001" and index == 20
                volume = (
                    Decimal("0") if suspended else Decimal(100_000 + token % 900_000)
                )
                limit_up = (previous * Decimal("1.10")).quantize(CENT, ROUND_HALF_UP)
                limit_down = (previous * Decimal("0.90")).quantize(CENT, ROUND_HALF_UP)
                result.append(
                    DailyBar(
                        instrument_id=instrument_id,
                        trade_date=day,
                        open=opening,
                        high=high,
                        low=low,
                        close=closing,
                        prev_close=previous,
                        volume=volume,
                        turnover=(volume * closing).quantize(CENT),
                        adjustment_factor=Decimal("1"),
                        suspended=suspended,
                        limit_up=limit_up,
                        limit_down=limit_down,
                        provider=self.name,
                        ingested_at=datetime.combine(
                            end, time(16), tzinfo=timezone.utc
                        ),
                        ingestion_run_id=run_id,
                    )
                )
                if not suspended:
                    previous = closing
        if self.include_invalid and result:
            target = result[-1]
            result[-1] = target.model_copy(update={"high": target.low - CENT})
        return result

    def corporate_actions(
        self, instrument_ids: list[str], start: date, end: date, run_id: str
    ) -> list[CorporateAction]:
        ex_date = start + (end - start) // 2
        while ex_date.weekday() >= 5:
            ex_date += timedelta(days=1)
        if ex_date > end or "XSHG:600519" not in instrument_ids:
            return []
        return [
            CorporateAction(
                action_id=_id(self.version, "dividend", ex_date),
                instrument_id="XSHG:600519",
                action_type=ActionType.CASH_DIVIDEND,
                announced_at=datetime.combine(
                    ex_date - timedelta(days=20), time(8), tzinfo=timezone.utc
                ),
                record_date=ex_date - timedelta(days=1),
                ex_date=ex_date,
                cash_amount=Decimal("10"),
                currency=Currency.CNY,
                provider=self.name,
                ingestion_run_id=run_id,
            )
        ]

    def instrument_status(
        self, instrument_ids: list[str], start: date, end: date, run_id: str
    ) -> list[InstrumentStatus]:
        open_days = [day for day in _dates(start, end) if day.weekday() < 5]
        result = []
        for instrument_id in instrument_ids:
            for index, day in enumerate(open_days):
                suspended = instrument_id == "XSHE:000001" and index == 20
                is_st = instrument_id == "BSE:430047" and index >= max(
                    0, len(open_days) - 10
                )
                result.append(
                    InstrumentStatus(
                        instrument_id=instrument_id,
                        trade_date=day,
                        suspended=suspended,
                        is_st=is_st,
                        can_buy=not suspended,
                        can_sell=not suspended,
                        reason="synthetic suspension" if suspended else None,
                        provider=self.name,
                        ingestion_run_id=run_id,
                    )
                )
        return result

    def financial_facts(
        self, instrument_ids: list[str], known_at: datetime, run_id: str
    ) -> list[FinancialFact]:
        periods = (
            date(2024, 12, 31),
            date(2025, 3, 31),
            date(2025, 6, 30),
            date(2025, 9, 30),
        )
        metrics = ("revenue", "net_income", "operating_cash_flow")
        result = []
        for instrument_index, instrument_id in enumerate(instrument_ids, start=1):
            for period_index, period in enumerate(periods, start=1):
                announced_at = datetime.combine(
                    period + timedelta(days=45), time(8), tzinfo=timezone.utc
                )
                if announced_at > known_at:
                    continue
                for metric_index, metric in enumerate(metrics, start=1):
                    result.append(
                        FinancialFact(
                            fact_id=_id(self.version, instrument_id, metric, period, 0),
                            instrument_id=instrument_id,
                            metric=metric,
                            report_period=period,
                            announced_at=announced_at,
                            value=Decimal(
                                instrument_index
                                * period_index
                                * metric_index
                                * 1_000_000
                            ),
                            unit="CNY",
                            currency=Currency.CNY,
                            provider=self.name,
                            ingestion_run_id=run_id,
                        )
                    )
        return result
