"""A minimal, standalone model setup for learning purposes."""
import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, SecretStr
from langchain_tavily import TavilySearch
from langchain.agents import create_agent

load_dotenv(override=True)

anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL")
anthropic_model = os.getenv("ANTHROPIC_MODEL")


if not anthropic_api_key or not anthropic_model:
    raise ValueError(
        "ANTHROPIC_API_KEY and ANTHROPIC_MODEL must be set in the project's .env file."
    )

model = ChatAnthropic(
    model_name=anthropic_model,
    api_key=SecretStr(anthropic_api_key),
    base_url=anthropic_base_url or None,
)

PLANNER_INSTRUCTIONS = (
    "You are a helpful research assistant, Given a query, come up with a set of web searches "
    "to perform to best answer the query, Output between 5 and 7 terms to query for."
)

planner_prompt = ChatPromptTemplate.from_messages([
    ("system", PLANNER_INSTRUCTIONS + "\n\n{format_instructions}"),
    ("human",  "{query}")
])

class WebSearchItem(BaseModel):
    query: str
    "The search term to use for the web search."
    "用于网络搜索的关键词"

    reason: str
    "You reasoning for why this search is important to the query."
    "为什么这个搜索对于解答该问题很重要的理由"

class WebSearchPlan(BaseModel):
    searches: list[WebSearchItem]
    "A list of web searches to perform to best answer the query"
    "为了尽可能全面回答该问题而需要执行的网页搜索列表"

planner_parser = PydanticOutputParser(pydantic_object=WebSearchPlan)

planner_prompt = planner_prompt.partial(
    format_instructions=planner_parser.get_format_instructions()
)

planner_chain = planner_prompt | model | planner_parser

planner_result = planner_chain.invoke({'query': '请问你对AI+教育有何看法'})

SEARCH_INSTRUCTIONS = (
    "You are a research assistant. Given a search term, you search the web for that term and "
    "produce a concise summary of the results. The summary must 2-3 paragraphs and less than 300"
    "words. Capture the main points. Write succinctly, no need to have complete sentences or good"
    "grammar. This will be consumed by someone synthesizing a report, so its vital you capture the "
    "essence and ignore any fluff. Do not include any additional commentary other than the summary itself."
)

search_tool = TavilySearch(max_results=5, topic="general")

search_agent = create_agent(
    model,
    tools=[search_tool],
    system_prompt=SEARCH_INSTRUCTIONS,
)

search_agent_res = search_agent.invoke({'messages': [{'role': 'user', "content": planner_result.searches[0].query}]})


class ReportData(BaseModel):
    """The structured result returned by the report-writing chain."""

    short_summary: str = Field(description="A brief summary of the report in Markdown format.")
    markdown_report: str = Field(description="The complete research report in Markdown format.")
    follow_up_questions: list[str] = Field(
        description="Suggested topics or questions for further research."
    )


WRITER_PROMPT = (
    "You are a senior researcher tasked with writing a cohesive report for a research query."
    "You will be provided with the original query, and some initial research done by a research assistant. \n"
    "You should first come up with an outline for the report that describes the structure and flow of the report. Then, "
    "generate the report and return that as your final output. \n The final output should be in markdown format, and it should"
    "be lengthy and detailed. Aim for 10-20 pages of content, at least 1500 words. 最终生成的报告采用中文输出."
)

writer_prompt = ChatPromptTemplate.from_messages([
    ('system', WRITER_PROMPT + "\n\n{format_instructions}"),
    ('human', '{query}')
])

writer_parser = PydanticOutputParser(pydantic_object=ReportData)
writer_prompt = writer_prompt.partial(
    format_instructions=writer_parser.get_format_instructions()
)


writer_chain = writer_prompt | model | writer_parser


# 生成关键词规划
def plan_searches(query: str) -> WebSearchPlan:
    result = planner_chain.invoke({'query': query})
    return result

# 根据关键词进行搜索
def search(item:WebSearchItem) -> str | None:
    try:
        final_query = f"Search Item: {item.query}\nReason for searching: {item.reason}"
        result = search_agent.invoke({"messages":[
            {
                "role": "user",
                "content": final_query
            }
        ]})
        return str(result['messages'][-1].content)
    except Exception:
        return None

# 根据关键词列表逐个搜索得到搜索结果列表
def perform_searches(search_plan: WebSearchPlan):
    results = []
    for item in search_plan.searches:
        result = search(item)
        if result is not None:
            results.append(result)
    return results

# 根据搜索的结果列表和用户提问生成报告
def write_report(query: str, search_results) -> ReportData:
    summary=''
    for search_result in search_results:
        summary += search_result
    final_query = f'Original query: {query}\n Summarized search results: {summary}'
    result = writer_chain.invoke({
        'query': final_query
    })
    return result

# 串联以上流程函数
def deepresearch(query: str) -> ReportData:
    '''
    输入一个研究主题，自动完成搜索规划、搜索和写报告
    返回最终的ReportData对象，就是一个markdown的格式完整的研究报告文档
    '''
    search_plan = plan_searches(query)
    search_results = perform_searches(search_plan)
    report = write_report(query, search_results)
    print(report.markdown_report)


deepresearch('AI在教育方面的应用场景')
