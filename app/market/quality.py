"""Deterministic market-data quality checks."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from app.market.models import (
    ActionType,
    CorporateAction,
    DailyBar,
    FinancialFact,
    InstrumentStatus,
    IssueSeverity,
    QualityIssue,
    TradingDay,
)


def _issue(
    run_id: str,
    code: str,
    entity_type: str,
    entity_key: str,
    message: str,
    *,
    rejected: bool = True,
    observed: dict | None = None,
) -> QualityIssue:
    identity = f"{run_id}\0{code}\0{entity_type}\0{entity_key}"
    return QualityIssue(
        issue_id=hashlib.sha256(identity.encode()).hexdigest()[:24],
        ingestion_run_id=run_id,
        severity=IssueSeverity.ERROR if rejected else IssueSeverity.WARNING,
        code=code,
        entity_type=entity_type,
        entity_key=entity_key,
        message=message,
        rejected=rejected,
        observed=observed or {},
        created_at=datetime.now(timezone.utc),
    )


def check_bar(
    bar: DailyBar, trading_day: TradingDay | None = None
) -> list[QualityIssue]:
    key = f"{bar.instrument_id}:{bar.trade_date.isoformat()}"
    issues: list[QualityIssue] = []
    if (
        bar.low > min(bar.open, bar.close)
        or bar.high < max(bar.open, bar.close)
        or bar.low > bar.high
    ):
        issues.append(
            _issue(
                bar.ingestion_run_id,
                "invalid_ohlc",
                "daily_bar",
                key,
                "OHLC prices violate low <= open/close <= high",
                observed={
                    name: str(getattr(bar, name))
                    for name in ("open", "high", "low", "close")
                },
            )
        )
    if bar.suspended and (bar.volume != 0 or bar.turnover != 0):
        issues.append(
            _issue(
                bar.ingestion_run_id,
                "suspended_with_trades",
                "daily_bar",
                key,
                "Suspended instrument has non-zero volume or turnover",
            )
        )
    if trading_day is not None and (
        not trading_day.is_open or trading_day.trade_date != bar.trade_date
    ):
        issues.append(
            _issue(
                bar.ingestion_run_id,
                "bar_on_closed_day",
                "daily_bar",
                key,
                "Bar does not belong to an open trading day",
            )
        )
    if (
        bar.limit_up is not None
        and bar.limit_down is not None
        and bar.limit_down >= bar.limit_up
    ):
        issues.append(
            _issue(
                bar.ingestion_run_id,
                "invalid_price_limits",
                "daily_bar",
                key,
                "Limit-down price must be lower than limit-up price",
            )
        )
    return issues


def check_financial_fact(fact: FinancialFact) -> list[QualityIssue]:
    key = fact.fact_id
    if fact.announced_at.date() < fact.report_period:
        return [
            _issue(
                fact.ingestion_run_id,
                "announcement_before_period",
                "financial_fact",
                key,
                "Financial fact was announced before its report period ended",
            )
        ]
    return []


def check_action(action: CorporateAction) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if action.announced_at.date() > action.ex_date:
        issues.append(
            _issue(
                action.ingestion_run_id,
                "action_announced_after_ex_date",
                "corporate_action",
                action.action_id,
                "Corporate action was announced after its ex-date",
            )
        )
    if action.action_type == ActionType.CASH_DIVIDEND:
        if action.cash_amount is None or action.currency is None:
            issues.append(
                _issue(
                    action.ingestion_run_id,
                    "incomplete_cash_dividend",
                    "corporate_action",
                    action.action_id,
                    "Cash dividend requires amount and currency",
                )
            )
    elif action.ratio is None:
        issues.append(
            _issue(
                action.ingestion_run_id,
                "missing_action_ratio",
                "corporate_action",
                action.action_id,
                "Non-cash corporate action requires a ratio",
            )
        )
    return issues


def check_status(status: InstrumentStatus) -> list[QualityIssue]:
    key = f"{status.instrument_id}:{status.trade_date.isoformat()}"
    if status.is_star_st and not status.is_st:
        return [
            _issue(
                status.ingestion_run_id,
                "invalid_star_st_state",
                "instrument_status",
                key,
                "*ST status must also be marked as ST",
            )
        ]
    if status.suspended and (status.can_buy or status.can_sell):
        return [
            _issue(
                status.ingestion_run_id,
                "suspended_but_tradable",
                "instrument_status",
                key,
                "Suspended instrument cannot be marked buyable or sellable",
            )
        ]
    return []


def duplicate_issues(
    run_id: str, entity_type: str, keys: list[str]
) -> list[QualityIssue]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for key in keys:
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return [
        _issue(
            run_id,
            "duplicate_record",
            entity_type,
            key,
            "Duplicate record in ingestion batch",
        )
        for key in sorted(duplicates)
    ]
