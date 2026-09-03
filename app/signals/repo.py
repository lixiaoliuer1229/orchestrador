"""PostgreSQL repository for investment signals and their lineage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from psycopg.types.json import Jsonb

from app.db import connect
from app.signals.models import (
    Instrument,
    Signal,
    SignalDetail,
    SignalRun,
    SignalRunDetail,
    SignalRunStatus,
)


class SignalRepo(Protocol):
    def start(self, run: SignalRun) -> None: ...
    def complete(self, run_id: str, signals: list[Signal]) -> None: ...
    def fail(self, run_id: str, error: str) -> None: ...
    def get_run(self, run_id: str) -> SignalRunDetail | None: ...
    def get_signal(self, signal_id: str) -> SignalDetail | None: ...
    def list(
        self,
        limit: int,
        offset: int,
        instrument_id: str | None = None,
        research_run_id: str | None = None,
    ) -> list[Signal]: ...


class PostgresSignalRepo:
    def start(self, run: SignalRun) -> None:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO signal_runs(
                    signal_run_id, research_run_id, graph_version, model, status, started_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    UUID(run.signal_run_id),
                    UUID(run.research_run_id),
                    run.graph_version,
                    run.model,
                    run.status.value,
                    run.started_at,
                ),
            )

    def complete(self, run_id: str, signals: list[Signal]) -> None:
        with connect() as connection, connection.cursor() as cursor:
            for signal in signals:
                instrument = signal.instrument
                cursor.execute(
                    """
                    INSERT INTO instruments(
                        instrument_id, symbol, exchange, market, currency, asset_type,
                        name, qlib_code, timezone, lot_size, settlement_days, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (instrument_id) DO UPDATE SET
                        name = COALESCE(EXCLUDED.name, instruments.name),
                        qlib_code = COALESCE(EXCLUDED.qlib_code, instruments.qlib_code),
                        timezone = EXCLUDED.timezone,
                        lot_size = EXCLUDED.lot_size,
                        settlement_days = EXCLUDED.settlement_days,
                        metadata = instruments.metadata || EXCLUDED.metadata
                    """,
                    (
                        instrument.instrument_id,
                        instrument.symbol,
                        instrument.exchange.value,
                        instrument.market.value,
                        instrument.currency.value,
                        instrument.asset_type.value,
                        instrument.name,
                        instrument.qlib_code,
                        instrument.timezone,
                        instrument.lot_size,
                        instrument.settlement_days,
                        Jsonb(instrument.metadata),
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO signals(
                        signal_id, signal_run_id, instrument_id, category, direction,
                        strength, signed_value, confidence, effective_at, expires_at,
                        rationale
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (signal_id) DO NOTHING
                    """,
                    (
                        signal.signal_id,
                        UUID(signal.signal_run_id),
                        instrument.instrument_id,
                        signal.category.value,
                        signal.direction.value,
                        signal.strength,
                        signal.signed_value,
                        signal.confidence,
                        signal.effective_at,
                        signal.expires_at,
                        signal.rationale,
                    ),
                )
                for claim_id in signal.claim_ids:
                    cursor.execute(
                        """
                        INSERT INTO signal_claims(signal_id, claim_id)
                        VALUES (%s, %s) ON CONFLICT DO NOTHING
                        """,
                        (signal.signal_id, claim_id),
                    )
            cursor.execute(
                """
                UPDATE signal_runs SET status = 'completed', completed_at = %s
                WHERE signal_run_id = %s
                """,
                (datetime.now(timezone.utc), UUID(run_id)),
            )

    def fail(self, run_id: str, error: str) -> None:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE signal_runs
                SET status = 'failed', completed_at = %s, error = %s
                WHERE signal_run_id = %s
                """,
                (datetime.now(timezone.utc), error[:1_000], UUID(run_id)),
            )

    def get_run(self, run_id: str) -> SignalRunDetail | None:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM signal_runs WHERE signal_run_id = %s", (UUID(run_id),)
            )
            row = cursor.fetchone()
            if not row:
                return None
            run = self._run(row)
            signals = self._signals(
                cursor,
                "WHERE s.signal_run_id = %s",
                (UUID(run_id),),
            )
        return SignalRunDetail(run=run, signals=signals)

    def get_signal(self, signal_id: str) -> SignalDetail | None:
        with connect() as connection, connection.cursor() as cursor:
            signals = self._signals(cursor, "WHERE s.signal_id = %s", (signal_id,))
            if not signals:
                return None
            cursor.execute(
                """
                SELECT DISTINCT e.evidence_id, e.source_id
                FROM signal_claims sc
                JOIN claim_evidence ce ON ce.claim_id = sc.claim_id
                JOIN evidence e ON e.evidence_id = ce.evidence_id
                WHERE sc.signal_id = %s ORDER BY e.evidence_id
                """,
                (signal_id,),
            )
            rows = cursor.fetchall()
        return SignalDetail(
            signal=signals[0],
            evidence_ids=[row["evidence_id"] for row in rows],
            source_ids=list(dict.fromkeys(row["source_id"] for row in rows)),
        )

    def list(
        self,
        limit: int = 20,
        offset: int = 0,
        instrument_id: str | None = None,
        research_run_id: str | None = None,
    ) -> list[Signal]:
        clauses: list[str] = []
        parameters: list[object] = []
        if instrument_id:
            clauses.append("s.instrument_id = %s")
            parameters.append(instrument_id)
        if research_run_id:
            clauses.append("sr.research_run_id = %s")
            parameters.append(UUID(research_run_id))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.extend([limit, offset])
        with connect() as connection, connection.cursor() as cursor:
            return self._signals(
                cursor,
                where,
                tuple(parameters),
                "ORDER BY s.effective_at DESC, s.signal_id LIMIT %s OFFSET %s",
            )

    @staticmethod
    def _signals(
        cursor,
        where: str,
        parameters: tuple[object, ...],
        tail: str = "",
    ) -> list[Signal]:
        cursor.execute(
            f"""
            SELECT s.*, sr.research_run_id, i.symbol, i.exchange, i.market,
                   i.currency, i.asset_type, i.name,
                   COALESCE(array_agg(sc.claim_id ORDER BY sc.claim_id)
                       FILTER (WHERE sc.claim_id IS NOT NULL), ARRAY[]::varchar[]) AS claim_ids
            FROM signals s
            JOIN signal_runs sr ON sr.signal_run_id = s.signal_run_id
            JOIN instruments i ON i.instrument_id = s.instrument_id
            LEFT JOIN signal_claims sc ON sc.signal_id = s.signal_id
            {where}
            GROUP BY s.signal_id, sr.research_run_id, i.instrument_id
            {tail}
            """,
            parameters,
        )
        result: list[Signal] = []
        for row in cursor.fetchall():
            instrument = Instrument.model_validate(row)
            result.append(
                Signal.model_validate(
                    {
                        **row,
                        "signal_run_id": str(row["signal_run_id"]),
                        "research_run_id": str(row["research_run_id"]),
                        "instrument": instrument,
                    }
                )
            )
        return result

    @staticmethod
    def _run(row) -> SignalRun:
        return SignalRun(
            signal_run_id=str(row["signal_run_id"]),
            research_run_id=str(row["research_run_id"]),
            graph_version=row["graph_version"],
            model=row["model"],
            status=SignalRunStatus(row["status"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error=row["error"],
        )
