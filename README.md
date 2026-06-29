# orchestrador 🚀

> 多智能体编排 / 工作流项目集合

本仓库是多个 AI/LangGraph 项目的合集,每个子目录都是一个独立的工程。

## 📦 子项目

| 子项目 | 说明 |
| ------ | ---- |
| [`langgraph-backend-studio/`](./langgraph-backend-studio/) | 后端工程师的 LangGraph 实战项目 — 状态机、工具调用、人机协作、多智能体、可观测性、生产部署。 |

## 🛠️ 仓库约定

- **代码组织**:每个子项目是独立的 Python 包,有自己的 `requirements.txt` / `Makefile` / 测试
- **依赖管理**:子项目内各自的 `venv`
- **提交规范**:见各子项目内的 `README.md`
- **Git**:根目录 `.gitignore` 已覆盖通用 Python/虚拟环境/数据文件

## 📝 License

MIT