"""Deterministic validation for LLM-extracted evidence and claims."""

from __future__ import annotations

import hashlib
import re

from app.research.models import (
    Claim,
    ClaimType,
    Evidence,
    Extraction,
    SourceDocument,
    VerificationStatus,
)


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def validate_extraction(
    run_id: str,
    sources: list[SourceDocument],
    extraction: Extraction,
) -> tuple[list[Evidence], list[Claim]]:
    """Keep only verbatim-backed evidence and derive claim verification states."""

    source_map = {source.source_id: source for source in sources}
    evidence: list[Evidence] = []
    by_key: dict[str, str] = {}

    for draft in extraction.evidence:
        source = source_map.get(draft.source_id)
        if not source:
            continue
        excerpt = _normalized_text(draft.excerpt)
        if not excerpt or excerpt not in _normalized_text(source.content):
            continue
        evidence_id = hashlib.sha256(
            f"{run_id}\0{draft.source_id}\0{excerpt}".encode("utf-8")
        ).hexdigest()[:24]
        if evidence_id not in {item.evidence_id for item in evidence}:
            evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    run_id=run_id,
                    source_id=draft.source_id,
                    excerpt=draft.excerpt.strip(),
                    normalized_value=draft.normalized_value,
                    unit=draft.unit,
                    currency=draft.currency,
                    data_period=draft.data_period,
                    confidence=draft.confidence,
                    location=draft.location,
                )
            )
        by_key.setdefault(draft.key, evidence_id)

    claims: list[Claim] = []
    for draft in extraction.claims:
        requested = list(dict.fromkeys(draft.evidence_keys))
        evidence_ids = [by_key[key] for key in requested if key in by_key]
        if evidence_ids and len(evidence_ids) == len(requested):
            status = VerificationStatus.SUPPORTED
        elif evidence_ids:
            status = VerificationStatus.PARTIALLY_SUPPORTED
        elif draft.claim_type in {ClaimType.OPINION, ClaimType.FORECAST}:
            status = VerificationStatus.UNVERIFIED
        else:
            status = VerificationStatus.UNSUPPORTED
        statement = draft.statement.strip()
        claim_id = hashlib.sha256(
            f"{run_id}\0{draft.claim_type.value}\0{statement.casefold()}".encode("utf-8")
        ).hexdigest()[:24]
        claims.append(
            Claim(
                claim_id=claim_id,
                run_id=run_id,
                statement=statement,
                claim_type=draft.claim_type,
                evidence_ids=evidence_ids,
                confidence=draft.confidence,
                verification_status=status,
                invalidation_reason=(
                    "引用的证据不存在或无法在来源正文中定位"
                    if status == VerificationStatus.UNSUPPORTED
                    else None
                ),
            )
        )
    return evidence, claims
