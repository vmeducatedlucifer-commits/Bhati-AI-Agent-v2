"""Bhati AI Agent v2 - FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import (
    chat,
    events,
    files,
    health,
    mcp,
    models,
    runs,
    sessions,
    swarm,
    tasks,
    terminal,
    tools,
    voice,
    workspace,
)
from app.core.config import settings
from app.core.errors import BhatiError
from app.core.logging import get_logger, setup_logging
from app.db.session import init_db
from app.sandbox.terminal import terminal_manager
from app.tools.builtin import register_builtin_tools, register_mcp_tools

setup_logging()
log = get_logger("main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info(
        "startup",
        env=settings.app_env,
        providers=settings.configured_providers(),
        swarm_max_agents=settings.swarm_max_agents,
    )
    settings.workspace_path.mkdir(parents=True, exist_ok=True)
    await init_db()
    register_builtin_tools()
    try:
        await register_mcp_tools()
    except Exception as exc:  # MCP is optional
        log.warning("mcp_bootstrap_failed", error=str(exc))
    yield
    await terminal_manager.shutdown()
    log.info("shutdown")


app = FastAPI(
    title="Bhati AI Agent v2",
    version="2.2.0",
    description=(
        "Autonomous multi-agent platform: swarm coordination (up to 1200 agents), "
        "per-agent workspaces, coding, computer use, research and device control."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (
    health,
    chat,
    runs,
    sessions,
    tools,
    files,
    workspace,
    terminal,
    events,
    voice,
    mcp,
    swarm,
    tasks,
    models,
):
    app.include_router(module.router, prefix="/api")


@app.exception_handler(BhatiError)
async def bhati_error_handler(_request: Request, exc: BhatiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.__class__.__name__, "detail": str(exc)})


@app.get("/")
async def root() -> dict:
    return {
        "name": "Bhati AI Agent v2",
        "docs": "/docs",
        "health": "/api/health",
        "swarm": "/api/swarm/config",
        "workspace": "/api/workspace",
        "tasks": "/api/tasks",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=not settings.is_production)
