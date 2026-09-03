import os
from datetime import date, datetime, time, timezone
from decimal import Decimal

os.environ["AUTH_ENABLED"] = "false"

from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.market.models import (
    ActionType,
    CorporateAction,
    Currency,
    DailyBar,
    Exchange,
    FinancialFact,
    InstrumentStatus,
    TradingDay,
)
from app.market.quality import (
    check_action,
    check_bar,
    check_financial_fact,
    check_status,
    duplicate_issues,
)

RUN_ID = "11111111-1111-1111-1111-111111111111"
NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)
client = TestClient(app)


def bar(**updates) -> DailyBar:
    values = {
        "instrument_id": "XSHG:600519",
        "trade_date": date(2026, 9, 3),
        "open": Decimal("1500"),
        "high": Decimal("1520"),
        "low": Decimal("1490"),
        "close": Decimal("1510"),
        "prev_close": Decimal("1498"),
        "volume": Decimal("10000"),
        "turnover": Decimal("15000000"),
        "provider": "test",
        "ingested_at": NOW,
        "ingestion_run_id": RUN_ID,
    }
    values.update(updates)
    return DailyBar(**values)


def open_day() -> TradingDay:
    return TradingDay(
        exchange=Exchange.XSHG,
        trade_date=date(2026, 9, 3),
        is_open=True,
        opens_at=time(9, 30),
        closes_at=time(15),
        timezone="Asia/Shanghai",
    )


def test_valid_daily_bar_passes_quality_checks():
    assert check_bar(bar(), open_day()) == []


def test_invalid_ohlc_and_suspended_trades_are_rejected():
    issues = check_bar(
        bar(high=Decimal("1495"), suspended=True),
        open_day(),
    )

    assert {item.code for item in issues} == {
        "invalid_ohlc",
        "suspended_with_trades",
    }
    assert all(item.rejected for item in issues)


def test_bar_on_closed_day_is_rejected():
    day = open_day().model_copy(update={"is_open": False})
    assert check_bar(bar(), day)[0].code == "bar_on_closed_day"


def test_financial_fact_uses_announcement_time_not_report_period():
    fact = FinancialFact(
        fact_id="fact-a",
        instrument_id="XSHG:600519",
        metric="revenue",
        report_period=date(2026, 12, 31),
        announced_at=NOW,
        value=Decimal("100"),
        unit="CNY",
        currency=Currency.CNY,
        provider="test",
        ingestion_run_id=RUN_ID,
    )

    assert check_financial_fact(fact)[0].code == "announcement_before_period"


def test_corporate_action_and_status_rules():
    action = CorporateAction(
        action_id="action-a",
        instrument_id="XSHG:600519",
        action_type=ActionType.CASH_DIVIDEND,
        announced_at=NOW,
        ex_date=date(2026, 9, 4),
        provider="test",
        ingestion_run_id=RUN_ID,
    )
    status = InstrumentStatus(
        instrument_id="XSHG:600519",
        trade_date=date(2026, 9, 3),
        suspended=True,
        provider="test",
        ingestion_run_id=RUN_ID,
    )

    assert check_action(action)[0].code == "incomplete_cash_dividend"
    assert check_status(status)[0].code == "suspended_but_tradable"


def test_duplicate_batch_keys_are_reported_once():
    issues = duplicate_issues(RUN_ID, "daily_bar", ["a", "a", "a", "b"])

    assert len(issues) == 1
    assert issues[0].entity_key == "a"


def test_market_bars_api(monkeypatch):
    expected = bar()

    class FakeRepo:
        def bars(self, instrument_id, start, end):
            assert instrument_id == "XSHG:600519"
            assert start == end == date(2026, 9, 3)
            return [expected]

    monkeypatch.setattr(main, "market_repo", FakeRepo())
    response = client.get("/market/bars/XSHG:600519?start=2026-09-03&end=2026-09-03")

    assert response.status_code == 200
    assert response.json()[0]["close"] == "1510"


def test_market_api_rejects_reversed_dates(monkeypatch):
    response = client.get(
        "/market/calendar?exchange=XSHG&start=2026-09-04&end=2026-09-03"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "start must not be after end"


def test_financial_api_requires_point_in_time_timezone():
    response = client.get("/market/financials/XSHG:600519?as_of=2026-09-03T12:00:00")

    assert response.status_code == 422
    assert response.json()["detail"] == "as_of must include a timezone"
