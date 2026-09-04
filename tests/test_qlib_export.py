import csv
from datetime import date, datetime, timezone
from decimal import Decimal

from app.market.models import (
    Currency,
    DailyBar,
    Exchange,
    FinancialFact,
    Instrument,
    Market,
)
from app.qlib.export import QlibCsvExporter
from app.signals.models import Signal, SignalCategory, SignalDirection

RUN_ID = "11111111-1111-1111-1111-111111111111"
SIGNAL_RUN_ID = "22222222-2222-2222-2222-222222222222"
DATES = (date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6))


def instrument() -> Instrument:
    return Instrument(
        instrument_id="XSHG:600519",
        symbol="600519",
        exchange=Exchange.XSHG,
        market=Market.CN,
        currency=Currency.CNY,
        name="模拟证券",
        qlib_code="SH600519",
        timezone="Asia/Shanghai",
        lot_size=100,
        settlement_days=1,
        metadata={"synthetic": True},
    )


def bars() -> list[DailyBar]:
    result = []
    for index, trading_date in enumerate(DATES):
        result.append(
            DailyBar(
                instrument_id="XSHG:600519",
                trade_date=trading_date,
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10.5"),
                volume=Decimal("1000"),
                turnover=Decimal("10500"),
                adjustment_factor=Decimal("2"),
                suspended=index == 1,
                provider="mock",
                ingested_at=datetime(2025, 1, 7, tzinfo=timezone.utc),
                ingestion_run_id=RUN_ID,
            )
        )
    return result


class FakeMarketRepo:
    def list_instruments(self, market, limit, offset):
        return [instrument()]

    def bars(self, instrument_id, start, end):
        return bars()

    def financials(self, instrument_id, as_of, metric):
        return [
            FinancialFact(
                fact_id="fact-a",
                instrument_id=instrument_id,
                metric="net_income",
                report_period=date(2024, 12, 31),
                announced_at=datetime(2025, 1, 2, 8, tzinfo=timezone.utc),
                value=Decimal("123"),
                unit="CNY",
                currency=Currency.CNY,
                provider="mock",
                ingestion_run_id=RUN_ID,
            )
        ]

    def snapshot(self):
        return [{"ingestion_run_id": RUN_ID, "version": "synthetic-cn-v1"}]


class FakeSignalRepo:
    def list(self, limit, offset, instrument_id, research_run_id):
        if offset:
            return []
        return [
            Signal(
                signal_id="signal-a",
                signal_run_id=SIGNAL_RUN_ID,
                research_run_id=RUN_ID,
                instrument=instrument(),
                category=SignalCategory.QUALITY,
                direction=SignalDirection.POSITIVE,
                strength=0.8,
                signed_value=0.8,
                confidence=0.5,
                effective_at=datetime(2025, 1, 2, 8, tzinfo=timezone.utc),
                expires_at=datetime(2025, 1, 6, 23, tzinfo=timezone.utc),
                rationale="test",
                claim_ids=["claim-a"],
            )
        ]


def test_export_creates_qlib_csv_with_point_in_time_features(tmp_path):
    manifest = QlibCsvExporter(FakeMarketRepo(), FakeSignalRepo()).export(
        tmp_path, Market.CN, DATES[0], DATES[-1]
    )
    with (tmp_path / "SH600519.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert manifest.instruments == ["SH600519"]
    assert "fund_net_income" in manifest.fields
    assert "signal_quality" in manifest.fields
    assert rows[0]["fund_net_income"] == ""
    assert rows[0]["signal_quality"] == ""
    assert rows[0]["close"] == "21.0"
    assert rows[0]["volume"] == "500"
    assert rows[1]["fund_net_income"] == "123"
    assert rows[1]["signal_quality"] == "0.8"
    assert rows[1]["open"] == ""
    assert rows[1]["factor"] == ""
    assert len(manifest.files["SH600519.csv"]) == 64
    assert (tmp_path / "manifest.json").exists()


def test_export_is_reproducible_except_manifest_timestamp(tmp_path):
    exporter = QlibCsvExporter(FakeMarketRepo(), FakeSignalRepo())
    first = exporter.export(tmp_path, Market.CN, DATES[0], DATES[-1])
    second = exporter.export(tmp_path, Market.CN, DATES[0], DATES[-1])

    assert first.files == second.files


def test_export_rejects_reversed_range(tmp_path):
    exporter = QlibCsvExporter(FakeMarketRepo())

    try:
        exporter.export(tmp_path, Market.CN, DATES[-1], DATES[0])
    except ValueError as exc:
        assert str(exc) == "start must not be after end"
    else:
        raise AssertionError("reversed range should fail")


def test_export_refuses_untracked_csv(tmp_path):
    (tmp_path / "personal.csv").write_text("do not delete", encoding="utf-8")

    try:
        QlibCsvExporter(FakeMarketRepo()).export(
            tmp_path, Market.CN, DATES[0], DATES[-1]
        )
    except ValueError as exc:
        assert "personal.csv" in str(exc)
    else:
        raise AssertionError("untracked CSV should be preserved and rejected")

    assert (tmp_path / "personal.csv").read_text(encoding="utf-8") == "do not delete"
