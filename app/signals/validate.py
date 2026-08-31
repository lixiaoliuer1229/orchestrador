"""Deterministic validation for model-proposed investment signals."""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from app.research.models import Claim, ResearchRun, VerificationStatus
from app.signals.models import (
    Currency,
    Exchange,
    Instrument,
    Market,
    Signal,
    SignalDirection,
    SignalExtraction,
)


_CN_EXCHANGES = {Exchange.XSHG, Exchange.XSHE, Exchange.BSE}
_US_EXCHANGES = {Exchange.XNYS, Exchange.XNAS, Exchange.XASE}


def normalize_instrument(symbol: str, exchange: Exchange, name: str | None) -> Instrument:
    normalized = symbol.strip().upper()
    if exchange in _CN_EXCHANGES:
        if not re.fullmatch(r"\d{6}", normalized):
            raise ValueError("Chinese equity symbols must contain exactly six digits")
        market, currency = Market.CN, Currency.CNY
    elif exchange in _US_EXCHANGES:
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", normalized):
            raise ValueError("US equity symbol is invalid")
        market, currency = Market.US, Currency.USD
    else:  # pragma: no cover - enum makes this defensive
        raise ValueError("unsupported exchange")
    return Instrument(
        instrument_id=f"{exchange.value}:{normalized}",
        symbol=normalized,
        exchange=exchange,
        market=market,
        currency=currency,
        name=name.strip() if name else None,
    )


def validate_signals(
    signal_run_id: str,
    research_run: ResearchRun,
    claims: list[Claim],
    evidence_ids: set[str],
    extraction: SignalExtraction,
) -> list[Signal]:
    """Return only signals fully backed by eligible claims from the research run."""

    eligible = {
        claim.claim_id: claim
        for claim in claims
        if claim.run_id == research_run.run_id
        and claim.evidence_ids
        and all(evidence_id in evidence_ids for evidence_id in claim.evidence_ids)
        and claim.verification_status
        in {VerificationStatus.SUPPORTED, VerificationStatus.PARTIALLY_SUPPORTED}
    }
    effective_at = research_run.completed_at or research_run.started_at
    signals: list[Signal] = []
    seen: set[str] = set()
    for draft in extraction.signals:
        requested = list(dict.fromkeys(draft.claim_ids))
        if not requested or any(claim_id not in eligible for claim_id in requested):
            continue
        try:
            instrument = normalize_instrument(
                draft.instrument.symbol,
                draft.instrument.exchange,
                draft.instrument.name,
            )
        except ValueError:
            continue
        claim_confidence = min(
            claim.confidence
            * (0.75 if claim.verification_status == VerificationStatus.PARTIALLY_SUPPORTED else 1)
            for claim in (eligible[claim_id] for claim_id in requested)
        )
        confidence = min(draft.confidence, claim_confidence)
        identity = "\0".join(
            [
                signal_run_id,
                instrument.instrument_id,
                draft.category.value,
                draft.direction.value,
                *sorted(requested),
            ]
        )
        signal_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        if signal_id in seen:
            continue
        seen.add(signal_id)
        signed_value = {
            SignalDirection.POSITIVE: draft.strength,
            SignalDirection.NEGATIVE: -draft.strength,
            SignalDirection.NEUTRAL: 0.0,
        }[draft.direction]
        signals.append(
            Signal(
                signal_id=signal_id,
                signal_run_id=signal_run_id,
                research_run_id=research_run.run_id,
                instrument=instrument,
                category=draft.category,
                direction=draft.direction,
                strength=draft.strength,
                signed_value=signed_value,
                confidence=confidence,
                effective_at=effective_at,
                expires_at=effective_at + timedelta(days=draft.horizon_days),
                rationale=draft.rationale.strip(),
                claim_ids=requested,
            )
        )
    return signals
