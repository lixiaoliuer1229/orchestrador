"""CLI for deterministic synthetic market data."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timezone

from app.market.ingest import MarketDataIngestionService
from app.market.mock import MockMarketDataProvider
from app.market.models import Market
from app.market.repo import PostgresMarketRepo


def _date(value: str) -> date:
    return date.fromisoformat(value)


def dry_run(provider: MockMarketDataProvider, start: date, end: date) -> dict[str, int]:
    instruments = provider.instruments(Market.CN, end)
    ids = [item.instrument_id for item in instruments]
    calendar = provider.calendar(Market.CN, start, end)
    placeholder = "00000000-0000-0000-0000-000000000000"
    return {
        "instruments": len(instruments),
        "calendar": len(calendar),
        "daily_bars": len(provider.daily_bars(ids, start, end, placeholder)),
        "corporate_actions": len(
            provider.corporate_actions(ids, start, end, placeholder)
        ),
        "instrument_status": len(
            provider.instrument_status(ids, start, end, placeholder)
        ),
        "financial_facts": len(
            provider.financial_facts(
                ids, datetime.combine(end, time.max, tzinfo=timezone.utc), placeholder
            )
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed deterministic synthetic A-share data"
    )
    parser.add_argument("--start", type=_date, default=date(2025, 1, 1))
    parser.add_argument("--end", type=_date, default=date(2025, 12, 31))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-invalid", action="store_true")
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("--start must not be after --end")
    provider = MockMarketDataProvider(include_invalid=not args.no_invalid)
    if args.dry_run:
        print(dry_run(provider, args.start, args.end))
        return
    result = MarketDataIngestionService(provider, PostgresMarketRepo()).ingest(
        Market.CN, args.start, args.end
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
