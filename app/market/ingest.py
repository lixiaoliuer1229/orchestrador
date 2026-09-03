"""Orchestrate provider ingestion through the production repository boundary."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.market.models import IngestionRun, Market
from app.market.provider import MarketDataProvider


class DatasetResult(BaseModel):
    dataset: str
    ingestion_run_id: str
    received: int
    accepted: int
    rejected: int


class IngestionResult(BaseModel):
    provider: str
    market: Market
    start: date
    end: date
    datasets: list[DatasetResult] = Field(default_factory=list)


class MarketDataIngestionService:
    def __init__(self, provider: MarketDataProvider, repo: Any):
        self.provider = provider
        self.repo = repo

    def ingest(self, market: Market, start: date, end: date) -> IngestionResult:
        if start > end:
            raise ValueError("start must not be after end")
        instruments = self.provider.instruments(market, end)
        instrument_ids = [item.instrument_id for item in instruments]
        calendar = self.provider.calendar(market, start, end)
        results = [
            self._plain(
                "instruments",
                market,
                start,
                end,
                instruments,
                self.repo.upsert_instruments,
            ),
            self._plain(
                "calendar", market, start, end, calendar, self.repo.upsert_calendar
            ),
        ]
        trading_days = {item.trade_date: item for item in calendar if item.is_open}
        results.append(
            self._guarded(
                "daily_bars",
                market,
                start,
                end,
                lambda run_id: self.provider.daily_bars(
                    instrument_ids, start, end, run_id
                ),
                lambda run_id, rows: self.repo.ingest_bars(run_id, rows, trading_days),
            )
        )
        results.append(
            self._guarded(
                "corporate_actions",
                market,
                start,
                end,
                lambda run_id: self.provider.corporate_actions(
                    instrument_ids, start, end, run_id
                ),
                self.repo.ingest_actions,
            )
        )
        results.append(
            self._guarded(
                "instrument_status",
                market,
                start,
                end,
                lambda run_id: self.provider.instrument_status(
                    instrument_ids, start, end, run_id
                ),
                self.repo.ingest_statuses,
            )
        )
        known_at = datetime.combine(end, time.max, tzinfo=timezone.utc)
        results.append(
            self._guarded(
                "financial_facts",
                market,
                start,
                end,
                lambda run_id: self.provider.financial_facts(
                    instrument_ids, known_at, run_id
                ),
                self.repo.ingest_financials,
            )
        )
        return IngestionResult(
            provider=self.provider.name,
            market=market,
            start=start,
            end=end,
            datasets=results,
        )

    def _new_run(
        self, dataset: str, market: Market, start: date, end: date
    ) -> IngestionRun:
        return IngestionRun(
            ingestion_run_id=str(uuid4()),
            provider=self.provider.name,
            dataset=dataset,
            market=market,
            data_start=start,
            data_end=end,
            version=getattr(self.provider, "version", "unknown"),
            started_at=datetime.now(timezone.utc),
        )

    def _plain(self, dataset, market, start, end, rows, save) -> DatasetResult:
        run = self._new_run(dataset, market, start, end)
        self.repo.start_ingestion(run)
        try:
            save(rows)
            self.repo.complete_ingestion(run.ingestion_run_id, len(rows), len(rows), 0)
        except Exception as exc:
            self.repo.fail_ingestion(run.ingestion_run_id, exc.__class__.__name__)
            raise
        return DatasetResult(
            dataset=dataset,
            ingestion_run_id=run.ingestion_run_id,
            received=len(rows),
            accepted=len(rows),
            rejected=0,
        )

    def _guarded(self, dataset, market, start, end, load, save) -> DatasetResult:
        run = self._new_run(dataset, market, start, end)
        self.repo.start_ingestion(run)
        try:
            rows = load(run.ingestion_run_id)
            accepted, _ = save(run.ingestion_run_id, rows)
        except Exception as exc:
            self.repo.fail_ingestion(run.ingestion_run_id, exc.__class__.__name__)
            raise
        return DatasetResult(
            dataset=dataset,
            ingestion_run_id=run.ingestion_run_id,
            received=len(rows),
            accepted=accepted,
            rejected=len(rows) - accepted,
        )
