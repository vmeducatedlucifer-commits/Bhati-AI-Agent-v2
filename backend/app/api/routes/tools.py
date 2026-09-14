"""Tool catalogue and direct invocation (useful for the dashboard and CLI)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user
from app.api.schemas import ToolInvokeRequest
from app.core.config import settings
from app.tools.base import ToolContext
from app.tools.registry import get_registry

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
async def list_tools(tag: str | None = None, _user: dict = Depends(current_user)) -> list[dict]:
    tools = get_registry().select(tags=[tag] if tag else None)
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "permission": tool.permission.value,
            "tags": tool.tags,
            "source": tool.source,
            "parameters": tool.parameters,
        }
        for tool in tools
    ]


@router.post("/invoke")
async def invoke(request: ToolInvokeRequest, _user: dict = Depends(current_user)) -> dict:
    tool = get_registry().get(request.name)
    if not tool:
        raise HTTPException(404, f"Unknown tool '{request.name}'")
    ctx = ToolContext(
        session_id=request.session_id,
        agent_id="manual",
        workspace=settings.workspace_path / request.session_id,
    )
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    result = await tool.run(ctx, request.arguments)
    return {"ok": result.ok, "output": result.output, "error": result.error, "data": result.data}
