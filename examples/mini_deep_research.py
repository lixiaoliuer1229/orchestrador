"""
基于 Pipeline-Agent 架构编写多智能体 DeepResearch 应用。

整个程序大致分为三个阶段：

1. 规划阶段：根据用户问题生成多个搜索关键词。
2. 搜索阶段：调用 Tavily 搜索工具，收集每个关键词对应的资料摘要。
3. 写作阶段：把原始问题和搜索结果交给大模型，生成结构化研究报告。

注意：本示例中的代码会在文件被执行时立即发起模型请求。如果这个文件被其他文件
import，也会执行这些顶层代码；在生产项目中通常会把执行入口放进 main() 函数中。
"""

# ============================== 1. 导入依赖 ==============================
import os

# python-dotenv：从 .env 文件中读取环境变量。
from dotenv import load_dotenv

# ChatAnthropic：LangChain 对 Anthropic Messages API 的封装。
# 只要底层网关兼容 Anthropic 协议，就可以通过 base_url 使用自定义网关。
from langchain_anthropic import ChatAnthropic

# PydanticOutputParser：把模型返回的普通文本解析成 Pydantic 对象。
# 这种方式不依赖模型服务端的 Tool Calling / JSON Schema 能力。
from langchain_core.output_parsers import PydanticOutputParser

# ChatPromptTemplate：组合 system prompt、human prompt 等聊天消息模板。
from langchain_core.prompts import ChatPromptTemplate

# BaseModel 用来定义结构化数据；Field 用来补充字段描述；
# SecretStr 用来包装 API Key，降低误打印密钥的风险。
from pydantic import BaseModel, Field, SecretStr

# TavilySearch：可以被 Agent 调用的网页搜索工具。
from langchain_tavily import TavilySearch

# create_agent：LangChain 新版本推荐的 Agent 创建方法。
from langchain.agents import create_agent


# ============================== 2. 加载配置 ==============================

# 读取 .env 文件中的配置。
# override=True 表示：如果系统环境变量和 .env 中有同名变量，优先使用 .env 的值。
load_dotenv(override=True)

# 读取模型服务所需的三个配置：
# - ANTHROPIC_API_KEY：调用模型服务的密钥
# - ANTHROPIC_BASE_URL：API 请求地址；为空时使用 SDK 默认地址
# - ANTHROPIC_MODEL：要调用的模型名称
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL")
anthropic_model = os.getenv("ANTHROPIC_MODEL")

# API Key 和模型名称是程序运行的最低配置。
# 在启动阶段主动检查，比运行到中途才发现配置错误更容易排查。
if not anthropic_api_key or not anthropic_model:
    raise ValueError(
        "ANTHROPIC_API_KEY and ANTHROPIC_MODEL must be set in the project's .env file."
    )

# ============================== 3. 创建模型 ==============================

# 创建一个可以被 LangChain 调用的聊天模型对象。
#
# model_name：当前 langchain-anthropic 版本中用于指定模型的参数名。
# api_key：SecretStr 只是对密钥做一层安全包装，不会改变密钥本身。
# base_url：允许把请求发送到自定义网关，而不是 Anthropic 官方地址。
model = ChatAnthropic(
    model_name=anthropic_model,
    api_key=SecretStr(anthropic_api_key),
    base_url=anthropic_base_url or None,
)

# ============================== 4. 定义规划提示词 ==============================

# 规划阶段的系统提示词。
# 它告诉模型：针对用户问题生成 5～7 个搜索词，并说明每个搜索词为什么重要。
PLANNER_INSTRUCTIONS = (
    "你是一名专业的研究规划助手。给定一个研究问题，请设计一组网页搜索关键词，"
    "以便尽可能全面、准确地回答这个问题。请生成 5 到 7 个搜索项，"
    "并为每个搜索项说明它为什么对回答原始问题很重要。"
)

# from_messages() 创建一个聊天提示词模板。
#
# system：系统消息，定义模型的角色和总体任务。
# human：用户消息，{query} 是运行时才填充的变量。
# {format_instructions} 也是运行时变量，稍后由 PydanticOutputParser 自动生成并填入。
planner_prompt = ChatPromptTemplate.from_messages([
    ("system", PLANNER_INSTRUCTIONS + "\n\n{format_instructions}"),
    ("human",  "{query}")
])

# ============================== 5. 定义规划结果的数据结构 ==============================

# BaseModel 是 Pydantic 的基础类。
# 继承 BaseModel 后，Pydantic 会根据字段声明对模型返回的数据进行解析和校验。
class WebSearchItem(BaseModel):
    # query：真正要交给搜索引擎的关键词。
    query: str = Field(description="用于网页搜索的关键词。")

    # reason：解释为什么这个关键词有助于回答原始问题。
    reason: str = Field(description="说明这个搜索关键词为什么有助于回答原始问题。")


class WebSearchPlan(BaseModel):
    # searches 是一个列表，列表中的每个元素都必须是 WebSearchItem 类型。
    # 例如：
    # {
    #     "searches": [
    #         {"query": "AI 教育应用", "reason": "了解主要应用场景"}
    #     ]
    # }
    searches: list[WebSearchItem] = Field(
        description="为了尽可能全面回答原始问题而需要执行的网页搜索列表。"
    )


# ============================== 6. 创建规划链 ==============================

# 把 Pydantic 模型交给输出解析器。
# 解析器负责把模型返回的 JSON 文本解析成 WebSearchPlan，并校验字段类型。
planner_parser = PydanticOutputParser(pydantic_object=WebSearchPlan)

# 这是一段手写的中文格式说明，用来告诉模型应该返回怎样的 JSON。
# 这里没有直接使用 parser.get_format_instructions()，因为该方法生成的说明通常是英文。
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
      "reason": "选择这个关键词的原因"
    }
  ]
}
"""

# partial() 可以提前为提示词模板填充固定变量。
# 之后每次调用 planner_chain 时，只需要传入 query 即可。
planner_prompt = planner_prompt.partial(
    format_instructions=PLANNER_FORMAT_INSTRUCTIONS
)

# LangChain 的 | 是 Runnable 管道运算符，表示把前一步的输出交给下一步：
#
# 输入字典
#   -> planner_prompt：生成消息
#   -> model：调用大模型
#   -> planner_parser：把模型文本解析成 WebSearchPlan
#
# 由于当前网关不支持 with_structured_output() 所需的工具调用参数，
# 这里采用“普通文本输出 + 本地 Pydantic 解析”的方式实现结构化结果。
planner_chain = planner_prompt | model | planner_parser

# 直接调用一次规划链，用于演示。
# invoke() 是同步调用，会等待模型返回结果。
# 返回值 planner_result 的类型应该是 WebSearchPlan，而不是普通字符串。
planner_result = planner_chain.invoke({'query': '请问你对AI+教育有何看法'})

# ============================== 7. 定义搜索 Agent ==============================

# 搜索 Agent 的系统提示词。
# Agent 每次接收一个搜索项，调用 TavilySearch，然后把搜索结果整理成简短摘要。
SEARCH_INSTRUCTIONS = (
    "你是一名网络研究助手。给定一个搜索项，请使用可用的网页搜索工具搜索相关内容，"
    "并对搜索结果进行简洁、准确的总结。总结应包含 2 到 3 个段落，长度不超过 300 字。"
    "请提炼搜索结果中的主要观点，表达简洁即可，不需要使用完整句子，也不要添加无关内容。"
    "这些总结将交给另一名研究员，用于整合成最终报告，因此请重点保留核心信息，忽略冗余内容。"
    "除了总结本身，不要输出任何额外说明。"
)

# 创建 Tavily 搜索工具。
# max_results=5：每次搜索最多返回 5 条结果。
# topic="general"：使用通用搜索主题。
search_tool = TavilySearch(max_results=5, topic="general")

# 创建搜索 Agent。
#
# model：Agent 使用的语言模型。
# tools：Agent 可以调用的外部工具列表，这里只有 Tavily 搜索。
# system_prompt：告诉 Agent 什么时候以及如何使用搜索工具。
search_agent = create_agent(
    model,
    tools=[search_tool],
    system_prompt=SEARCH_INSTRUCTIONS,
)

# 从规划结果中取出第一个搜索关键词，作为搜索 Agent 的输入。
# Agent 的输入通常是一个包含 messages 的字典，每条消息包含 role 和 content。
search_agent_res = search_agent.invoke({
    'messages': [
        {
            'role': 'user',
            'content': planner_result.searches[0].query,
        }
    ]
})


# ============================== 8. 定义报告结果的数据结构 ==============================

# 报告生成链的最终返回结构。
#
# 这三个字段共同组成一份完整的研究结果：
# 1. short_summary：给读者快速了解报告内容的简短摘要。
# 2. markdown_report：完整的 Markdown 格式正文。
# 3. follow_up_questions：建议继续研究的问题列表。
class ReportData(BaseModel):
    """The structured result returned by the report-writing chain."""

    # Field(description=...) 的描述会参与生成格式说明，帮助模型理解字段用途。
    short_summary: str = Field(description="使用 Markdown 格式写成的报告简短摘要。")
    markdown_report: str = Field(description="使用 Markdown 格式写成的完整研究报告。")
    follow_up_questions: list[str] = Field(
        description="建议进一步研究的主题或问题列表。"
    )


# ============================== 9. 定义报告写作链 ==============================

# 写作阶段的系统提示词。
# 这里要求模型根据原始问题和搜索资料，先组织结构，再生成中文 Markdown 报告。
WRITER_PROMPT = (
    "你是一名资深研究员，负责针对一个研究问题撰写结构完整、内容连贯的研究报告。"
    "你将收到原始研究问题，以及研究助手收集的一些初步资料。\n"
    "请先设计报告的大纲，说明报告的结构和内容组织方式，然后再撰写完整报告并作为最终结果返回。\n"
    "最终结果必须使用 Markdown 格式，并且内容要详细、完整。目标篇幅为 10 到 20 页，至少 1500 字。"
    "最终报告必须使用中文撰写。"
)

# 写作提示词同样包含两个部分：
# - system：写作规则和输出格式要求
# - human：运行时传入待研究的问题和搜索结果
writer_prompt = ChatPromptTemplate.from_messages([
    ('system', WRITER_PROMPT + "\n\n{format_instructions}"),
    ('human', '{query}')
])

# 为 ReportData 创建输出解析器。
# 它会把模型返回的 JSON 文本转换成 ReportData 实例，并校验字段类型。
writer_parser = PydanticOutputParser(pydantic_object=ReportData)

# 写作链的中文 JSON 格式说明。
WRITER_FORMAT_INSTRUCTIONS = """
请严格按照以下要求返回结果：
1. 只返回一个合法的 JSON 对象，不要返回 Markdown 代码块，也不要添加额外解释。
2. JSON 对象必须包含以下三个字段：short_summary、markdown_report、follow_up_questions。
3. short_summary 必须是字符串，内容是报告的简短摘要。
4. markdown_report 必须是字符串，内容是完整的中文 Markdown 报告。
5. follow_up_questions 必须是字符串数组，每个元素都是建议进一步研究的问题或主题。

JSON 结构示例：
{
  "short_summary": "报告摘要",
  "markdown_report": "# 报告标题\\n\\n报告正文",
  "follow_up_questions": ["可以进一步研究的问题一", "可以进一步研究的问题二"]
}
"""

# 把 ReportData 的格式说明固定注入 writer_prompt。
writer_prompt = writer_prompt.partial(
    format_instructions=WRITER_FORMAT_INSTRUCTIONS
)


# 写作链的数据流：
# 输入 query
#   -> writer_prompt：生成包含格式要求的消息
#   -> model：生成普通文本
#   -> writer_parser：解析为 ReportData
#
# 这仍然实现了结构化输出，只是结构校验发生在本地，
# 而不是依赖网关的原生结构化输出功能。
writer_chain = writer_prompt | model | writer_parser


# ============================== 10. 封装各阶段函数 ==============================

# 生成关键词规划。
# 这个函数把“调用规划链”的细节封装起来，外部只需要传入一个问题。
def plan_searches(query: str) -> WebSearchPlan:
    # 返回值由 planner_parser 解析，因此类型是 WebSearchPlan。
    result = planner_chain.invoke({'query': query})
    return result

# 根据一个关键词进行搜索。
def search(item: WebSearchItem) -> str | None:
    # str | None 表示：成功时返回字符串，失败时返回 None。
    try:
        # 同时把关键词和搜索理由传给 Agent，帮助 Agent 理解搜索目标。
        final_query = f"Search Item: {item.query}\nReason for searching: {item.reason}"

        # Agent 会根据 system_prompt 自主判断是否调用 TavilySearch。
        result = search_agent.invoke({"messages":[
            {
                "role": "user",
                "content": final_query
            }
        ]})

        # Agent 返回的是一个包含 messages 的字典。
        # 最后一条消息通常是 Agent 汇总搜索结果后的最终回答。
        return str(result['messages'][-1].content)
    except Exception:
        # 当前示例选择跳过失败的单次搜索，让其他关键词继续执行。
        # 生产环境通常应该记录异常原因，而不是完全忽略异常。
        return None

# 根据关键词列表逐个搜索，得到搜索结果列表。
def perform_searches(search_plan: WebSearchPlan):
    # 用普通 list 保存每个搜索项对应的摘要文本。
    results = []

    # search_plan.searches 中的每一项都是 WebSearchItem。
    for item in search_plan.searches:
        result = search(item)
        if result is not None:
            results.append(result)

    return results

# 根据搜索结果列表和用户问题生成报告。
def write_report(query: str, search_results) -> ReportData:
    # 把多个搜索结果拼接成一个较大的上下文字符串。
    summary=''
    for search_result in search_results:
        summary += search_result

    # 这里把原始问题和搜索摘要一起作为 writer_chain 的 query 输入。
    final_query = f'Original query: {query}\n Summarized search results: {summary}'

    # writer_chain 最终返回 ReportData 对象，而不是普通字符串。
    result = writer_chain.invoke({
        'query': final_query
    })
    return result

# 串联以上流程函数，形成完整的 DeepResearch 流程。
def deepresearch(query: str) -> ReportData:
    """
    输入一个研究主题，自动完成搜索规划、搜索和写报告。

    参数：
        query：用户想要研究的主题。

    返回：
        ReportData：包含摘要、Markdown 正文和后续研究问题。
    """
    # 第一步：让规划链生成搜索关键词。
    search_plan = plan_searches(query)

    # 第二步：根据每个关键词调用搜索 Agent。
    search_results = perform_searches(search_plan)

    # 第三步：把搜索结果交给写作链生成最终报告。
    report = write_report(query, search_results)

    # 这里先打印 Markdown 正文；调用方也可以直接使用 report 对象的其他字段。
    print(report.markdown_report)


# ============================== 11. 运行示例 ==============================

# 执行整个研究流程。
# 由于这是顶层代码，运行 Python 文件时会立即执行，并产生真实的模型/搜索请求。
deepresearch('AI在教育方面的应用场景')
