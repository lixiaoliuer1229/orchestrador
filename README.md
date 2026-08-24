# Orchestrador

基于 FastAPI、LangChain 和 LangGraph 的统一 Agent API 服务。

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

- `GET /ok`：容器健康检查。
- `GET /health`：服务和 Graph 注册状态。
- `GET /graphs`：已注册 Graph 列表。
- `POST /graphs/{graph_name}/invoke`：调用指定 Graph。
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
├── __init__.py                         # Python 应用包
└── main.py                             # FastAPI 统一入口

bak/mini_deep_research/
├── __init__.py                         # 公共模型、提示词和组件
├── config.py                           # 正式环境配置校验
├── mini_deep_research.py               # Pipeline 实现
├── mini_deep_research_by_langGraph.py  # LangGraph 实现
```

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
- `TAVILY_API_KEY`

本地开发可以使用 `.env`：

```bash
cp .env.example .env
# 编辑 .env，填入真实配置
```

系统环境变量的优先级高于 `.env`，真实密钥不要提交到 Git。

## 运行 LangGraph 版本

```bash
python -m bak.mini_deep_research.mini_deep_research_by_langGraph
```

## 运行 Pipeline 版本

```bash
python -m bak.mini_deep_research.mini_deep_research
```
