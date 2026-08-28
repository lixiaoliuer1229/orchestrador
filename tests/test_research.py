from datetime import datetime, timezone
import hashlib

import pytest
from langchain_core.messages import HumanMessage

from app.graphs.research.graph import build_graph
from app.graphs.research.search import TavilySearcher, _env_choice
from app.research.models import (
    ClaimDraft,
    ClaimType,
    EvidenceDraft,
    Extraction,
    Report,
    SearchItem,
    SearchPlan,
    SourceDocument,
)


class FakeRunnable:
    def __init__(self, result):
        self.result = result
        self.inputs = []

    async def ainvoke(self, value):
        self.inputs.append(value)
        return self.result


class FakeSearcher:
    def __init__(self, responses=None, failures=None):
        self.responses = responses or {}
        self.failures = set(failures or [])
        self.queries = []

    async def search(self, item):
        self.queries.append(item.query)
        if item.query in self.failures:
            raise RuntimeError("provider unavailable")
        return self.responses.get(item.query, [])


class FakeRepo:
    def __init__(self):
        self.runs = []
        self.plans = []
        self.sources = []
        self.analyses = []
        self.completed = []
        self.failed = []

    def start(self, run):
        self.runs.append(run)

    def save_plan(self, run_id, plan):
        self.plans.append((run_id, plan))

    def save_sources(self, run_id, sources):
        self.sources.append((run_id, sources))

    def save_analysis(self, run_id, evidence, claims):
        self.analyses.append((run_id, evidence, claims))

    def complete(self, run_id, report, failures):
        self.completed.append((run_id, report, failures))

    def fail(self, run_id, error):
        self.failed.append((run_id, error))


def source(
    source_id: str,
    url: str,
    query: str,
    score: float = 0.8,
    content: str = "Evidence content",
) -> SourceDocument:
    return SourceDocument(
        source_id=source_id,
        canonical_url=url,
        title=f"Source {source_id}",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        queries=[query],
        score=score,
        retrieved_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_research_graph_plans_searches_and_writes_cited_report(monkeypatch):
    monkeypatch.setenv("RESEARCH_MAX_QUERIES", "3")
    planner = FakeRunnable(
        SearchPlan(
            searches=[
                SearchItem(query="official source", reason="primary evidence"),
                SearchItem(query="independent source", reason="cross-check"),
                SearchItem(query="failed source", reason="additional view"),
                SearchItem(query="trimmed source", reason="over configured limit"),
            ]
        )
    )
    first = source("source-a", "https://example.com/a", "official source", 0.7)
    duplicate = source("source-a", "https://example.com/a", "independent source", 0.9)
    second = source(
        "source-b",
        "https://example.org/b",
        "independent source",
        content="Independent evidence content",
    )
    searcher = FakeSearcher(
        responses={
            "official source": [first],
            "independent source": [duplicate, second],
        },
        failures={"failed source"},
    )
    writer = FakeRunnable(
        Report(
            short_summary="Summary",
            markdown_report="# Report\n\nSupported claim [source-a].",
            source_ids=["source-a", "invented-id"],
        )
    )
    extractor = FakeRunnable(
        Extraction(
            evidence=[
                EvidenceDraft(
                    key="ev1",
                    source_id="source-a",
                    excerpt="Evidence content",
                    confidence=0.9,
                )
            ],
            claims=[
                ClaimDraft(
                    statement="Supported claim",
                    claim_type=ClaimType.FACT,
                    evidence_keys=["ev1"],
                    confidence=0.9,
                )
            ],
        )
    )
    repo = FakeRepo()
    graph = build_graph(
        planner=planner,
        extractor=extractor,
        writer=writer,
        searcher=searcher,
        repo=repo,
        model_name="test-model",
    )

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Research this topic")]}
    )

    assert result["query"] == "Research this topic"
    assert len(result["plan"].searches) == 3
    assert searcher.queries == [
        "official source",
        "independent source",
        "failed source",
    ]
    assert [item.source_id for item in result["sources"]] == [
        "source-a",
        "source-b",
    ]
    assert result["sources"][0].score == 0.9
    assert result["failures"][0].query == "failed source"
    assert result["report"].source_ids == ["source-a"]
    assert len(result["evidence"]) == 1
    assert len(result["claims"]) == 1
    assert result["claims"][0].evidence_ids == [result["evidence"][0].evidence_id]
    assert result["messages"][-1].content.startswith("# Report")
    assert "source-a" in writer.inputs[0]
    assert repo.runs[0].model == "test-model"
    assert repo.completed[0][0] == result["run_id"]


@pytest.mark.asyncio
async def test_research_graph_returns_safe_failure_report_without_sources():
    planner = FakeRunnable(
        SearchPlan(
            searches=[SearchItem(query="only query", reason="needed evidence")]
        )
    )
    writer = FakeRunnable(Report(short_summary="must not run", markdown_report="x"))
    extractor = FakeRunnable(Extraction())
    repo = FakeRepo()
    graph = build_graph(
        planner=planner,
        extractor=extractor,
        writer=writer,
        searcher=FakeSearcher(failures={"only query"}),
        repo=repo,
        model_name="test-model",
    )

    result = await graph.ainvoke({"messages": [HumanMessage(content="Question")]})

    assert result["report"].source_ids == []
    assert "未获得可用网页来源" in result["report"].short_summary
    assert writer.inputs == []
    assert extractor.inputs == []
    assert len(repo.completed) == 1


@pytest.mark.asyncio
async def test_research_graph_does_not_write_report_from_unsupported_claims():
    planner = FakeRunnable(
        SearchPlan(searches=[SearchItem(query="query", reason="find evidence")])
    )
    item = source("source-a", "https://example.com/a", "query")
    extractor = FakeRunnable(
        Extraction(
            evidence=[
                EvidenceDraft(
                    key="invented",
                    source_id="source-a",
                    excerpt="This text is not in the source",
                    confidence=0.8,
                )
            ],
            claims=[
                ClaimDraft(
                    statement="Unsupported claim",
                    claim_type=ClaimType.FACT,
                    evidence_keys=["invented"],
                    confidence=0.8,
                )
            ],
        )
    )
    writer = FakeRunnable(Report(short_summary="must not run", markdown_report="x"))
    repo = FakeRepo()
    graph = build_graph(
        planner=planner,
        extractor=extractor,
        writer=writer,
        searcher=FakeSearcher(responses={"query": [item]}),
        repo=repo,
        model_name="test-model",
    )

    result = await graph.ainvoke({"messages": [HumanMessage(content="Question")]})

    assert result["claims"][0].verification_status.value == "unsupported"
    assert result["evidence"] == []
    assert "没有主张获得有效证据支持" in result["report"].short_summary
    assert writer.inputs == []
    assert len(repo.completed) == 1


@pytest.mark.asyncio
async def test_research_graph_rejects_missing_question():
    graph = build_graph(
        planner=FakeRunnable(
            SearchPlan(searches=[SearchItem(query="unused", reason="unused")])
        ),
        extractor=FakeRunnable(Extraction()),
        writer=FakeRunnable(Report(short_summary="x", markdown_report="x")),
        searcher=FakeSearcher(),
        repo=FakeRepo(),
        model_name="test-model",
    )

    with pytest.raises(ValueError, match="at least one message"):
        await graph.ainvoke({"messages": []})


def test_tavily_result_normalization_skips_invalid_entries():
    searcher = object.__new__(TavilySearcher)
    searcher.source_chars = 20
    item = SearchItem(query="test", reason="test normalization")

    sources = searcher._sources(
        item,
        [
            {
                "title": "Valid",
                "url": "https://example.com/page",
                "content": "abcdefghijklmnopqrstuvwxyz",
                "score": 0.75,
            },
            {"title": "Missing URL", "content": "ignored"},
        ],
    )

    assert len(sources) == 1
    assert sources[0].title == "Valid"
    assert sources[0].content == "abcdefghijklmnopqrst"
    assert sources[0].score == 0.75


def test_tavily_canonicalizes_tracking_urls():
    searcher = object.__new__(TavilySearcher)
    searcher.source_chars = 100
    item = SearchItem(query="test", reason="canonical URL")

    sources = searcher._sources(
        item,
        [
            {
                "title": "Tracked",
                "url": "HTTPS://Example.COM/page?utm_source=x&b=2&a=1#section",
                "content": "content",
            }
        ],
    )

    assert str(sources[0].canonical_url) == "https://example.com/page?a=1&b=2"


def test_invalid_search_depth_is_rejected(monkeypatch):
    monkeypatch.setenv("RESEARCH_SEARCH_DEPTH", "unlimited")

    with pytest.raises(RuntimeError, match="RESEARCH_SEARCH_DEPTH"):
        _env_choice(
            "RESEARCH_SEARCH_DEPTH",
            "advanced",
            {"basic", "advanced", "fast", "ultra-fast"},
        )
