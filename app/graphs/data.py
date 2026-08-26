"""Production read-only data agent."""

from langchain.agents import create_agent

from app.model_config import create_chat_model
from app.tools.sql import sql_inter


PROMPT = """
你是一名只读数据查询助手。你可以把用户的数据问题转换为一条安全的 MySQL
只读语句，并调用 `sql_inter` 获取结果。

安全边界：
- 仅允许 SELECT、SHOW、DESCRIBE/DESC 和 EXPLAIN。
- 禁止写入、删除、建表、修改结构、调用存储过程、锁表、文件读写和多语句。
- 不得尝试读取系统文件、环境变量、凭据或绕过数据库权限。
- 不得声称可以执行 Python、Shell 或任意绘图代码；这些能力没有开放。
- 数据库账号仍必须由部署环境配置为最小权限的只读账号。

回答要求：
- 使用简体中文，清晰、简洁地解释查询结果。
- `truncated=true` 表示结果达到服务端行数上限，必须提醒用户缩小查询范围。
- 不暴露连接信息、内部异常或凭据。
- 不能确认的数据不要编造。
"""

TOOLS = [sql_inter]


def create_graph(model_name: str | None = None):
    return create_agent(
        model=create_chat_model(model_name),
        tools=TOOLS,
        system_prompt=PROMPT,
    )


graph = create_graph()
