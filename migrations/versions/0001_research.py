"""Create research evidence and audit tables.

Revision ID: 0001_research
Revises:
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_research"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("graph_version", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("search_plan", postgresql.JSONB()),
        sa.Column("report", postgresql.JSONB()),
        sa.Column("failures", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text()),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="research_runs_status_ck",
        ),
    )
    op.create_index("research_runs_started_idx", "research_runs", ["started_at"])
    op.create_index("research_runs_status_idx", "research_runs", ["status"])

    op.create_table(
        "source_documents",
        sa.Column("source_id", sa.String(24), primary_key=True),
        sa.Column("canonical_url", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text()),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("language", sa.String(16)),
        sa.Column("market", sa.String(32)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("source_documents_hash_idx", "source_documents", ["content_hash"])
    op.create_index(
        "source_documents_published_idx", "source_documents", ["published_at"]
    )

    op.create_table(
        "research_run_sources",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_runs.run_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            sa.String(24),
            sa.ForeignKey("source_documents.source_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("queries", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("score", sa.Float()),
    )

    op.create_table(
        "evidence",
        sa.Column("evidence_id", sa.String(24), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(24),
            sa.ForeignKey("source_documents.source_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text()),
        sa.Column("unit", sa.String(64)),
        sa.Column("currency", sa.String(16)),
        sa.Column("data_period", sa.String(64)),
        sa.Column("extraction_method", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("location", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="evidence_confidence_ck"
        ),
    )
    op.create_index("evidence_run_idx", "evidence", ["run_id"])
    op.create_index("evidence_source_idx", "evidence", ["source_id"])

    op.create_table(
        "claims",
        sa.Column("claim_id", sa.String(24), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(24), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("verification_status", sa.String(32), nullable=False),
        sa.Column("invalidation_reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "claim_type IN ('fact', 'derived', 'estimate', 'opinion', 'forecast')",
            name="claims_type_ck",
        ),
        sa.CheckConstraint(
            "verification_status IN ('unverified', 'supported', "
            "'partially_supported', 'conflicting', 'unsupported', 'stale')",
            name="claims_verification_ck",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="claims_confidence_ck"
        ),
    )
    op.create_index("claims_run_idx", "claims", ["run_id"])
    op.create_index("claims_status_idx", "claims", ["verification_status"])

    op.create_table(
        "claim_evidence",
        sa.Column(
            "claim_id",
            sa.String(24),
            sa.ForeignKey("claims.claim_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "evidence_id",
            sa.String(24),
            sa.ForeignKey("evidence.evidence_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("claim_evidence")
    op.drop_index("claims_status_idx", table_name="claims")
    op.drop_index("claims_run_idx", table_name="claims")
    op.drop_table("claims")
    op.drop_index("evidence_source_idx", table_name="evidence")
    op.drop_index("evidence_run_idx", table_name="evidence")
    op.drop_table("evidence")
    op.drop_table("research_run_sources")
    op.drop_index("source_documents_published_idx", table_name="source_documents")
    op.drop_index("source_documents_hash_idx", table_name="source_documents")
    op.drop_table("source_documents")
    op.drop_index("research_runs_status_idx", table_name="research_runs")
    op.drop_index("research_runs_started_idx", table_name="research_runs")
    op.drop_table("research_runs")
