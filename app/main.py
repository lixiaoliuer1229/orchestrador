"""Unified FastAPI entry point for the Orchestrador service."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bak.langgraph_chatbot.graph import graph as chatbot_graph
from bak.langgraph_dataanalysis.graph import graph as data_agent_graph


logger = logging.getLogger(__name__)

GRAPHS = {
    "chatbot": chatbot_graph,
    "data_agent": data_agent_graph,
}


class GraphInvokeRequest(BaseModel):
    """Input accepted by the unified graph invocation endpoint."""

    input: dict[str, Any]
    config: dict[str, Any] = Field(default_factory=dict)


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

public_dir = Path(os.getenv("PUBLIC_DIR") or "public")
images_dir = public_dir / "images"
images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=images_dir), name="images")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, Any]:
    return {
        "service": "orchestrador",
        "status": "ok",
        "docs": "/docs",
        "graphs": sorted(GRAPHS),
    }


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


@app.post("/graphs/{graph_name}/invoke", tags=["graphs"])
async def invoke_graph(
    graph_name: str,
    request: GraphInvokeRequest,
) -> JSONResponse:
    graph = GRAPHS.get(graph_name)
    if graph is None:
        raise HTTPException(status_code=404, detail="Unknown graph")

    try:
        async with asyncio.timeout(_request_timeout_seconds()):
            result = await graph.ainvoke(request.input, config=request.config)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Graph invocation timed out") from exc
    except Exception as exc:
        logger.exception("Graph invocation failed", extra={"graph_name": graph_name})
        raise HTTPException(status_code=500, detail="Graph invocation failed") from exc

    return JSONResponse(content=jsonable_encoder(result))

