from datetime import datetime, timezone

from app.research.evidence import validate_extraction
from app.research.models import (
    ClaimDraft,
    ClaimType,
    EvidenceDraft,
    Extraction,
    SourceDocument,
    VerificationStatus,
)


def source() -> SourceDocument:
    return SourceDocument(
        source_id="source-1",
        canonical_url="https://example.com/report",
        title="Annual report",
        retrieved_at=datetime.now(timezone.utc),
        content="Revenue increased by 20 percent during fiscal year 2025.",
        content_hash="hash",
    )


def test_only_verbatim_evidence_is_accepted():
    extraction = Extraction(
        evidence=[
            EvidenceDraft(
                key="valid",
                source_id="source-1",
                excerpt="Revenue increased by 20 percent",
                normalized_value="20",
                unit="percent",
                confidence=0.95,
            ),
            EvidenceDraft(
                key="invented",
                source_id="source-1",
                excerpt="Profit doubled",
                confidence=0.7,
            ),
        ],
        claims=[
            ClaimDraft(
                statement="Revenue increased.",
                claim_type=ClaimType.FACT,
                evidence_keys=["valid"],
                confidence=0.9,
            ),
            ClaimDraft(
                statement="Profit doubled.",
                claim_type=ClaimType.FACT,
                evidence_keys=["invented"],
                confidence=0.7,
            ),
        ],
    )

    evidence, claims = validate_extraction("run-1", [source()], extraction)

    assert len(evidence) == 1
    assert evidence[0].normalized_value == "20"
    assert claims[0].verification_status == VerificationStatus.SUPPORTED
    assert claims[1].verification_status == VerificationStatus.UNSUPPORTED
    assert claims[1].evidence_ids == []


def test_missing_part_of_claim_evidence_is_partial():
    extraction = Extraction(
        evidence=[
            EvidenceDraft(
                key="valid",
                source_id="source-1",
                excerpt="fiscal year 2025",
                confidence=0.9,
            )
        ],
        claims=[
            ClaimDraft(
                statement="A derived conclusion",
                claim_type=ClaimType.DERIVED,
                evidence_keys=["valid", "missing"],
                confidence=0.6,
            )
        ],
    )

    _, claims = validate_extraction("run-1", [source()], extraction)

    assert claims[0].verification_status == VerificationStatus.PARTIALLY_SUPPORTED
