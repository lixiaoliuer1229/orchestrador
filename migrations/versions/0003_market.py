"""Create provider-independent market data tables.

Revision ID: 0003_market
Revises: 0002_signals
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_market"
down_revision: Union[str, Sequence[str], None] = "0002_signals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("instruments_asset_type_ck", "instruments", type_="check")
    op.create_check_constraint(
        "instruments_asset_type_ck",
        "instruments",
        "asset_type IN ('equity', 'etf', 'index')",
    )
    op.add_column("instruments", sa.Column("qlib_code", sa.String(32)))
    op.add_column("instruments", sa.Column("listing_date", sa.Date()))
    op.add_column("instruments", sa.Column("delisting_date", sa.Date()))
    op.add_column(
        "instruments",
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
    )
    op.add_column("instruments", sa.Column("industry", sa.Text()))
    op.add_column("instruments", sa.Column("sector", sa.Text()))
    op.add_column(
        "instruments",
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
    )
    op.add_column(
        "instruments",
        sa.Column("lot_size", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "instruments",
        sa.Column("settlement_days", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "instruments",
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_unique_constraint(
        "instruments_qlib_code_uq", "instruments", ["qlib_code"]
    )
    op.create_check_constraint(
        "instruments_state_ck",
        "instruments",
        "state IN ('active', 'inactive', 'delisted')",
    )
    op.create_check_constraint("instruments_lot_size_ck", "instruments", "lot_size > 0")
    op.create_check_constraint(
        "instruments_settlement_ck", "instruments", "settlement_days BETWEEN 0 AND 3"
    )

    op.create_table(
        "data_ingestion_runs",
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("dataset", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("data_start", sa.Date()),
        sa.Column("data_end", sa.Date()),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("received_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.CheckConstraint("market IN ('CN', 'US')", name="ingestion_runs_market_ck"),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ingestion_runs_status_ck",
        ),
        sa.CheckConstraint(
            "received_count >= 0 AND accepted_count >= 0 AND rejected_count >= 0",
            name="ingestion_runs_counts_ck",
        ),
    )
    op.create_index("ingestion_runs_started_idx", "data_ingestion_runs", ["started_at"])

    op.create_table(
        "trading_calendars",
        sa.Column("exchange", sa.String(16), primary_key=True),
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("opens_at", sa.Time()),
        sa.Column("closes_at", sa.Time()),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("note", sa.Text()),
    )
    op.create_index("trading_calendars_date_idx", "trading_calendars", ["trade_date"])

    op.create_table(
        "daily_bars",
        sa.Column(
            "instrument_id",
            sa.String(64),
            sa.ForeignKey("instruments.instrument_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("open", sa.Numeric(20, 6), nullable=False),
        sa.Column("high", sa.Numeric(20, 6), nullable=False),
        sa.Column("low", sa.Numeric(20, 6), nullable=False),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.Column("prev_close", sa.Numeric(20, 6)),
        sa.Column("volume", sa.Numeric(24, 4), nullable=False),
        sa.Column("turnover", sa.Numeric(24, 4), nullable=False),
        sa.Column("adjustment_factor", sa.Numeric(20, 10), nullable=False),
        sa.Column("suspended", sa.Boolean(), nullable=False),
        sa.Column("limit_up", sa.Numeric(20, 6)),
        sa.Column("limit_down", sa.Numeric(20, 6)),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_ingestion_runs.ingestion_run_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name="daily_bars_prices_ck",
        ),
        sa.CheckConstraint(
            "volume >= 0 AND turnover >= 0", name="daily_bars_activity_ck"
        ),
        sa.CheckConstraint("adjustment_factor > 0", name="daily_bars_factor_ck"),
    )
    op.create_index("daily_bars_date_idx", "daily_bars", ["trade_date"])

    op.create_table(
        "corporate_actions",
        sa.Column("action_id", sa.String(24), primary_key=True),
        sa.Column(
            "instrument_id",
            sa.String(64),
            sa.ForeignKey("instruments.instrument_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_date", sa.Date()),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("cash_amount", sa.Numeric(20, 6)),
        sa.Column("ratio", sa.Numeric(20, 10)),
        sa.Column("currency", sa.String(8)),
        sa.Column("source_id", sa.String(24)),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_ingestion_runs.ingestion_run_id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.create_index(
        "corporate_actions_instrument_idx",
        "corporate_actions",
        ["instrument_id", "ex_date"],
    )

    op.create_table(
        "instrument_statuses",
        sa.Column(
            "instrument_id",
            sa.String(64),
            sa.ForeignKey("instruments.instrument_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("suspended", sa.Boolean(), nullable=False),
        sa.Column("is_st", sa.Boolean(), nullable=False),
        sa.Column("is_star_st", sa.Boolean(), nullable=False),
        sa.Column("can_buy", sa.Boolean(), nullable=False),
        sa.Column("can_sell", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_ingestion_runs.ingestion_run_id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )

    op.create_table(
        "financial_facts",
        sa.Column("fact_id", sa.String(24), primary_key=True),
        sa.Column(
            "instrument_id",
            sa.String(64),
            sa.ForeignKey("instruments.instrument_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric", sa.String(128), nullable=False),
        sa.Column("report_period", sa.Date(), nullable=False),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(30, 8), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8)),
        sa.Column("restatement", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_id", sa.String(24)),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_ingestion_runs.ingestion_run_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.CheckConstraint("restatement >= 0", name="financial_facts_restatement_ck"),
    )
    op.create_index(
        "financial_facts_point_in_time_idx",
        "financial_facts",
        ["instrument_id", "metric", "announced_at"],
    )

    op.create_table(
        "data_quality_issues",
        sa.Column("issue_id", sa.String(24), primary_key=True),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_ingestion_runs.ingestion_run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_key", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("rejected", sa.Boolean(), nullable=False),
        sa.Column("observed", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "quality_issues_run_idx", "data_quality_issues", ["ingestion_run_id"]
    )
    op.create_index("quality_issues_code_idx", "data_quality_issues", ["code"])


def downgrade() -> None:
    op.drop_index("quality_issues_code_idx", table_name="data_quality_issues")
    op.drop_index("quality_issues_run_idx", table_name="data_quality_issues")
    op.drop_table("data_quality_issues")
    op.drop_index("financial_facts_point_in_time_idx", table_name="financial_facts")
    op.drop_table("financial_facts")
    op.drop_table("instrument_statuses")
    op.drop_index("corporate_actions_instrument_idx", table_name="corporate_actions")
    op.drop_table("corporate_actions")
    op.drop_index("daily_bars_date_idx", table_name="daily_bars")
    op.drop_table("daily_bars")
    op.drop_index("trading_calendars_date_idx", table_name="trading_calendars")
    op.drop_table("trading_calendars")
    op.drop_index("ingestion_runs_started_idx", table_name="data_ingestion_runs")
    op.drop_table("data_ingestion_runs")
    op.drop_constraint("instruments_settlement_ck", "instruments", type_="check")
    op.drop_constraint("instruments_lot_size_ck", "instruments", type_="check")
    op.drop_constraint("instruments_state_ck", "instruments", type_="check")
    op.drop_constraint("instruments_qlib_code_uq", "instruments", type_="unique")
    for column in (
        "metadata",
        "settlement_days",
        "lot_size",
        "timezone",
        "sector",
        "industry",
        "state",
        "delisting_date",
        "listing_date",
        "qlib_code",
    ):
        op.drop_column("instruments", column)
    op.drop_constraint("instruments_asset_type_ck", "instruments", type_="check")
    op.create_check_constraint(
        "instruments_asset_type_ck", "instruments", "asset_type IN ('equity')"
    )
