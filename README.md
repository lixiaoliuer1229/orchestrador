# Mini DeepResearch

基于 LangChain、LangGraph、Anthropic 和 Tavily 的轻量级研究工作流。

## 目录结构

```text
mini_deep_research/
├── __init__.py                         # 公共模型、提示词和组件
├── config.py                           # 正式环境配置校验
├── mini_deep_research.py               # Pipeline 实现
├── mini_deep_research_by_langGraph.py  # LangGraph 实现
└── __main__.py                         # 默认运行入口
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
python -m mini_deep_research
```

## 运行 Pipeline 版本

```bash
python -m mini_deep_research.mini_deep_research
```
