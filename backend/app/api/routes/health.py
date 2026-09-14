from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.tools.registry import get_registry

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


@router.get("/info")
async def info() -> dict:
    registry = get_registry()
    return {
        "name": "Bhati AI Agent v2",
        "env": settings.app_env,
        "providers": settings.configured_providers(),
        "models": {
            "default": settings.default_model,
            "fast": settings.fast_model,
            "reasoning": settings.reasoning_model,
        },
        "sandbox": settings.sandbox_mode,
        "tools": len(registry.all()),
        "max_parallel_agents": settings.max_parallel_agents,
    }
