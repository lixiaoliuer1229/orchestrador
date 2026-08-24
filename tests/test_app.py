from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.main import GRAPHS, app


client = TestClient(app)


def test_ok() -> None:
    response = client.get("/ok")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_graph_list() -> None:
    response = client.get("/graphs")

    assert response.status_code == 200
    assert response.json() == {"graphs": ["chatbot", "data_agent"]}


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
