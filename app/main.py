"""Unified FastAPI entry point for the Orchestrador service."""

from __future__ import annotations

import asyncio
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.model_config import SUPPORTED_MODELS, configured_model
from bak.langgraph_chatbot.graph import create_graph as create_chatbot_graph
from bak.langgraph_chatbot.graph import graph as chatbot_graph
from bak.langgraph_dataanalysis.graph import create_graph as create_data_agent_graph
from bak.langgraph_dataanalysis.graph import graph as data_agent_graph


logger = logging.getLogger(__name__)

GRAPHS = {
    "chatbot": chatbot_graph,
    "data_agent": data_agent_graph,
}
GRAPH_FACTORIES = {
    "chatbot": create_chatbot_graph,
    "data_agent": create_data_agent_graph,
}


@lru_cache(maxsize=len(SUPPORTED_MODELS) * len(GRAPH_FACTORIES))
def _configured_graph(graph_name: str, model: str):
    return GRAPH_FACTORIES[graph_name](model)


class GraphInvokeRequest(BaseModel):
    """Input accepted by the unified graph invocation endpoint."""

    input: dict[str, Any]
    config: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None


def _request_timeout_seconds() -> float:
    raw_value = os.getenv("APP_REQUEST_TIMEOUT_SECONDS", "300")
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            "APP_REQUEST_TIMEOUT_SECONDS must be a number"
        ) from exc
    if timeout <= 0:
        raise RuntimeError("APP_REQUEST_TIMEOUT_SECONDS must be greater than zero")
    return timeout


app = FastAPI(
    title="Orchestrador API",
    version="1.0.0",
    description="Unified API for the configured LangGraph agents.",
)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

public_dir = Path(os.getenv("PUBLIC_DIR") or "public")
images_dir = public_dir / "images"
images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=images_dir), name="images")


@app.get("/", include_in_schema=False, response_class=FileResponse)
async def root() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/ok", tags=["health"])
async def ok() -> dict[str, bool]:
    return {"ok": True}


@app.get("/health", tags=["health"])
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "graphs": sorted(GRAPHS),
    }


@app.get("/graphs", tags=["graphs"])
async def list_graphs() -> dict[str, list[str]]:
    return {"graphs": sorted(GRAPHS)}


@app.get("/runtime", tags=["runtime"])
async def runtime() -> dict[str, Any]:
    return {
        "service": "orchestrador",
        "model": configured_model(),
        "models": list(SUPPORTED_MODELS),
        "model_endpoint": (
            "custom" if os.getenv("ANTHROPIC_BASE_URL") else "anthropic-official"
        ),
        "graphs": sorted(GRAPHS),
        "request_timeout_seconds": _request_timeout_seconds(),
    }


@app.post("/graphs/{graph_name}/invoke", tags=["graphs"])
async def invoke_graph(
    graph_name: str,
    request: GraphInvokeRequest,
) -> JSONResponse:
    if graph_name not in GRAPHS:
        raise HTTPException(status_code=404, detail="Unknown graph")

    model = request.model or configured_model()
    if model not in SUPPORTED_MODELS:
        raise HTTPException(status_code=422, detail="Unsupported model")

    graph = (
        _configured_graph(graph_name, model)
        if graph_name in GRAPH_FACTORIES
        else GRAPHS[graph_name]
    )

    try:
        async with asyncio.timeout(_request_timeout_seconds()):
            result = await graph.ainvoke(request.input, config=request.config)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Graph invocation timed out") from exc
    except Exception as exc:
        logger.exception("Graph invocation failed", extra={"graph_name": graph_name})
        raise HTTPException(status_code=500, detail="Graph invocation failed") from exc

    return JSONResponse(content=jsonable_encoder(result))
