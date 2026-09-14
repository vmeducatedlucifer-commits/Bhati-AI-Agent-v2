"""Manage MCP servers at runtime — connect, list tools, hot-register."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user
from app.api.schemas import MCPServerIn
from app.mcp.manager import MCPServerConfig, get_mcp_manager
from app.tools.registry import get_registry

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/servers")
async def list_servers(_user: dict = Depends(current_user)) -> list[dict]:
    manager = get_mcp_manager()
    return [
        {"name": config.name, "transport": config.transport, "enabled": config.enabled, "url": config.url}
        for config in manager.servers.values()
    ]


@router.post("/servers")
async def add_server(payload: MCPServerIn, _user: dict = Depends(current_user)) -> dict:
    manager = get_mcp_manager()
    manager.add_server(MCPServerConfig(**payload.model_dump()))
    tools = await manager.list_tools(payload.name)
    get_registry().register_many(tools)
    return {"server": payload.name, "tools": [tool.name for tool in tools]}


@router.post("/servers/{name}/reload")
async def reload_server(name: str, _user: dict = Depends(current_user)) -> dict:
    manager = get_mcp_manager()
    if name not in manager.servers:
        raise HTTPException(404, "Server not configured")
    tools = await manager.list_tools(name)
    get_registry().register_many(tools)
    return {"server": name, "tools": [tool.name for tool in tools]}
