# orchestrador 🚀

> LangGraph 后端工程师实战项目 —— 从零搭建生产级多智能体系统

## 📌 项目简介

这是一个面向 **后端工程师** 的 LangGraph 学习与实战项目。与 LangChain 的传统 Chain 不同,
LangGraph 采用 **图结构（Graph）+ 状态机（State Machine）** 的方式构建智能体应用,
天然支持循环、分支、并行、人工介入（Human-in-the-loop）等复杂场景。

## 🗂️ 目录结构

```
orchestrador/
├── src/                    # 核心代码
│   ├── agents/             # 智能体定义
│   ├── chains/             # 传统链（旧范式，了解即可）
│   ├── graphs/             # LangGraph 状态机（主战场！）
│   ├── tools/              # 自定义工具（函数调用）
│   └── utils/              # 工具函数
├── tests/                  # 单元测试（后端工程师的修养）
├── notebooks/              # 实验性 Jupyter 笔记
├── examples/               # 可运行的示例脚本
├── docker-compose.yml      # 一键拉起依赖（向量库、Redis 等）
├── requirements.txt        # 依赖管理
├── .env.example            # 环境变量模板
├── main.py                 # 仓库根 CLI 入口
└── README.md               # 项目说明 + 学习路线图
```

## 🚀 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 等配置
```

### 3. 启动依赖服务（可选）

```bash
docker compose up -d
```

### 4. 运行示例

```bash
python main.py run examples/hello_graph.py
# 或直接：
python examples/hello_graph.py

# 运行 mini DeepResearch 示例（需要配置 Anthropic 和 Tavily 环境变量）
python -m examples.mini_deep_research
```

### 5. 仓库根 CLI（main.py）

```bash
python main.py info          # 项目信息
python main.py test          # 跑 pytest
python main.py docker-up     # 拉起依赖服务
python main.py docker-down   # 停止依赖服务
python main.py make install  # make <target>
python main.py shell         # 进 shell
```

## 🧭 学习路线图

| 阶段 | 主题 | 关键概念 | 对应模块 |
| ---- | ---- | -------- | -------- |
| L1 | LangChain 基础 | Prompt / LLM / OutputParser | `src/chains/` |
| L2 | 工具与函数调用 | Tool / ToolNode / bind_tools | `src/tools/` |
| L3 | LangGraph 入门 | StateGraph / Node / Edge | `src/graphs/` |
| L4 | 状态管理 | State / Reducer / Checkpoint | `src/graphs/state_schema.py` |
| L5 | 控制流 | Conditional Edge / Loop / Branch | `src/graphs/` |
| L6 | 人机协作 | interrupt_before / interrupt_after | `src/graphs/` |
| L7 | 多智能体 | Subgraph / Send / Handoff | `src/agents/` |
| L8 | 持久化 & Memory | MemoryStore / Sqlite / Redis | `src/graphs/` |
| L9 | 可观测性 | LangSmith / Logging / Tracing | `src/utils/` |
| L10 | 生产化部署 | FastAPI / Docker / Async | `examples/api_server.py` |

## 📚 推荐资源

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [LangChain Academy: LangGraph 课程](https://academy.langchain.com/)
- [LangGraph 示例库](https://github.com/langchain-ai/langgraph/tree/main/examples)

## 🧪 测试

```bash
pytest tests/ -v
# 或
python main.py test
```

## 📝 License

MIT
