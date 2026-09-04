"""Export PostgreSQL market data to Qlib dump-compatible CSV files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.market.models import FinancialFact, Instrument, Market
from app.market.repo import PostgresMarketRepo
from app.signals.models import Signal
from app.signals.repo import PostgresSignalRepo

BASE_FIELDS = (
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "money",
    "factor",
)


class ExportManifest(BaseModel):
    format: str = "qlib-dump-csv-v1"
    generated_at: datetime
    market: Market
    start: date
    end: date
    point_in_time_policy: str = "next_open_trading_day"
    instruments: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)
    ingestion_runs: list[dict[str, Any]] = Field(default_factory=list)


def _safe_metric(metric: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9_]+", "_", metric.strip().lower()).strip("_")
    return f"fund_{normalized}" if normalized else None


def _next_date(after: date, trading_dates: list[date]) -> date | None:
    return next((item for item in trading_dates if item > after), None)


def _financial_features(
    facts: list[FinancialFact], trading_dates: list[date], timezone_name: str
) -> dict[date, dict[str, Decimal]]:
    local_timezone = ZoneInfo(timezone_name)
    events: dict[date, list[FinancialFact]] = {}
    for fact in facts:
        available = _next_date(
            fact.announced_at.astimezone(local_timezone).date(), trading_dates
        )
        if available:
            events.setdefault(available, []).append(fact)
    current: dict[str, tuple[date, datetime, int, Decimal]] = {}
    result: dict[date, dict[str, Decimal]] = {}
    for trading_date in trading_dates:
        for fact in events.get(trading_date, []):
            field = _safe_metric(fact.metric)
            if not field:
                continue
            candidate = (
                fact.report_period,
                fact.announced_at,
                fact.restatement,
                fact.value,
            )
            existing = current.get(field)
            if existing is None or candidate[:3] >= existing[:3]:
                current[field] = candidate
        result[trading_date] = {field: item[3] for field, item in current.items()}
    return result


def _signal_features(
    signals: list[Signal], trading_dates: list[date], timezone_name: str
) -> dict[date, dict[str, Decimal]]:
    local_timezone = ZoneInfo(timezone_name)
    result: dict[date, dict[str, Decimal]] = {}
    for trading_date in trading_dates:
        values: dict[str, list[tuple[Decimal, Decimal]]] = {}
        for signal in signals:
            available = _next_date(
                signal.effective_at.astimezone(local_timezone).date(), trading_dates
            )
            if (
                available is None
                or trading_date < available
                or trading_date > signal.expires_at.astimezone(local_timezone).date()
            ):
                continue
            field = f"signal_{signal.category.value}"
            values.setdefault(field, []).append(
                (Decimal(str(signal.signed_value)), Decimal(str(signal.confidence)))
            )
        result[trading_date] = {}
        for field, observations in values.items():
            total_weight = sum((weight for _, weight in observations), Decimal("0"))
            if total_weight:
                result[trading_date][field] = (
                    sum(
                        (value * weight for value, weight in observations), Decimal("0")
                    )
                    / total_weight
                )
    return result


class QlibCsvExporter:
    def __init__(self, market_repo, signal_repo=None):
        self.market_repo = market_repo
        self.signal_repo = signal_repo

    def export(
        self, output: Path, market: Market, start: date, end: date
    ) -> ExportManifest:
        if start > end:
            raise ValueError("start must not be after end")
        output.mkdir(parents=True, exist_ok=True)
        self._prepare_output(output)
        instruments = self.market_repo.list_instruments(market, 1000, 0)
        file_hashes: dict[str, str] = {}
        all_fields = set(BASE_FIELDS)
        exported: list[str] = []
        for instrument in instruments:
            if not instrument.qlib_code:
                continue
            bars = self.market_repo.bars(instrument.instrument_id, start, end)
            if not bars:
                continue
            trading_dates = [bar.trade_date for bar in bars]
            facts = self.market_repo.financials(
                instrument.instrument_id,
                datetime.combine(
                    end, datetime.max.time(), tzinfo=ZoneInfo(instrument.timezone)
                ).astimezone(timezone.utc),
                None,
            )
            financial = _financial_features(facts, trading_dates, instrument.timezone)
            signals = self._signals(instrument)
            signal_values = _signal_features(
                signals, trading_dates, instrument.timezone
            )
            dynamic_fields = sorted(
                {key for values in financial.values() for key in values}
                | {key for values in signal_values.values() for key in values}
            )
            fields = [*BASE_FIELDS, *dynamic_fields]
            path = output / f"{instrument.qlib_code.upper()}.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for bar in bars:
                    row = self._bar_row(instrument, bar)
                    row.update(financial.get(bar.trade_date, {}))
                    row.update(signal_values.get(bar.trade_date, {}))
                    writer.writerow(row)
            file_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            exported.append(instrument.qlib_code.upper())
            all_fields.update(fields)
        manifest = ExportManifest(
            generated_at=datetime.now(timezone.utc),
            market=market,
            start=start,
            end=end,
            instruments=sorted(exported),
            fields=[*BASE_FIELDS, *sorted(all_fields - set(BASE_FIELDS))],
            files=file_hashes,
            ingestion_runs=self.market_repo.snapshot(),
        )
        (output / "manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        return manifest

    @staticmethod
    def _prepare_output(output: Path) -> None:
        manifest_path = output / "manifest.json"
        tracked: set[str] = set()
        if manifest_path.exists():
            previous = ExportManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
            tracked = set(previous.files)
        untracked = {
            path.name for path in output.glob("*.csv") if path.name not in tracked
        }
        if untracked:
            raise ValueError(
                "output contains untracked CSV files: " + ", ".join(sorted(untracked))
            )
        for name in tracked:
            path = output / name
            if path.is_file() and path.suffix.lower() == ".csv":
                path.unlink()

    def _signals(self, instrument: Instrument) -> list[Signal]:
        if self.signal_repo is None:
            return []
        result: list[Signal] = []
        offset = 0
        while True:
            page = self.signal_repo.list(100, offset, instrument.instrument_id, None)
            result.extend(page)
            if len(page) < 100:
                return result
            offset += 100

    @staticmethod
    def _bar_row(instrument, bar) -> dict[str, Any]:
        row: dict[str, Any] = {
            "date": bar.trade_date.isoformat(),
            "symbol": instrument.qlib_code,
        }
        if bar.suspended:
            row.update({field: "" for field in BASE_FIELDS[2:]})
            return row
        factor = bar.adjustment_factor
        row.update(
            {
                "open": bar.open * factor,
                "high": bar.high * factor,
                "low": bar.low * factor,
                "close": bar.close * factor,
                "volume": bar.volume / factor,
                "money": bar.turnover,
                "factor": factor,
            }
        )
        return row


def _date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export point-in-time Qlib source CSV")
    parser.add_argument("--output", type=Path, default=Path("data/qlib/source"))
    parser.add_argument("--market", type=Market, default=Market.CN)
    parser.add_argument("--start", type=_date, default=date(2025, 1, 1))
    parser.add_argument("--end", type=_date, default=date(2025, 12, 31))
    args = parser.parse_args()
    manifest = QlibCsvExporter(PostgresMarketRepo(), PostgresSignalRepo()).export(
        args.output, args.market, args.start, args.end
    )
    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
