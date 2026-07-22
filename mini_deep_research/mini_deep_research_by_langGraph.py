from __future__ import annotations

import json
import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph

if __package__:
    from . import ReportData, WebSearchPlan, get_research_components, parse_search_plan
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mini_deep_research import (  # noqa: E402
        ReportData,
        WebSearchPlan,
        get_research_components,
        parse_search_plan,
    )


def planner_node(state: MessagesState):
    """Generate a search plan and append it to the graph message state."""

    user_query = state["messages"][-1].content
    raw_plan = get_research_components().planner_chain.invoke({"query": user_query})
    plan: WebSearchPlan = parse_search_plan(raw_plan)

    return {
        "plan": plan,
        "messages": [AIMessage(content=plan.model_dump_json())],
    }

def search_node(state: MessagesState):
    plan_json = state["messages"][-1].content
    plan = WebSearchPlan.model_validate_json(plan_json)

    summaries = []
    for item in plan.searches:
        run = get_research_components().search_agent.invoke(
            {"messages": [HumanMessage(content=item.query)]}
        )
        msgs = run["messages"]
        # 取可读内容：也就是最后一条ToolMessage 或 AIMessage的内容
        readable = next(
            (m for m in reversed(msgs) if isinstance(m, (ToolMessage, AIMessage))),
            msgs[-1],
        )
        summaries.append(f'## {item.query}\n\n{readable.content}')
    combined = "\n\n".join(summaries)
    return {"messages": [AIMessage(content=combined)]}

def writer_node(state: MessagesState):
    original_query = state["messages"][0].content
    combined_summary = state["messages"][-1].content

    writer_input = (
        f'原始问题: {original_query}\n\n'
        f'搜索摘要：\n{combined_summary}'
    )

    report: ReportData = get_research_components().writer_chain.invoke({"query": writer_input})

    return {"messages": [AIMessage(content=json.dumps(report.model_dump(), ensure_ascii=False, indent=2))]}


def build_graph():
    """Build the LangGraph DeepResearch workflow."""

    builder = StateGraph(MessagesState)
    builder.add_node("planner_node", planner_node)
    builder.add_node("search_node", search_node)
    builder.add_node("writer_node", writer_node)

    builder.add_edge(START, "planner_node")
    builder.add_edge("planner_node", "search_node")
    builder.add_edge("search_node", "writer_node")
    builder.add_edge("writer_node", END)
    return builder.compile()


graph = build_graph()


def main() -> None:
    initial_state = {
        "messages": [HumanMessage(content="请生成一份关于人工智能伦理的研究报告")]
    }
    final_state = graph.invoke(initial_state)
    print(final_state["messages"][-1].content)


if __name__ == "__main__":
    main()
