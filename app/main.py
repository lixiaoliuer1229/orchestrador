"""Unified FastAPI entry point for the Orchestrador service."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import (
    SESSION_COOKIE,
    auth_enabled,
    authenticate,
    cookie_secure,
    create_session,
    create_user,
    delete_session,
    init_auth_database,
    list_users,
    session_user,
    set_user_active,
)
from app.model_config import SUPPORTED_MODELS, configured_model
from bak.langgraph_chatbot.graph import create_graph as create_chatbot_graph
from bak.langgraph_chatbot.graph import graph as chatbot_graph
from bak.langgraph_dataanalysis.graph import create_graph as create_data_agent_graph
from bak.langgraph_dataanalysis.graph import graph as data_agent_graph


logger = logging.getLogger(__name__)
login_attempts: dict[str, deque[float]] = defaultdict(deque)

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


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserCreateRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,64}$")
    password: str = Field(min_length=12, max_length=256)
    role: str = Field(default="user", pattern=r"^(admin|user)$")


class UserStatusRequest(BaseModel):
    active: bool


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    if auth_enabled():
        await asyncio.to_thread(init_auth_database)
    yield


app = FastAPI(
    title="Orchestrador API",
    version="1.0.0",
    description="Unified API for the configured LangGraph agents.",
    lifespan=lifespan,
)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

public_dir = Path(os.getenv("PUBLIC_DIR") or "public")
images_dir = public_dir / "images"
images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=images_dir), name="images")


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not auth_enabled() or request.url.path in {"/ok", "/login", "/auth/login"} or request.url.path.startswith("/static/"):
            return await call_next(request)
        user = await asyncio.to_thread(session_user, request.cookies.get(SESSION_COOKIE))
        if user:
            request.state.user = user
            return await call_next(request)
        if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": "Authentication required"}, status_code=401)


app.add_middleware(AuthenticationMiddleware)


def _require_admin(request: Request) -> None:
    if getattr(request.state, "user", {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator required")


@app.get("/", include_in_schema=False, response_class=FileResponse)
async def root() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/login", include_in_schema=False, response_class=FileResponse)
async def login_page() -> FileResponse:
    return FileResponse(static_dir / "login.html")


@app.post("/auth/login", tags=["auth"])
async def login(request: Request, credentials: LoginRequest) -> JSONResponse:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = login_attempts[client_ip]
    while attempts and now - attempts[0] > 900:
        attempts.popleft()
    if len(attempts) >= 10:
        return JSONResponse(
            {"detail": "登录尝试过多，请稍后再试"},
            status_code=429,
            headers={"Retry-After": "900"},
        )
    user = await asyncio.to_thread(authenticate, credentials.username, credentials.password)
    if not user:
        attempts.append(now)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    attempts.clear()
    token = await asyncio.to_thread(create_session, user["id"])
    response = JSONResponse({"username": user["username"], "role": user["role"]})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=cookie_secure(),
        samesite="strict",
        max_age=int(os.getenv("AUTH_SESSION_HOURS", "12")) * 3600,
        path="/",
    )
    return response


@app.post("/auth/logout", tags=["auth"])
async def logout(request: Request) -> JSONResponse:
    await asyncio.to_thread(delete_session, request.cookies.get(SESSION_COOKIE))
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/auth/me", tags=["auth"])
async def me(request: Request) -> dict[str, Any]:
    return request.state.user


@app.get("/admin", include_in_schema=False, response_class=FileResponse)
async def admin_page(request: Request) -> FileResponse:
    _require_admin(request)
    return FileResponse(static_dir / "admin.html")


@app.get("/admin/users", tags=["admin"])
async def admin_users(request: Request) -> list[dict[str, Any]]:
    _require_admin(request)
    return await asyncio.to_thread(list_users)


@app.post("/admin/users", tags=["admin"])
async def admin_create_user(request: Request, user: UserCreateRequest) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await asyncio.to_thread(create_user, user.username, user.password, user.role)
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail="用户名已存在") from exc
        raise


@app.patch("/admin/users/{user_id}", tags=["admin"])
async def admin_set_user_status(
    request: Request, user_id: int, status: UserStatusRequest
) -> dict[str, bool]:
    _require_admin(request)
    if request.state.user["id"] == user_id and not status.active:
        raise HTTPException(status_code=422, detail="不能停用当前管理员账号")
    await asyncio.to_thread(set_user_active, user_id, status.active)
    return {"ok": True}


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
