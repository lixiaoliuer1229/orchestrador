from datetime import datetime, timezone

import pytest

from app.graphs.signals import build_graph
from app.research.models import (
    Claim,
    ClaimType,
    Evidence,
    ResearchRun,
    RunDetail,
    RunStatus,
    VerificationStatus,
)
from app.signals.models import (
    Exchange,
    InstrumentDraft,
    SignalCategory,
    SignalDirection,
    SignalDraft,
    SignalExtraction,
)
from app.signals.validate import normalize_instrument, validate_signals


NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)
RESEARCH_RUN_ID = "11111111-1111-1111-1111-111111111111"
SIGNAL_RUN_ID = "22222222-2222-2222-2222-222222222222"


def research_run() -> ResearchRun:
    return ResearchRun(
        run_id=RESEARCH_RUN_ID,
        query="研究贵州茅台",
        graph_version="research-v2",
        model="test-model",
        status=RunStatus.COMPLETED,
        started_at=NOW,
        completed_at=NOW,
    )


def claim(
    claim_id: str = "claim-a",
    status: VerificationStatus = VerificationStatus.SUPPORTED,
    confidence: float = 0.8,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        run_id=RESEARCH_RUN_ID,
        statement="公司盈利能力稳定",
        claim_type=ClaimType.FACT,
        evidence_ids=["evidence-a"],
        confidence=confidence,
        verification_status=status,
    )


def draft(claim_ids=None) -> SignalDraft:
    return SignalDraft(
        instrument=InstrumentDraft(
            symbol="600519", exchange=Exchange.XSHG, name="贵州茅台"
        ),
        category=SignalCategory.QUALITY,
        direction=SignalDirection.POSITIVE,
        strength=0.7,
        confidence=0.95,
        horizon_days=30,
        rationale="盈利能力形成正面质量信号",
        claim_ids=claim_ids or ["claim-a"],
    )


def test_normalize_instrument_supports_cn_and_us():
    cn = normalize_instrument("600519", Exchange.XSHG, " 贵州茅台 ")
    us = normalize_instrument("aapl", Exchange.XNAS, "Apple")

    assert cn.instrument_id == "XSHG:600519"
    assert cn.market.value == "CN"
    assert cn.currency.value == "CNY"
    assert us.instrument_id == "XNAS:AAPL"
    assert us.market.value == "US"
    assert us.currency.value == "USD"


def test_normalize_instrument_rejects_invalid_symbol():
    with pytest.raises(ValueError, match="six digits"):
        normalize_instrument("AAPL", Exchange.XSHG, None)


def test_signal_validation_binds_claims_and_caps_confidence():
    signals = validate_signals(
        SIGNAL_RUN_ID,
        research_run(),
        [claim(status=VerificationStatus.PARTIALLY_SUPPORTED, confidence=0.8)],
        {"evidence-a"},
        SignalExtraction(signals=[draft()]),
    )

    assert len(signals) == 1
    assert signals[0].instrument.instrument_id == "XSHG:600519"
    assert signals[0].confidence == pytest.approx(0.6)
    assert signals[0].signed_value == 0.7
    assert signals[0].claim_ids == ["claim-a"]
    assert (signals[0].expires_at - signals[0].effective_at).days == 30


def test_signal_validation_rejects_unknown_or_unsupported_claims():
    unknown = validate_signals(
        SIGNAL_RUN_ID,
        research_run(),
        [claim()],
        {"evidence-a"},
        SignalExtraction(signals=[draft(["invented-claim"])]),
    )
    unsupported = validate_signals(
        SIGNAL_RUN_ID,
        research_run(),
        [claim(status=VerificationStatus.UNSUPPORTED)],
        {"evidence-a"},
        SignalExtraction(signals=[draft()]),
    )

    assert unknown == []
    assert unsupported == []


class FakeExtractor:
    def __init__(self, result):
        self.result = result
        self.inputs = []

    async def ainvoke(self, value):
        self.inputs.append(value)
        return self.result


class FakeResearchRepo:
    def __init__(self, detail):
        self.detail = detail

    def get(self, run_id):
        return self.detail if run_id == RESEARCH_RUN_ID else None


class FakeSignalRepo:
    def __init__(self):
        self.started = []
        self.completed = []
        self.failed = []

    def start(self, run):
        self.started.append(run)

    def complete(self, run_id, signals):
        self.completed.append((run_id, signals))

    def fail(self, run_id, error):
        self.failed.append((run_id, error))


def detail(status=VerificationStatus.SUPPORTED) -> RunDetail:
    return RunDetail(
        run=research_run(),
        evidence=[
            Evidence(
                evidence_id="evidence-a",
                run_id=RESEARCH_RUN_ID,
                source_id="source-a",
                excerpt="公司盈利能力稳定",
                confidence=0.9,
            )
        ],
        claims=[claim(status=status)],
    )


@pytest.mark.asyncio
async def test_signal_graph_generates_and_persists_valid_signals():
    extractor = FakeExtractor(SignalExtraction(signals=[draft()]))
    repo = FakeSignalRepo()
    graph = build_graph(
        extractor=extractor,
        research_repo=FakeResearchRepo(detail()),
        signal_repo=repo,
        model_name="test-model",
    )

    result = await graph.ainvoke({"research_run_id": RESEARCH_RUN_ID})

    assert len(result["signals"]) == 1
    assert "claim-a" in extractor.inputs[0]
    assert repo.started[0].research_run_id == RESEARCH_RUN_ID
    assert repo.completed[0][1][0].signal_id == result["signals"][0].signal_id


@pytest.mark.asyncio
async def test_signal_graph_skips_model_without_eligible_claims():
    extractor = FakeExtractor(SignalExtraction(signals=[draft()]))
    repo = FakeSignalRepo()
    graph = build_graph(
        extractor=extractor,
        research_repo=FakeResearchRepo(detail(VerificationStatus.UNSUPPORTED)),
        signal_repo=repo,
        model_name="test-model",
    )

    result = await graph.ainvoke({"research_run_id": RESEARCH_RUN_ID})

    assert result["signals"] == []
    assert extractor.inputs == []
    assert repo.completed[0][1] == []


@pytest.mark.asyncio
async def test_signal_graph_rejects_unknown_research_run():
    graph = build_graph(
        extractor=FakeExtractor(SignalExtraction()),
        research_repo=FakeResearchRepo(None),
        signal_repo=FakeSignalRepo(),
        model_name="test-model",
    )

    with pytest.raises(ValueError, match="not found"):
        await graph.ainvoke({"research_run_id": RESEARCH_RUN_ID})
