"""Custom model registry.

Lets the user plug in ANY endpoint at runtime - self-hosted vLLM, LM Studio,
Together, Fireworks, Azure OpenAI, a proxy, or a custom Anthropic-compatible
gateway - without touching code.

Two wire formats are supported:
- `openai`    : /chat/completions (works for vLLM, LM Studio, Together, Groq-like, Azure)
- `anthropic` : /v1/messages (works for Anthropic itself and compatible gateways)

Models are addressed as `custom:<alias>` e.g. `custom:my-vllm-qwen`.
Definitions persist to `CUSTOM_MODELS_FILE` (default: data/custom_models.json).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from app.core.config import settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger

log = get_logger("llm.custom")

WireFormat = Literal["openai", "anthropic"]


@dataclass
class CustomModel:
    alias: str                      # short name used as custom:<alias>
    base_url: str                   # e.g. http://localhost:8001/v1
    model: str                      # provider-side model id
    format: WireFormat = "openai"
    api_key: str = ""
    label: str = ""
    context_window: int = 128_000
    max_output_tokens: int = 8192
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    temperature: float | None = None
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    notes: str = ""

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data["api_key"] = "***" if self.api_key else ""
        data["id"] = f"custom:{self.alias}"
        return data


class CustomModelRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(settings.custom_models_file)
        self._models: dict[str, CustomModel] = {}
        self.load()

    # ------------------------------------------------------------ persistence
    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._models = {
                item["alias"]: CustomModel(**item) for item in raw.get("models", [])
            }
            log.info("custom_models_loaded", count=len(self._models))
        except Exception as exc:
            log.warning("custom_models_load_failed", error=str(exc))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"models": [asdict(model) for model in self._models.values()]}, indent=2),
            encoding="utf-8",
        )

    # ----------------------------------------------------------------- crud
    def add(self, model: CustomModel) -> CustomModel:
        if not model.base_url.startswith(("http://", "https://")):
            raise ConfigurationError("base_url must start with http:// or https://")
        self._models[model.alias] = model
        self.save()
        log.info("custom_model_added", alias=model.alias, format=model.format)
        return model

    def remove(self, alias: str) -> bool:
        existed = self._models.pop(alias, None) is not None
        if existed:
            self.save()
        return existed

    def get(self, alias: str) -> CustomModel | None:
        return self._models.get(alias)

    def resolve(self, model_id: str) -> CustomModel | None:
        """Accepts 'custom:alias' or a bare alias."""
        alias = model_id.split(":", 1)[1] if model_id.startswith("custom:") else model_id
        model = self._models.get(alias)
        return model if (model and model.enabled) else None

    def list(self) -> list[CustomModel]:
        return list(self._models.values())


@lru_cache
def get_custom_models() -> CustomModelRegistry:
    return CustomModelRegistry()
