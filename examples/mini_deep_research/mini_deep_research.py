"""Pipeline-Agent implementation of the mini DeepResearch workflow."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

if __package__:
    from . import (
        ReportData,
        ResearchComponents,
        WebSearchItem,
        WebSearchPlan,
        get_research_components,
        parse_search_plan,
    )
else:
    # Support `python examples/mini_deep_research/mini_deep_research.py`.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from examples.mini_deep_research import (  # noqa: E402
        ReportData,
        ResearchComponents,
        WebSearchItem,
        WebSearchPlan,
        get_research_components,
        parse_search_plan,
    )


def plan_searches(
    query: str,
    components: ResearchComponents | None = None,
) -> WebSearchPlan:
    """Generate the web-search plan for a research question."""

    components = components or get_research_components()
    return parse_search_plan(components.planner_chain.invoke({"query": query}))


def search(
    item: WebSearchItem,
    components: ResearchComponents | None = None,
) -> str | None:
    """Search one planned item and return its concise summary."""

    components = components or get_research_components()
    final_query = f"Search Item: {item.query}\nReason for searching: {item.reason}"
    try:
        result = components.search_agent.invoke(
            {"messages": [{"role": "user", "content": final_query}]}
        )
        return str(result["messages"][-1].content)
    except Exception:
        # A failed search should not prevent the remaining planned searches.
        return None


def perform_searches(
    search_plan: WebSearchPlan,
    components: ResearchComponents | None = None,
) -> list[str]:
    """Run each planned search and keep successful summaries."""

    return [
        result
        for item in search_plan.searches
        if (result := search(item, components)) is not None
    ]


def write_report(
    query: str,
    search_results: Sequence[str],
    components: ResearchComponents | None = None,
) -> ReportData:
    """Write a structured report from the original query and search summaries."""

    components = components or get_research_components()
    summary = "".join(search_results)
    final_query = f"Original query: {query}\nSummarized search results: {summary}"
    return components.writer_chain.invoke({"query": final_query})


def deepresearch(query: str) -> ReportData:
    """Run planning, searching, and report writing for one research topic."""

    components = get_research_components()
    search_plan = plan_searches(query, components)
    search_results = perform_searches(search_plan, components)
    report = write_report(query, search_results, components)
    print(report.markdown_report)
    return report


def main() -> None:
    deepresearch("AI在教育方面的应用场景")


if __name__ == "__main__":
    main()
