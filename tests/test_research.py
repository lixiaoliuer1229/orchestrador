from datetime import datetime, timezone

import pytest
from langchain_core.messages import HumanMessage

from app.graphs.research.graph import build_graph
from app.graphs.research.models import Report, SearchItem, SearchPlan, Source
from app.graphs.research.search import TavilySearcher, _env_choice


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


def source(source_id: str, url: str, query: str, score: float = 0.8) -> Source:
    return Source(
        source_id=source_id,
        query=query,
        title=f"Source {source_id}",
        url=url,
        content="Evidence content",
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
    second = source("source-b", "https://example.org/b", "independent source")
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
    graph = build_graph(planner=planner, writer=writer, searcher=searcher)

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
    assert result["messages"][-1].content.startswith("# Report")
    assert "source-a" in writer.inputs[0]


@pytest.mark.asyncio
async def test_research_graph_returns_safe_failure_report_without_sources():
    planner = FakeRunnable(
        SearchPlan(
            searches=[SearchItem(query="only query", reason="needed evidence")]
        )
    )
    writer = FakeRunnable(Report(short_summary="must not run", markdown_report="x"))
    graph = build_graph(
        planner=planner,
        writer=writer,
        searcher=FakeSearcher(failures={"only query"}),
    )

    result = await graph.ainvoke({"messages": [HumanMessage(content="Question")]})

    assert result["report"].source_ids == []
    assert "未获得可用网页来源" in result["report"].short_summary
    assert writer.inputs == []


@pytest.mark.asyncio
async def test_research_graph_rejects_missing_question():
    graph = build_graph(
        planner=FakeRunnable(
            SearchPlan(searches=[SearchItem(query="unused", reason="unused")])
        ),
        writer=FakeRunnable(Report(short_summary="x", markdown_report="x")),
        searcher=FakeSearcher(),
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


def test_invalid_search_depth_is_rejected(monkeypatch):
    monkeypatch.setenv("RESEARCH_SEARCH_DEPTH", "unlimited")

    with pytest.raises(RuntimeError, match="RESEARCH_SEARCH_DEPTH"):
        _env_choice(
            "RESEARCH_SEARCH_DEPTH",
            "advanced",
            {"basic", "advanced", "fast", "ultra-fast"},
        )
