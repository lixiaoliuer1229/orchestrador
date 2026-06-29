"""FastAPI server exposing the hello_graph over HTTP + SSE streaming."""
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from src.graphs.hello_graph import hello_graph
from src.utils.config import settings
from src.utils.logger import setup_logging

setup_logging()

app = FastAPI(title="LangGraph Backend Studio", version="0.1.0")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    state = {"messages": [HumanMessage(content=req.message)], "turn_count": 0}
    result = hello_graph.invoke(state)
    return ChatResponse(reply=result["messages"][-1].content)


@app.post("/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Stream tokens from the LLM via LangGraph streaming."""
    state = {"messages": [HumanMessage(content=req.message)], "turn_count": 0}

    def event_source():
        for chunk in hello_graph.stream(state, stream_mode="messages"):
            token, _meta = chunk
            yield token.content or ""

    return StreamingResponse(event_source(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "examples.api_server:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
    )