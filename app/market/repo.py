"""PostgreSQL persistence and guarded ingestion for market data."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID

from psycopg.types.json import Jsonb

from app.db import connect
from app.market.models import (
    DailyBar,
    CorporateAction,
    FinancialFact,
    IngestionRun,
    IngestionStatus,
    Instrument,
    InstrumentStatus,
    Market,
    QualityIssue,
    TradingDay,
)
from app.market.quality import (
    check_action,
    check_bar,
    check_financial_fact,
    check_status,
    duplicate_issues,
)


class MarketRepo(Protocol):
    def list_instruments(
        self, market: Market | None, limit: int, offset: int
    ) -> list[Instrument]: ...
    def calendar(self, exchange: str, start: date, end: date) -> list[TradingDay]: ...
    def bars(self, instrument_id: str, start: date, end: date) -> list[DailyBar]: ...
    def actions(
        self, instrument_id: str, start: date, end: date
    ) -> list[CorporateAction]: ...
    def statuses(
        self, instrument_id: str, start: date, end: date
    ) -> list[InstrumentStatus]: ...
    def financials(
        self, instrument_id: str, as_of: datetime, metric: str | None
    ) -> list[FinancialFact]: ...
    def list_ingestions(self, limit: int, offset: int) -> list[IngestionRun]: ...
    def list_issues(
        self, run_id: str, limit: int, offset: int
    ) -> list[QualityIssue]: ...
    def snapshot(self) -> list[dict]: ...


class PostgresMarketRepo:
    def upsert_instruments(self, instruments: list[Instrument]) -> None:
        with connect() as connection, connection.cursor() as cursor:
            for item in instruments:
                cursor.execute(
                    """
                    INSERT INTO instruments(
                        instrument_id, symbol, exchange, market, currency, asset_type,
                        name, qlib_code, listing_date, delisting_date, state, industry,
                        sector, timezone, lot_size, settlement_days, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s)
                    ON CONFLICT (instrument_id) DO UPDATE SET
                        name = EXCLUDED.name, qlib_code = EXCLUDED.qlib_code,
                        listing_date = EXCLUDED.listing_date,
                        delisting_date = EXCLUDED.delisting_date, state = EXCLUDED.state,
                        industry = EXCLUDED.industry, sector = EXCLUDED.sector,
                        timezone = EXCLUDED.timezone, lot_size = EXCLUDED.lot_size,
                        settlement_days = EXCLUDED.settlement_days,
                        metadata = instruments.metadata || EXCLUDED.metadata
                    """,
                    (
                        item.instrument_id,
                        item.symbol,
                        item.exchange.value,
                        item.market.value,
                        item.currency.value,
                        item.asset_type.value,
                        item.name,
                        item.qlib_code,
                        item.listing_date,
                        item.delisting_date,
                        item.state.value,
                        item.industry,
                        item.sector,
                        item.timezone,
                        item.lot_size,
                        item.settlement_days,
                        Jsonb(item.metadata),
                    ),
                )

    def upsert_calendar(self, days: list[TradingDay]) -> None:
        with connect() as connection, connection.cursor() as cursor:
            for day in days:
                cursor.execute(
                    """
                    INSERT INTO trading_calendars(
                        exchange, trade_date, is_open, opens_at, closes_at, timezone, note
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (exchange, trade_date) DO UPDATE SET
                        is_open = EXCLUDED.is_open, opens_at = EXCLUDED.opens_at,
                        closes_at = EXCLUDED.closes_at, timezone = EXCLUDED.timezone,
                        note = EXCLUDED.note
                    """,
                    (
                        day.exchange.value,
                        day.trade_date,
                        day.is_open,
                        day.opens_at,
                        day.closes_at,
                        day.timezone,
                        day.note,
                    ),
                )

    def start_ingestion(self, run: IngestionRun) -> None:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO data_ingestion_runs(
                    ingestion_run_id, provider, dataset, market, data_start, data_end,
                    version, status, started_at, received_count, accepted_count,
                    rejected_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    UUID(run.ingestion_run_id),
                    run.provider,
                    run.dataset,
                    run.market.value,
                    run.data_start,
                    run.data_end,
                    run.version,
                    run.status.value,
                    run.started_at,
                    run.received_count,
                    run.accepted_count,
                    run.rejected_count,
                ),
            )

    def ingest_bars(
        self,
        run_id: str,
        bars: list[DailyBar],
        trading_days: dict[date, TradingDay],
    ) -> tuple[int, list[QualityIssue]]:
        self._require_run_id(run_id, bars)
        keys = [f"{item.instrument_id}:{item.trade_date.isoformat()}" for item in bars]
        issues = duplicate_issues(run_id, "daily_bar", keys)
        duplicate_keys = {item.entity_key for item in issues}
        for bar in bars:
            issues.extend(check_bar(bar, trading_days.get(bar.trade_date)))
        rejected_keys = {item.entity_key for item in issues if item.rejected}
        accepted = [
            bar
            for bar, key in zip(bars, keys, strict=True)
            if key not in rejected_keys and key not in duplicate_keys
        ]
        with connect() as connection, connection.cursor() as cursor:
            self._save_issues(cursor, issues)
            for bar in accepted:
                cursor.execute(
                    """
                    INSERT INTO daily_bars(
                        instrument_id, trade_date, open, high, low, close, prev_close,
                        volume, turnover, adjustment_factor, suspended, limit_up,
                        limit_down, provider, ingested_at, ingestion_run_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s)
                    ON CONFLICT (instrument_id, trade_date) DO UPDATE SET
                        open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                        close = EXCLUDED.close, prev_close = EXCLUDED.prev_close,
                        volume = EXCLUDED.volume, turnover = EXCLUDED.turnover,
                        adjustment_factor = EXCLUDED.adjustment_factor,
                        suspended = EXCLUDED.suspended, limit_up = EXCLUDED.limit_up,
                        limit_down = EXCLUDED.limit_down, provider = EXCLUDED.provider,
                        ingested_at = EXCLUDED.ingested_at,
                        ingestion_run_id = EXCLUDED.ingestion_run_id
                    """,
                    (
                        bar.instrument_id,
                        bar.trade_date,
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.prev_close,
                        bar.volume,
                        bar.turnover,
                        bar.adjustment_factor,
                        bar.suspended,
                        bar.limit_up,
                        bar.limit_down,
                        bar.provider,
                        bar.ingested_at,
                        UUID(bar.ingestion_run_id),
                    ),
                )
            self._finish(
                cursor, run_id, len(bars), len(accepted), len(bars) - len(accepted)
            )
        return len(accepted), issues

    def ingest_financials(
        self, run_id: str, facts: list[FinancialFact]
    ) -> tuple[int, list[QualityIssue]]:
        self._require_run_id(run_id, facts)
        keys = [item.fact_id for item in facts]
        issues = duplicate_issues(run_id, "financial_fact", keys)
        for fact in facts:
            issues.extend(check_financial_fact(fact))
        rejected_keys = {item.entity_key for item in issues if item.rejected}
        accepted = [fact for fact in facts if fact.fact_id not in rejected_keys]
        with connect() as connection, connection.cursor() as cursor:
            self._save_issues(cursor, issues)
            for fact in accepted:
                cursor.execute(
                    """
                    INSERT INTO financial_facts(
                        fact_id, instrument_id, metric, report_period, announced_at,
                        value, unit, currency, restatement, source_id, provider,
                        ingestion_run_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (fact_id) DO UPDATE SET
                        announced_at = EXCLUDED.announced_at, value = EXCLUDED.value,
                        unit = EXCLUDED.unit, currency = EXCLUDED.currency,
                        restatement = EXCLUDED.restatement, source_id = EXCLUDED.source_id,
                        provider = EXCLUDED.provider,
                        ingestion_run_id = EXCLUDED.ingestion_run_id
                    """,
                    (
                        fact.fact_id,
                        fact.instrument_id,
                        fact.metric,
                        fact.report_period,
                        fact.announced_at,
                        fact.value,
                        fact.unit,
                        fact.currency.value if fact.currency else None,
                        fact.restatement,
                        fact.source_id,
                        fact.provider,
                        UUID(fact.ingestion_run_id),
                    ),
                )
            self._finish(
                cursor, run_id, len(facts), len(accepted), len(facts) - len(accepted)
            )
        return len(accepted), issues

    def ingest_actions(
        self, run_id: str, actions: list[CorporateAction]
    ) -> tuple[int, list[QualityIssue]]:
        self._require_run_id(run_id, actions)
        issues = duplicate_issues(
            run_id, "corporate_action", [item.action_id for item in actions]
        )
        for action in actions:
            issues.extend(check_action(action))
        rejected = {item.entity_key for item in issues if item.rejected}
        accepted = [item for item in actions if item.action_id not in rejected]
        with connect() as connection, connection.cursor() as cursor:
            self._save_issues(cursor, issues)
            for item in accepted:
                cursor.execute(
                    """
                    INSERT INTO corporate_actions(
                        action_id, instrument_id, action_type, announced_at, record_date,
                        ex_date, cash_amount, ratio, currency, source_id, provider,
                        ingestion_run_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (action_id) DO UPDATE SET
                        announced_at = EXCLUDED.announced_at,
                        record_date = EXCLUDED.record_date, ex_date = EXCLUDED.ex_date,
                        cash_amount = EXCLUDED.cash_amount, ratio = EXCLUDED.ratio,
                        currency = EXCLUDED.currency, source_id = EXCLUDED.source_id,
                        provider = EXCLUDED.provider,
                        ingestion_run_id = EXCLUDED.ingestion_run_id
                    """,
                    (
                        item.action_id,
                        item.instrument_id,
                        item.action_type.value,
                        item.announced_at,
                        item.record_date,
                        item.ex_date,
                        item.cash_amount,
                        item.ratio,
                        item.currency.value if item.currency else None,
                        item.source_id,
                        item.provider,
                        UUID(item.ingestion_run_id),
                    ),
                )
            self._finish(
                cursor,
                run_id,
                len(actions),
                len(accepted),
                len(actions) - len(accepted),
            )
        return len(accepted), issues

    def ingest_statuses(
        self, run_id: str, statuses: list[InstrumentStatus]
    ) -> tuple[int, list[QualityIssue]]:
        self._require_run_id(run_id, statuses)
        keys = [
            f"{item.instrument_id}:{item.trade_date.isoformat()}" for item in statuses
        ]
        issues = duplicate_issues(run_id, "instrument_status", keys)
        for item in statuses:
            issues.extend(check_status(item))
        rejected = {item.entity_key for item in issues if item.rejected}
        accepted = [
            item
            for item, key in zip(statuses, keys, strict=True)
            if key not in rejected
        ]
        with connect() as connection, connection.cursor() as cursor:
            self._save_issues(cursor, issues)
            for item in accepted:
                cursor.execute(
                    """
                    INSERT INTO instrument_statuses(
                        instrument_id, trade_date, suspended, is_st, is_star_st,
                        can_buy, can_sell, reason, provider, ingestion_run_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (instrument_id, trade_date) DO UPDATE SET
                        suspended = EXCLUDED.suspended, is_st = EXCLUDED.is_st,
                        is_star_st = EXCLUDED.is_star_st, can_buy = EXCLUDED.can_buy,
                        can_sell = EXCLUDED.can_sell, reason = EXCLUDED.reason,
                        provider = EXCLUDED.provider,
                        ingestion_run_id = EXCLUDED.ingestion_run_id
                    """,
                    (
                        item.instrument_id,
                        item.trade_date,
                        item.suspended,
                        item.is_st,
                        item.is_star_st,
                        item.can_buy,
                        item.can_sell,
                        item.reason,
                        item.provider,
                        UUID(item.ingestion_run_id),
                    ),
                )
            self._finish(
                cursor,
                run_id,
                len(statuses),
                len(accepted),
                len(statuses) - len(accepted),
            )
        return len(accepted), issues

    def fail_ingestion(self, run_id: str, error: str) -> None:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE data_ingestion_runs SET status = 'failed', completed_at = %s,
                   error = %s WHERE ingestion_run_id = %s""",
                (datetime.now(timezone.utc), error[:1000], UUID(run_id)),
            )

    def complete_ingestion(
        self, run_id: str, received: int, accepted: int, rejected: int = 0
    ) -> None:
        with connect() as connection, connection.cursor() as cursor:
            self._finish(cursor, run_id, received, accepted, rejected)

    def list_instruments(
        self, market: Market | None = None, limit: int = 100, offset: int = 0
    ) -> list[Instrument]:
        where = "WHERE market = %s" if market else ""
        parameters = (market.value, limit, offset) if market else (limit, offset)
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM instruments {where} ORDER BY instrument_id LIMIT %s OFFSET %s",
                parameters,
            )
            return [Instrument.model_validate(row) for row in cursor.fetchall()]

    def calendar(self, exchange: str, start: date, end: date) -> list[TradingDay]:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM trading_calendars WHERE exchange = %s
                   AND trade_date BETWEEN %s AND %s ORDER BY trade_date""",
                (exchange, start, end),
            )
            return [TradingDay.model_validate(row) for row in cursor.fetchall()]

    def bars(self, instrument_id: str, start: date, end: date) -> list[DailyBar]:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM daily_bars WHERE instrument_id = %s
                   AND trade_date BETWEEN %s AND %s ORDER BY trade_date""",
                (instrument_id, start, end),
            )
            return [self._bar(row) for row in cursor.fetchall()]

    def actions(
        self, instrument_id: str, start: date, end: date
    ) -> list[CorporateAction]:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM corporate_actions WHERE instrument_id = %s
                   AND ex_date BETWEEN %s AND %s ORDER BY ex_date, action_id""",
                (instrument_id, start, end),
            )
            return [
                CorporateAction.model_validate(
                    {**row, "ingestion_run_id": str(row["ingestion_run_id"])}
                )
                for row in cursor.fetchall()
            ]

    def statuses(
        self, instrument_id: str, start: date, end: date
    ) -> list[InstrumentStatus]:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM instrument_statuses WHERE instrument_id = %s
                   AND trade_date BETWEEN %s AND %s ORDER BY trade_date""",
                (instrument_id, start, end),
            )
            return [
                InstrumentStatus.model_validate(
                    {**row, "ingestion_run_id": str(row["ingestion_run_id"])}
                )
                for row in cursor.fetchall()
            ]

    def financials(
        self, instrument_id: str, as_of: datetime, metric: str | None = None
    ) -> list[FinancialFact]:
        metric_clause = "AND metric = %s" if metric else ""
        parameters = (
            (instrument_id, as_of, metric) if metric else (instrument_id, as_of)
        )
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT * FROM financial_facts WHERE instrument_id = %s
                    AND announced_at <= %s {metric_clause}
                    ORDER BY report_period, announced_at, restatement""",
                parameters,
            )
            return [self._fact(row) for row in cursor.fetchall()]

    def list_ingestions(self, limit: int = 20, offset: int = 0) -> list[IngestionRun]:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM data_ingestion_runs ORDER BY started_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [self._run(row) for row in cursor.fetchall()]

    def list_issues(
        self, run_id: str, limit: int = 100, offset: int = 0
    ) -> list[QualityIssue]:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM data_quality_issues WHERE ingestion_run_id = %s
                   ORDER BY created_at, issue_id LIMIT %s OFFSET %s""",
                (UUID(run_id), limit, offset),
            )
            return [self._issue_model(row) for row in cursor.fetchall()]

    def snapshot(self) -> list[dict]:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT ingestion_run_id, provider, dataset, version, completed_at,
                          received_count, accepted_count, rejected_count
                   FROM data_ingestion_runs WHERE status = 'completed'
                   ORDER BY completed_at, ingestion_run_id"""
            )
            return [
                {**row, "ingestion_run_id": str(row["ingestion_run_id"])}
                for row in cursor.fetchall()
            ]

    @staticmethod
    def _finish(
        cursor, run_id: str, received: int, accepted: int, rejected: int
    ) -> None:
        cursor.execute(
            """UPDATE data_ingestion_runs SET status = 'completed', completed_at = %s,
               received_count = %s, accepted_count = %s, rejected_count = %s
               WHERE ingestion_run_id = %s""",
            (datetime.now(timezone.utc), received, accepted, rejected, UUID(run_id)),
        )

    @staticmethod
    def _require_run_id(run_id: str, records: list) -> None:
        if any(item.ingestion_run_id != run_id for item in records):
            raise ValueError("record ingestion_run_id does not match target run")

    @staticmethod
    def _save_issues(cursor, issues: list[QualityIssue]) -> None:
        for item in issues:
            cursor.execute(
                """INSERT INTO data_quality_issues(
                    issue_id, ingestion_run_id, severity, code, entity_type, entity_key,
                    message, rejected, observed, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (issue_id) DO UPDATE SET observed = EXCLUDED.observed,
                    created_at = EXCLUDED.created_at""",
                (
                    item.issue_id,
                    UUID(item.ingestion_run_id),
                    item.severity.value,
                    item.code,
                    item.entity_type,
                    item.entity_key,
                    item.message,
                    item.rejected,
                    Jsonb(item.observed),
                    item.created_at,
                ),
            )

    @staticmethod
    def _bar(row) -> DailyBar:
        return DailyBar.model_validate(
            {**row, "ingestion_run_id": str(row["ingestion_run_id"])}
        )

    @staticmethod
    def _fact(row) -> FinancialFact:
        return FinancialFact.model_validate(
            {**row, "ingestion_run_id": str(row["ingestion_run_id"])}
        )

    @staticmethod
    def _issue_model(row) -> QualityIssue:
        return QualityIssue.model_validate(
            {**row, "ingestion_run_id": str(row["ingestion_run_id"])}
        )

    @staticmethod
    def _run(row) -> IngestionRun:
        return IngestionRun.model_validate(
            {**row, "ingestion_run_id": str(row["ingestion_run_id"])}
        )
