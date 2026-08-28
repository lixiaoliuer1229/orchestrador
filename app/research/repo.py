"""PostgreSQL repository for research audit data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from psycopg.types.json import Jsonb

from app.db import connect
from app.research.models import (
    Claim,
    Evidence,
    Report,
    ResearchRun,
    RunDetail,
    RunStatus,
    SearchFailure,
    SearchPlan,
    SourceDocument,
)


class ResearchRepo(Protocol):
    def start(self, run: ResearchRun) -> None: ...
    def save_plan(self, run_id: str, plan: SearchPlan) -> None: ...
    def save_sources(self, run_id: str, sources: list[SourceDocument]) -> None: ...
    def save_analysis(
        self, run_id: str, evidence: list[Evidence], claims: list[Claim]
    ) -> None: ...
    def complete(
        self, run_id: str, report: Report, failures: list[SearchFailure]
    ) -> None: ...
    def fail(self, run_id: str, error: str) -> None: ...
    def get(self, run_id: str) -> RunDetail | None: ...
    def list(self, limit: int, offset: int) -> list[ResearchRun]: ...


def _json(model) -> Jsonb:
    return Jsonb(model.model_dump(mode="json"))


class PostgresResearchRepo:
    def start(self, run: ResearchRun) -> None:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO research_runs(
                    run_id, query, graph_version, model, status, started_at,
                    config_snapshot, failures
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, '[]'::jsonb)
                """,
                (
                    UUID(run.run_id),
                    run.query,
                    run.graph_version,
                    run.model,
                    run.status.value,
                    run.started_at,
                    Jsonb(run.config_snapshot),
                ),
            )

    def save_plan(self, run_id: str, plan: SearchPlan) -> None:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE research_runs SET search_plan = %s WHERE run_id = %s",
                (_json(plan), UUID(run_id)),
            )

    def save_sources(self, run_id: str, sources: list[SourceDocument]) -> None:
        if not sources:
            return
        with connect() as connection, connection.cursor() as cursor:
            for source in sources:
                cursor.execute(
                    """
                    INSERT INTO source_documents(
                        source_id, canonical_url, title, publisher, source_type,
                        published_at, retrieved_at, content, content_hash,
                        language, market, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        publisher = COALESCE(EXCLUDED.publisher, source_documents.publisher),
                        source_type = EXCLUDED.source_type,
                        published_at = COALESCE(
                            EXCLUDED.published_at, source_documents.published_at
                        ),
                        retrieved_at = EXCLUDED.retrieved_at,
                        content = EXCLUDED.content,
                        content_hash = EXCLUDED.content_hash,
                        language = COALESCE(EXCLUDED.language, source_documents.language),
                        market = COALESCE(EXCLUDED.market, source_documents.market),
                        metadata = source_documents.metadata || EXCLUDED.metadata
                    """,
                    (
                        source.source_id,
                        str(source.canonical_url),
                        source.title,
                        source.publisher,
                        source.source_type.value,
                        source.published_at,
                        source.retrieved_at,
                        source.content,
                        source.content_hash,
                        source.language,
                        source.market,
                        Jsonb(source.metadata),
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO research_run_sources(run_id, source_id, queries, score)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (run_id, source_id) DO UPDATE SET
                        queries = EXCLUDED.queries,
                        score = EXCLUDED.score
                    """,
                    (
                        UUID(run_id),
                        source.source_id,
                        Jsonb(source.queries),
                        source.score,
                    ),
                )

    def save_analysis(
        self, run_id: str, evidence: list[Evidence], claims: list[Claim]
    ) -> None:
        with connect() as connection, connection.cursor() as cursor:
            for item in evidence:
                cursor.execute(
                    """
                    INSERT INTO evidence(
                        evidence_id, run_id, source_id, excerpt, normalized_value,
                        unit, currency, data_period, extraction_method, confidence,
                        location
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (evidence_id) DO NOTHING
                    """,
                    (
                        item.evidence_id,
                        UUID(run_id),
                        item.source_id,
                        item.excerpt,
                        item.normalized_value,
                        item.unit,
                        item.currency,
                        item.data_period,
                        item.extraction_method,
                        item.confidence,
                        Jsonb(item.location),
                    ),
                )
            for claim in claims:
                cursor.execute(
                    """
                    INSERT INTO claims(
                        claim_id, run_id, statement, claim_type, confidence,
                        verification_status, invalidation_reason
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (claim_id) DO NOTHING
                    """,
                    (
                        claim.claim_id,
                        UUID(run_id),
                        claim.statement,
                        claim.claim_type.value,
                        claim.confidence,
                        claim.verification_status.value,
                        claim.invalidation_reason,
                    ),
                )
                for evidence_id in claim.evidence_ids:
                    cursor.execute(
                        """
                        INSERT INTO claim_evidence(claim_id, evidence_id)
                        VALUES (%s, %s) ON CONFLICT DO NOTHING
                        """,
                        (claim.claim_id, evidence_id),
                    )

    def complete(
        self, run_id: str, report: Report, failures: list[SearchFailure]
    ) -> None:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE research_runs
                SET status = 'completed', completed_at = %s, report = %s, failures = %s
                WHERE run_id = %s
                """,
                (
                    datetime.now(timezone.utc),
                    _json(report),
                    Jsonb([item.model_dump(mode="json") for item in failures]),
                    UUID(run_id),
                ),
            )

    def fail(self, run_id: str, error: str) -> None:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE research_runs
                SET status = 'failed', completed_at = %s, error = %s
                WHERE run_id = %s
                """,
                (datetime.now(timezone.utc), error[:1_000], UUID(run_id)),
            )

    def get(self, run_id: str) -> RunDetail | None:
        run_uuid = UUID(run_id)
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM research_runs WHERE run_id = %s", (run_uuid,))
            row = cursor.fetchone()
            if not row:
                return None
            run = self._run(row)
            cursor.execute(
                """
                SELECT s.*, rs.queries, rs.score
                FROM source_documents s
                JOIN research_run_sources rs ON rs.source_id = s.source_id
                WHERE rs.run_id = %s ORDER BY s.retrieved_at, s.source_id
                """,
                (run_uuid,),
            )
            sources = [SourceDocument.model_validate(item) for item in cursor.fetchall()]
            cursor.execute(
                "SELECT * FROM evidence WHERE run_id = %s ORDER BY created_at, evidence_id",
                (run_uuid,),
            )
            evidence = [Evidence.model_validate(item) for item in cursor.fetchall()]
            cursor.execute(
                "SELECT * FROM claims WHERE run_id = %s ORDER BY created_at, claim_id",
                (run_uuid,),
            )
            claim_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT ce.claim_id, ce.evidence_id
                FROM claim_evidence ce
                JOIN claims c ON c.claim_id = ce.claim_id
                WHERE c.run_id = %s ORDER BY ce.claim_id, ce.evidence_id
                """,
                (run_uuid,),
            )
            links: dict[str, list[str]] = {}
            for link in cursor.fetchall():
                links.setdefault(link["claim_id"], []).append(link["evidence_id"])
            claims = [
                Claim.model_validate(
                    {**item, "evidence_ids": links.get(item["claim_id"], [])}
                )
                for item in claim_rows
            ]
        return RunDetail(run=run, sources=sources, evidence=evidence, claims=claims)

    def list(self, limit: int = 20, offset: int = 0) -> list[ResearchRun]:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM research_runs
                ORDER BY started_at DESC LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return [self._run(row) for row in cursor.fetchall()]

    @staticmethod
    def _run(row) -> ResearchRun:
        return ResearchRun(
            run_id=str(row["run_id"]),
            query=row["query"],
            graph_version=row["graph_version"],
            model=row["model"],
            status=RunStatus(row["status"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            config_snapshot=row["config_snapshot"] or {},
            plan=(
                SearchPlan.model_validate(row["search_plan"])
                if row["search_plan"]
                else None
            ),
            report=(Report.model_validate(row["report"]) if row["report"] else None),
            failures=[
                SearchFailure.model_validate(item) for item in row["failures"] or []
            ],
            error=row["error"],
        )
