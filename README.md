# Orchestrador

基于 FastAPI、LangChain 和 LangGraph 的统一 Agent API 服务。

## 项目目标

Orchestrador 的最终目标是构建一套面向 **多市场量化研究与交易**的智能化基座，首个落地市场为 A 股，未来可扩展至美股及其他市场。系统以 LangGraph 组织研究任务、理解公告新闻、生成并验证研究假设；以 Qlib 等确定性工具完成因子计算、模型训练、组合构建和回测；以独立的风控、订单管理和市场/券商适配层控制真实资金路径。

核心原则是：

> **量化引擎负责研究与回测，LangGraph 负责智能研究编排，独立风控服务负责审单，市场与券商适配器负责执行。**

LangGraph 是系统中的“研究员和流程调度员”，不是交易系统的最终控制器。LLM 可以生成带证据和有效期的候选信号，但不能直接决定下单数量、绕过风控或直接调用券商下单。行情采集、仓位计算、风险检查、订单状态和成交对账均由可测试、可重复的确定性程序负责。

### 目标架构

![Orchestrador 多市场智能量化研究与交易架构](docs/images/research-trading-architecture.svg)

可编辑图源：[research-trading-architecture.drawio](docs/images/research-trading-architecture.drawio)。

### Qlib 与智能研究层的互补关系

Qlib 和 LangGraph/AI Berkshire 方法论不互相替代，而是分别提供量化证据和基本面证据：

| 能力 | 量化研究引擎（首期 Qlib） | LangGraph 智能研究层 |
| --- | --- | --- |
| 主要输入 | 结构化行情、财务和因子数据 | 公告、财报、新闻、研报和网页资料 |
| 核心任务 | 因子计算、模型训练、收益预测、组合优化和回测 | 联网研究、事实抽取、来源交叉验证、多空审查和投资论文跟踪 |
| 主要输出 | 可复现的因子、预测分数和回测结果 | 带引用、置信度、风险和有效期的研究结论 |
| 擅长回答 | 信号在历史和样本外是否有效 | 公司为什么值得研究，风险和变化来自哪里 |
| 不负责 | 理解复杂叙事和最终交易执行 | 代替回测、确定仓位或直接下单 |

两层形成双向研究闭环：

1. Qlib 从股票池中发现异常因子和候选标的，触发 LangGraph 深度研究。
2. LangGraph 从财报、行业和新闻中提出可量化的假设，交给 Qlib 回测验证。
3. 两侧结果汇合为标准化候选信号，必须包含策略版本、有效期和 `evidence_ids`。
4. 候选信号只能进入独立的组合与风控层，不能直接成为券商订单。

AI Berkshire 中值得吸收的是研究纪律和工作流，包括财务数据交叉验证、公司/行业/财报研究、多角色反方审查、新闻异动归因以及投资论文漂移检测；具体大师人格、内容发布和写死的数据源不进入核心架构。

### 系统边界

- LangGraph 负责研究编排、工具调用、条件分支、任务恢复和人工审批。
- Qlib 或独立 Python 服务负责数据处理、因子、模型、回测及组合计算。
- Risk Engine 必须以确定性规则检查仓位、行业暴露、换手率、价格偏差、数据新鲜度和最大亏损，并通过市场规则适配器处理 T+1、整手、涨跌停、停牌等市场特有约束。
- OMS 和 Broker Adapter 独立于 LLM 运行；即使模型服务超时或宕机，订单同步、风控和对账仍应正常工作。
- LangGraph checkpoint 只保存研究流程状态，不作为订单、持仓或账户资金的权威账本。
- 数据版本、模型版本、Prompt 版本、策略版本、信号证据、风控结果、订单请求和券商回报必须可审计。

### 第一阶段范围

第一版以 A 股日频研究作为首个验证场景，但领域模型和接口不得写死为单一市场，也不直接追求盘中高频或无人值守实盘：

1. 收盘后更新并校验行情、财务、公告和新闻数据。
2. 使用 Qlib 计算因子、模型分数并完成历史回测。
3. 使用 LangGraph 联网研究异常标的，生成带来源的候选信号。
4. 由确定性组合和风控模块生成待审批订单。
5. 先运行回测和模拟盘，保留人工审批并完成每日成交、持仓与资金对账。
6. 经数月稳定模拟、故障恢复和极端行情测试后，再评估小资金自动执行。

当前仓库已经完成安全数据访问、联网研究、证据审计、标准化候选信号、市场数据导入，以及 point-in-time Qlib 数据适配。下一阶段是建立独立的 Qlib 运行环境，完成因子检验与回测；组合、风控和交易链路随后推进。

## API 入口

统一 Python 入口为：

```text
app.main:app
```

本地启动：

```bash
python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1
```

主要接口：

- `GET /`：数据与智能体控制台，可查看运行状态并发起 Graph 调用。
- `GET /runtime`：当前模型、端点类型、Graph 和超时配置。
- `GET /ok`：容器健康检查。
- `GET /health`：服务和 Graph 注册状态。
- `GET /graphs`：已注册 Graph 列表。
- `POST /graphs/{graph_name}/invoke`：调用指定 Graph。
- `GET /research/runs`：查询可追溯研究运行。
- `GET /signals`：按证券或研究运行查询候选信号。
- `GET /signals/{signal_id}`：查看 Signal → Claim → Evidence → Source 血缘。
- `GET /signals/runs/{signal_run_id}`：查看一次信号转换运行。
- `GET /docs`：OpenAPI 文档。
- `GET /images/{filename}`：数据分析生成的图片。

调用示例：

```bash
curl -X POST http://127.0.0.1:8000/graphs/chatbot/invoke \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "messages": [
        {"role": "user", "content": "你好"}
      ]
    },
    "config": {
      "configurable": {"thread_id": "demo-1"}
    }
  }'
```

生产容器使用单 worker Uvicorn，并由 Docker Compose 负责健康检查和异常重启。

## 目录结构

```text
app/
├── main.py              # FastAPI 统一入口和 Graph 注册
├── model_config.py      # 模型别名与客户端配置
├── auth.py              # 认证与用户管理
├── db.py                # PostgreSQL 连接配置
├── graphs/              # 正式 Agent / Graph
│   ├── chat.py
│   ├── data.py
│   ├── signals.py       # Claim 到候选 Signal 的受控转换
│   └── research/
│       ├── graph.py     # 规划、搜索和报告节点
│       ├── search.py    # 受控 Tavily 适配器
│       └── state.py     # ResearchState
└── tools/               # 权限受控、可独立测试的工具
    └── sql.py

app/research/            # 研究领域模型、证据校验和 Repository
app/signals/             # 证券、信号模型、校验和 Repository
app/market/              # 市场数据模型、Provider、质量规则和 Repository
app/qlib/                # Point-in-time CSV 导出和 Qlib binary 转换
migrations/              # Alembic 数据库迁移

tests/                   # API、Graph 与安全回归测试
```

`bak/` 仅保存历史练习和实验代码，不属于生产包。正式运行时代码、测试和文档不得依赖该目录；如需借鉴其中的实现，应在 `app/` 下重新设计并编写。

## 安装

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 配置

正式环境应直接注入以下环境变量：

- `APP_ENV=production`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`
- `ANTHROPIC_BASE_URL`（可选）

项目通过 Norotech Gateway 支持按请求切换以下基座模型：

- `coding-chat`（默认）
- `strong-chat`
- `cheap-chat`
- `minimax-latest`

调用 `POST /graphs/{graph_name}/invoke` 时可在 JSON 顶层传入 `model`；未传时使用
`ANTHROPIC_MODEL`。服务只接受上述白名单，前端控制台也提供对应的模型选择框。
- `TAVILY_API_KEY`

`research_agent` 使用受控的联网研究流程，相关限制可以通过以下变量调整：

- `RESEARCH_MAX_QUERIES`：单次研究最多搜索词数，默认 `5`，上限 `7`。
- `RESEARCH_RESULTS_PER_QUERY`：每个搜索词最多结果数，默认 `5`，上限 `10`。
- `RESEARCH_SEARCH_DEPTH`：Tavily 搜索深度，默认 `advanced`；可改为 `basic`、`fast` 或 `ultra-fast` 以控制成本和延迟。
- `RESEARCH_SEARCH_CONCURRENCY`：并发搜索数，默认 `3`，上限 `7`。
- `RESEARCH_SEARCH_TIMEOUT_SECONDS`：单次搜索超时，默认 `20` 秒，上限 `60` 秒。
- `RESEARCH_SEARCH_RETRIES`：单次搜索尝试次数，默认 `2`，上限 `4`。
- `RESEARCH_SOURCE_CHARS`：单个来源保留的最大正文字符数，默认 `6000`。
- `RESEARCH_CONTEXT_CHARS`：报告节点接收的总来源字符数，默认 `40000`。

`research_agent` 会持久化 `ResearchRun`、来源正文、Evidence、Claim 和最终报告。Evidence 摘录必须能在来源正文中定位；Claim 引用不存在或未通过定位校验的 Evidence 时，会被标记为 `partially_supported`、`unsupported` 或 `unverified`，不能静默视为已验证事实。

`signal_agent` 接收 `research_run_id`，只允许包含 Evidence 且状态为 `supported` 或 `partially_supported` 的 Claim 形成候选 Signal。它支持 A 股 `XSHG/XSHE/BSE` 与美股 `XNYS/XNAS/XASE` 证券标识，保存方向、强度、置信度、有效时间和完整血缘。部分支持的 Claim 会降低信号置信度；未知 Claim、无证据 Claim 和非法证券代码不会落库。候选 Signal 不能直接触发下单。

信号转换调用示例：

```bash
curl -X POST http://127.0.0.1:8000/graphs/signal_agent/invoke \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {"research_run_id": "11111111-1111-1111-1111-111111111111"}
  }'
```

`data_agent` 只能执行单条只读 MySQL 查询。生产环境必须使用数据库只读账号，并可通过以下变量收紧服务端限制：

- `DATA_AGENT_MAX_ROWS`：单次最多返回的记录数，默认 `500`，上限 `5000`。
- `DATA_AGENT_QUERY_TIMEOUT_MS`：查询及连接超时，默认 `10000` 毫秒，上限 `60000` 毫秒。

出于安全考虑，API 不向模型开放任意 Python、Shell 或绘图代码执行能力。

本地开发可以使用 `.env`：

```bash
cp .env.example .env
cp .env.postgres.example .env.postgres
# 编辑 .env，填入真实配置
```

系统环境变量的优先级高于 `.env`，真实密钥不要提交到 Git。

首次启动或更新版本时执行数据库迁移：

```bash
python -m alembic upgrade head
```

Docker 镜像会在启动 API 前自动执行迁移。研究数据通过 PostgreSQL 持久化，包含运行记录、来源原文、证据摘录、主张及其引用关系。

研究历史接口：

- `GET /research/runs`：分页查询研究运行记录。
- `GET /research/runs/{run_id}`：查看一次研究的来源、证据、主张和报告。

信号查询接口：

- `GET /signals`：分页查询信号，可按 `instrument_id` 或 `research_run_id` 筛选。
- `GET /signals/{signal_id}`：查看信号及关联 Evidence、Source ID。
- `GET /signals/runs/{signal_run_id}`：查看一次信号转换及其全部结果。

### 市场数据基础层

市场数据层采用供应商无关的 `MarketDataProvider` 协议，当前已定义并持久化证券主数据、交易日历、日频 OHLCV、复权因子、公司行为、A 股 ST/停牌及可买卖状态、财务事实、导入批次和质量问题。A 股证券使用 `XSHG/XSHE/BSE`，并保存对应的 Qlib 代码；数据结构同时支持美股交易所。

所有批量数据关联 `ingestion_run_id`。日线会检查 OHLC 关系、休市日数据、停牌成交和涨跌停边界；财务事实以 `announced_at` 控制时点可见性；不合格记录写入质量问题表，但不会进入正式数据表。目前仅完成领域和存储边界，尚未绑定真实行情供应商。

开发阶段可以通过确定性的 `MockMarketDataProvider` 填充合成 A 股数据。默认生成 2025 年 5 只模拟证券，并故意包含一条错误 OHLC 用于验证质量门控。所有证券名称和元数据均明确标记为模拟数据，不能用于评价真实策略收益。

只生成并查看数据量，不连接数据库：

```bash
python -m app.market.seed --dry-run
```

执行迁移后写入 PostgreSQL：

```bash
python -m alembic upgrade head
python -m app.market.seed
```

可以通过 `--start YYYY-MM-DD --end YYYY-MM-DD` 调整范围；使用 `--no-invalid` 可以不生成故意构造的错误记录。重复执行会通过主键 upsert 更新同一份合成数据，不会产生重复行情。

市场数据查询接口：

- `GET /market/instruments`：查询证券主数据，可按市场筛选。
- `GET /market/calendar`：查询指定交易所的交易日历。
- `GET /market/bars/{instrument_id}`：查询日频行情。
- `GET /market/actions/{instrument_id}`：查询公司行为。
- `GET /market/status/{instrument_id}`：查询停牌、ST 和可交易状态。
- `GET /market/financials/{instrument_id}`：按 `as_of` 时点查询当时已公告的财务事实。
- `GET /market/ingestions`：查询数据导入批次。
- `GET /market/ingestions/{run_id}/issues`：查询批次质量问题。

### Qlib 数据适配

Qlib 适配层会从 PostgreSQL 导出每只证券一个 CSV，基础字段为 `date/symbol/open/high/low/close/volume/money/factor`，并合并 `fund_*` 财务特征和 `signal_*` 研究信号。财务公告和 Signal 均按证券所在时区延迟到下一交易日生效；停牌日的行情、成交量和复权因子输出为空值。每次导出生成包含数据批次、字段及 SHA-256 的 `manifest.json`。

```bash
python -m app.qlib.export \
  --output data/qlib/source \
  --start 2025-01-01 \
  --end 2025-12-31
```

将 CSV 转换成 Qlib 本地存储布局：

```bash
python -m app.qlib.bin \
  --source data/qlib/source \
  --output data/qlib/bin
```

输出包含 `calendars/day.txt`、`instruments/all.txt` 和 `features/<symbol>/*.day.bin`。二进制输出目录必须为空，防止历史文件混入新数据集。当前项目 Python 为 3.14，而 Qlib 0.9.7 官方支持范围截至 Python 3.12，因此 Qlib 运行和模型训练后续将使用独立的 Python 3.12 环境；主 API 环境不直接安装 `pyqlib`。

## 测试

```bash
python -m pytest -q
```
