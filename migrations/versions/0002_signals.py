"""Create cross-market investment signal and lineage tables.

Revision ID: 0002_signals
Revises: 0001_research
Create Date: 2026-08-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_signals"
down_revision: Union[str, Sequence[str], None] = "0001_research"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("instrument_id", sa.String(64), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("exchange", sa.String(16), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("asset_type", sa.String(24), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("exchange", "symbol", name="instruments_exchange_symbol_uq"),
        sa.CheckConstraint("market IN ('CN', 'US')", name="instruments_market_ck"),
        sa.CheckConstraint(
            "exchange IN ('XSHG', 'XSHE', 'BSE', 'XNYS', 'XNAS', 'XASE')",
            name="instruments_exchange_ck",
        ),
        sa.CheckConstraint("currency IN ('CNY', 'USD')", name="instruments_currency_ck"),
        sa.CheckConstraint("asset_type IN ('equity')", name="instruments_asset_type_ck"),
    )
    op.create_index("instruments_market_idx", "instruments", ["market"])

    op.create_table(
        "signal_runs",
        sa.Column("signal_run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "research_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("graph_version", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')", name="signal_runs_status_ck"
        ),
    )
    op.create_index("signal_runs_research_idx", "signal_runs", ["research_run_id"])
    op.create_index("signal_runs_started_idx", "signal_runs", ["started_at"])

    op.create_table(
        "signals",
        sa.Column("signal_id", sa.String(24), primary_key=True),
        sa.Column(
            "signal_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signal_runs.signal_run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            sa.String(64),
            sa.ForeignKey("instruments.instrument_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("strength", sa.Numeric(5, 4), nullable=False),
        sa.Column("signed_value", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "category IN ('quality', 'growth', 'valuation', 'financial_safety', "
            "'industry', 'catalyst', 'risk', 'sentiment')",
            name="signals_category_ck",
        ),
        sa.CheckConstraint(
            "direction IN ('positive', 'negative', 'neutral')",
            name="signals_direction_ck",
        ),
        sa.CheckConstraint("strength >= 0 AND strength <= 1", name="signals_strength_ck"),
        sa.CheckConstraint(
            "signed_value >= -1 AND signed_value <= 1", name="signals_value_ck"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="signals_confidence_ck"
        ),
        sa.CheckConstraint("expires_at > effective_at", name="signals_expiry_ck"),
    )
    op.create_index("signals_instrument_time_idx", "signals", ["instrument_id", "effective_at"])
    op.create_index("signals_category_idx", "signals", ["category"])
    op.create_index("signals_expiry_idx", "signals", ["expires_at"])

    op.create_table(
        "signal_claims",
        sa.Column(
            "signal_id",
            sa.String(24),
            sa.ForeignKey("signals.signal_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "claim_id",
            sa.String(24),
            sa.ForeignKey("claims.claim_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index("signal_claims_claim_idx", "signal_claims", ["claim_id"])


def downgrade() -> None:
    op.drop_index("signal_claims_claim_idx", table_name="signal_claims")
    op.drop_table("signal_claims")
    op.drop_index("signals_expiry_idx", table_name="signals")
    op.drop_index("signals_category_idx", table_name="signals")
    op.drop_index("signals_instrument_time_idx", table_name="signals")
    op.drop_table("signals")
    op.drop_index("signal_runs_started_idx", table_name="signal_runs")
    op.drop_index("signal_runs_research_idx", table_name="signal_runs")
    op.drop_table("signal_runs")
    op.drop_index("instruments_market_idx", table_name="instruments")
    op.drop_table("instruments")
