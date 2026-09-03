from datetime import date, datetime, time, timezone

from app.market.ingest import MarketDataIngestionService
from app.market.mock import MockMarketDataProvider
from app.market.models import Market
from app.market.quality import check_bar
from app.market.seed import dry_run

START = date(2025, 1, 1)
END = date(2025, 3, 31)


def test_mock_provider_is_deterministic_and_explicitly_synthetic():
    first = MockMarketDataProvider(include_invalid=False)
    second = MockMarketDataProvider(include_invalid=False)
    instruments = first.instruments(Market.CN, END)
    ids = [item.instrument_id for item in instruments]

    first_bars = first.daily_bars(ids, START, END, "run-a")
    second_bars = second.daily_bars(ids, START, END, "run-a")

    assert first_bars == second_bars
    assert len(instruments) == 5
    assert all(item.metadata["synthetic"] is True for item in instruments)
    assert {item.provider for item in first_bars} == {"mock"}


def test_mock_provider_includes_a_quality_gate_sample():
    provider = MockMarketDataProvider(include_invalid=True)
    ids = [item.instrument_id for item in provider.instruments(Market.CN, END)]
    bars = provider.daily_bars(ids, START, END, "run-a")

    issues = check_bar(bars[-1])

    assert issues[0].code == "invalid_ohlc"


def test_mock_provider_models_suspension_and_financial_visibility():
    provider = MockMarketDataProvider(include_invalid=False)
    ids = [item.instrument_id for item in provider.instruments(Market.CN, END)]
    statuses = provider.instrument_status(ids, START, END, "run-a")
    known_at = datetime.combine(END, time.max, tzinfo=timezone.utc)
    facts = provider.financial_facts(ids, known_at, "run-a")

    assert any(
        item.suspended and not item.can_buy and not item.can_sell for item in statuses
    )
    assert all(item.announced_at <= known_at for item in facts)


class FakeRepo:
    def __init__(self):
        self.started = []
        self.completed = []

    def start_ingestion(self, run):
        self.started.append(run)

    def complete_ingestion(self, run_id, received, accepted, rejected):
        self.completed.append((run_id, received, accepted, rejected))

    def fail_ingestion(self, run_id, error):
        raise AssertionError(error)

    def upsert_instruments(self, rows):
        self.instruments = rows

    def upsert_calendar(self, rows):
        self.calendar = rows

    def ingest_bars(self, run_id, rows, trading_days):
        invalid = sum(
            bool(check_bar(row, trading_days.get(row.trade_date))) for row in rows
        )
        return len(rows) - invalid, []

    def ingest_actions(self, run_id, rows):
        return len(rows), []

    def ingest_statuses(self, run_id, rows):
        return len(rows), []

    def ingest_financials(self, run_id, rows):
        return len(rows), []


def test_ingestion_service_uses_separate_auditable_runs():
    repo = FakeRepo()
    result = MarketDataIngestionService(
        MockMarketDataProvider(include_invalid=True), repo
    ).ingest(Market.CN, START, END)

    assert [item.dataset for item in result.datasets] == [
        "instruments",
        "calendar",
        "daily_bars",
        "corporate_actions",
        "instrument_status",
        "financial_facts",
    ]
    assert len({item.ingestion_run_id for item in result.datasets}) == 6
    bars = next(item for item in result.datasets if item.dataset == "daily_bars")
    assert bars.rejected == 1


def test_seed_dry_run_does_not_need_a_database():
    counts = dry_run(MockMarketDataProvider(), START, END)

    assert counts["instruments"] == 5
    assert counts["daily_bars"] > 0
    assert counts["corporate_actions"] == 1
