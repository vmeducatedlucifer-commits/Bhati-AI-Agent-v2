"""Model management: list providers and register custom OpenAI/Anthropic-compatible models."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.llm.base import Message
from app.llm.custom import CustomModel, get_custom_models
from app.llm.router import get_router

router = APIRouter(prefix="/models", tags=["models"])


class CustomModelRequest(BaseModel):
    alias: str = Field(description="Short name; the model is addressed as custom:<alias>")
    base_url: str
    model: str
    format: str = Field(default="openai", description="openai | anthropic")
    api_key: str = ""
    label: str = ""
    context_window: int = 128_000
    max_output_tokens: int = 8192
    supports_tools: bool = True
    supports_vision: bool = False
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    notes: str = ""


class TestRequest(BaseModel):
    model: str
    prompt: str = "Reply with the single word: ok"


@router.get("")
async def list_models() -> dict:
    return {
        "providers": get_router().providers,
        "models": get_router().available_models(),
        "defaults": {
            "default": settings.default_model,
            "fast": settings.fast_model,
            "reasoning": settings.reasoning_model,
            "embedding": settings.embedding_model,
        },
    }


@router.get("/custom")
async def list_custom() -> dict:
    return {"models": [model.public() for model in get_custom_models().list()]}


@router.post("/custom")
async def add_custom(request: CustomModelRequest) -> dict:
    if request.format not in {"openai", "anthropic"}:
        raise HTTPException(status_code=400, detail="format must be 'openai' or 'anthropic'")
    model = get_custom_models().add(CustomModel(**request.model_dump()))
    get_router().reload()
    return model.public()


@router.delete("/custom/{alias}")
async def delete_custom(alias: str) -> dict:
    removed = get_custom_models().remove(alias)
    get_router().reload()
    return {"deleted": removed}


@router.post("/test")
async def test_model(request: TestRequest) -> dict:
    """Send a one-shot prompt to verify a (custom) model actually works."""
    try:
        response = await get_router().complete(
            [Message(role="user", content=request.prompt)],
            model=request.model,
            max_tokens=64,
            temperature=0,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "model": request.model,
        "ok": True,
        "output": response.content,
        "tokens": response.usage.total_tokens if response.usage else 0,
    }


@router.post("/reload")
async def reload_models() -> dict:
    get_router().reload()
    return {"providers": get_router().providers}
