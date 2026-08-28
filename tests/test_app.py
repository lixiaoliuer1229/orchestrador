import os
from datetime import datetime, timezone

os.environ["AUTH_ENABLED"] = "false"

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app import main
from app.main import GRAPHS, app
from app.model_config import create_chat_model
from app.research.models import ResearchRun


client = TestClient(app)


def test_ok() -> None:
    response = client.get("/ok")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_frontend() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "量化研究控制台" in response.text
    assert "可追溯研究档案" in response.text
    assert "停止等待" in response.text


def test_runtime() -> None:
    response = client.get("/runtime")

    assert response.status_code == 200
    body = response.json()
    assert body["model"] in body["models"]
    assert body["models"] == [
        "coding-chat",
        "strong-chat",
        "cheap-chat",
        "minimax-latest",
    ]
    assert body["graphs"] == ["chatbot", "data_agent", "research_agent"]


def test_graph_list() -> None:
    response = client.get("/graphs")

    assert response.status_code == 200
    assert response.json() == {
        "graphs": ["chatbot", "data_agent", "research_agent"]
    }


def test_unknown_graph() -> None:
    response = client.post(
        "/graphs/missing/invoke",
        json={"input": {"messages": []}},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown graph"}


def test_graph_result_is_json_serializable() -> None:
    class FakeGraph:
        async def ainvoke(self, graph_input, config):
            return {
                "messages": [AIMessage(content="测试成功")],
                "received_config": config,
            }

    GRAPHS["fake"] = FakeGraph()
    try:
        response = client.post(
            "/graphs/fake/invoke",
            json={
                "input": {"messages": [{"role": "user", "content": "你好"}]},
                "config": {"configurable": {"thread_id": "test-thread"}},
            },
        )
    finally:
        GRAPHS.pop("fake", None)

    assert response.status_code == 200
    body = response.json()
    assert body["messages"][0]["content"] == "测试成功"
    assert body["received_config"]["configurable"]["thread_id"] == "test-thread"


def test_unknown_model_is_rejected() -> None:
    response = client.post(
        "/graphs/chatbot/invoke",
        json={"input": {"messages": []}, "model": "unknown-model"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Unsupported model"}


def test_model_factory_uses_requested_alias() -> None:
    assert create_chat_model("cheap-chat").model == "cheap-chat"
    assert create_chat_model("minimax-latest").model == "minimax-latest"


def test_research_run_history(monkeypatch) -> None:
    run = ResearchRun(
        run_id="11111111-1111-1111-1111-111111111111",
        query="test query",
        graph_version="research-v2",
        model="coding-chat",
        started_at=datetime.now(timezone.utc),
    )

    class FakeRepo:
        def list(self, limit, offset):
            assert (limit, offset) == (10, 0)
            return [run]

        def get(self, run_id):
            return None

    monkeypatch.setattr(main, "research_repo", FakeRepo())

    response = client.get("/research/runs?limit=10")

    assert response.status_code == 200
    assert response.json()[0]["run_id"] == run.run_id


def test_missing_research_run(monkeypatch) -> None:
    class FakeRepo:
        def get(self, run_id):
            return None

    monkeypatch.setattr(main, "research_repo", FakeRepo())

    response = client.get(
        "/research/runs/11111111-1111-1111-1111-111111111111"
    )

    assert response.status_code == 404
