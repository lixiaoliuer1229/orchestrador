"""Shared building blocks for the mini DeepResearch examples.

The package keeps model construction lazy: importing these shared definitions
does not require credentials and does not send a request to an external
service.  Call :func:`get_research_components` when a workflow is executed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_tavily import TavilySearch
from pydantic import BaseModel, Field, SecretStr


class WebSearchItem(BaseModel):
    """A single search query and the reason it belongs in the research plan."""

    query: str = Field(description="用于网页搜索的关键词。")
    reason: str = Field(description="说明这个搜索关键词为什么有助于回答原始问题。")


class WebSearchPlan(BaseModel):
    """The list of searches generated for a research question."""

    searches: list[WebSearchItem] = Field(
        description="为了尽可能全面回答原始问题而需要执行的网页搜索列表。"
    )


class ReportData(BaseModel):
    """The structured result returned by the report-writing chain."""

    short_summary: str = Field(description="使用 Markdown 格式写成的报告简短摘要。")
    markdown_report: str = Field(description="使用 Markdown 格式写成的完整研究报告。")
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="建议进一步研究的主题或问题列表；没有时返回空数组。",
    )


PLANNER_INSTRUCTIONS = (
    "你是一名专业的研究规划助手。给定一个研究问题，请设计一组网页搜索关键词，"
    "以便尽可能全面、准确地回答这个问题。请生成 5 到 7 个搜索项，"
    "并为每个搜索项说明它为什么对回答原始问题很重要。"
)

PLANNER_FORMAT_INSTRUCTIONS = """
请严格按照以下要求返回结果：
1. 只返回一个合法的 JSON 对象，不要返回 Markdown 代码块，也不要添加额外解释。
2. JSON 对象必须包含 searches 字段，且 searches 必须是数组。
3. searches 数组中的每个元素都必须包含两个字符串字段：query 和 reason。
4. query 是搜索关键词，reason 是选择该关键词的原因。
5. 请生成 5 到 7 个搜索项。

JSON 结构示例：
{
  "searches": [
    {
      "query": "搜索关键词",
      "reason": "选择这个搜索关键词的原因"
    }
  ]
}
"""

SEARCH_INSTRUCTIONS = (
    "你是一名网络研究助手。给定一个搜索项，请使用可用的网页搜索工具搜索相关内容，"
    "并对搜索结果进行简洁、准确的总结。总结应包含 2 到 3 个段落，长度不超过 300 字。"
    "请提炼搜索结果中的主要观点，表达简洁即可，不需要使用完整句子，也不要添加无关内容。"
    "这些总结将交给另一名研究员，用于整合成最终报告，因此请重点保留核心信息，忽略冗余内容。"
    "除了总结本身，不要输出任何额外说明。"
)

WRITER_PROMPT = (
    "你是一名资深研究员，负责针对一个研究问题撰写结构完整、内容连贯的研究报告。"
    "你将收到原始研究问题，以及研究助手收集的一些初步资料。\n"
    "请先设计报告的大纲，说明报告的结构和内容组织方式，然后再撰写完整报告并作为最终结果返回。\n"
    "最终结果必须使用 Markdown 格式，并且内容要详细、完整。目标篇幅为 10 到 20 页，至少 1500 字。"
    "最终报告必须使用中文撰写。"
)

WRITER_FORMAT_INSTRUCTIONS = """
请严格按照以下要求返回结果：
1. 只返回一个合法的 JSON 对象，不要返回 Markdown 代码块，也不要添加额外解释。
2. JSON 对象必须包含以下三个字段：short_summary、markdown_report、follow_up_questions。
3. short_summary 必须是字符串，内容是报告的简短摘要。
4. markdown_report 必须是字符串，内容是完整的中文 Markdown 报告。
5. follow_up_questions 必须是字符串数组，每个元素都是建议进一步研究的问题或主题；
   如果没有补充问题，也必须返回空数组 []。

JSON 结构示例：
{
  "short_summary": "报告摘要",
  "markdown_report": "# 报告标题\\n\\n报告正文",
  "follow_up_questions": ["可以进一步研究的问题一", "可以进一步研究的问题二"]
}
"""


@dataclass(frozen=True)
class ResearchComponents:
    """Shared chains and agents used by the pipeline and graph examples."""

    planner_chain: Any
    search_agent: Any
    writer_chain: Any


def _create_model() -> ChatAnthropic:
    """Create the configured Anthropic-compatible chat model."""

    load_dotenv(override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model_name = os.getenv("ANTHROPIC_MODEL")
    if not api_key or not model_name:
        raise ValueError(
            "ANTHROPIC_API_KEY and ANTHROPIC_MODEL must be set in the project's .env file."
        )

    return ChatAnthropic(
        model_name=model_name,
        api_key=SecretStr(api_key),
        base_url=os.getenv("ANTHROPIC_BASE_URL") or None,
    )


@lru_cache(maxsize=1)
def get_research_components() -> ResearchComponents:
    """Build and cache the shared planner, search agent, and writer chain."""

    model = _create_model()

    planner_prompt = ChatPromptTemplate.from_messages([
        ("system", PLANNER_INSTRUCTIONS + "\n\n{format_instructions}"),
        ("human", "{query}"),
    ]).partial(format_instructions=PLANNER_FORMAT_INSTRUCTIONS)
    planner_parser = PydanticOutputParser(pydantic_object=WebSearchPlan)
    planner_chain = planner_prompt | model | planner_parser

    search_tool = TavilySearch(max_results=5, topic="general")
    search_agent = create_agent(
        model,
        tools=[search_tool],
        system_prompt=SEARCH_INSTRUCTIONS,
    )

    writer_prompt = ChatPromptTemplate.from_messages([
        ("system", WRITER_PROMPT + "\n\n{format_instructions}"),
        ("human", "{query}"),
    ]).partial(format_instructions=WRITER_FORMAT_INSTRUCTIONS)
    writer_parser = PydanticOutputParser(pydantic_object=ReportData)
    writer_chain = writer_prompt | model | writer_parser

    return ResearchComponents(
        planner_chain=planner_chain,
        search_agent=search_agent,
        writer_chain=writer_chain,
    )


def parse_search_plan(raw: Any) -> WebSearchPlan:
    """Normalize parser output so pipeline and graph nodes share one conversion."""

    if isinstance(raw, WebSearchPlan):
        return raw
    return WebSearchPlan.model_validate(raw)


__all__ = [
    "PLANNER_FORMAT_INSTRUCTIONS",
    "PLANNER_INSTRUCTIONS",
    "ReportData",
    "ResearchComponents",
    "SEARCH_INSTRUCTIONS",
    "WebSearchItem",
    "WebSearchPlan",
    "WRITER_FORMAT_INSTRUCTIONS",
    "WRITER_PROMPT",
    "get_research_components",
    "parse_search_plan",
]
