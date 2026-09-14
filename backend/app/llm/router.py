"""Model router: `provider/model` resolution, capability presets, fallbacks."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from functools import lru_cache
from typing import Any, Literal

from app.core.config import settings
from app.core.errors import ConfigurationError, ProviderError
from app.core.logging import get_logger
from app.llm.anthropic import AnthropicProvider
from app.llm.base import LLMProvider, LLMResponse, Message, StreamChunk
from app.llm.google import GoogleProvider
from app.llm.openai_compatible import OpenAICompatibleProvider

log = get_logger("llm.router")

TaskClass = Literal["default", "fast", "reasoning", "embedding"]

OPENAI_COMPATIBLE: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


class ModelRouter:
    """Resolves `provider/model` strings to a live provider, with fallbacks."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._build()

    def _build(self) -> None:
        keys = {
            "openai": settings.openai_api_key,
            "groq": settings.groq_api_key,
            "deepseek": settings.deepseek_api_key,
            "mistral": settings.mistral_api_key,
            "openrouter": settings.openrouter_api_key,
        }
        for name, base_url in OPENAI_COMPATIBLE.items():
            if keys.get(name):
                self._providers[name] = OpenAICompatibleProvider(name, keys[name], base_url)
        if settings.anthropic_api_key:
            self._providers["anthropic"] = AnthropicProvider(settings.anthropic_api_key)
        if settings.google_api_key:
            self._providers["google"] = GoogleProvider(settings.google_api_key)
        if settings.ollama_base_url:
            self._providers["ollama"] = OpenAICompatibleProvider(
                "ollama", api_key=None, base_url=settings.ollama_base_url
            )
        log.info("llm_providers_ready", providers=sorted(self._providers))

    # ------------------------------------------------------------------ utils
    @property
    def providers(self) -> list[str]:
        return sorted(self._providers)

    def model_for(self, task: TaskClass = "default") -> str:
        return {
            "default": settings.default_model,
            "fast": settings.fast_model,
            "reasoning": settings.reasoning_model,
            "embedding": settings.embedding_model,
        }[task]

    def resolve(self, model: str | None = None, task: TaskClass = "default") -> tuple[LLMProvider, str]:
        spec = model or self.model_for(task)
        provider_name, _, model_name = spec.partition("/")
        if not model_name:  # bare model id -> guess by prefix
            provider_name, model_name = self._guess_provider(spec), spec
        provider = self._providers.get(provider_name)
        if provider is None:
            fallback = self._first_available()
            if fallback is None:
                raise ConfigurationError(
                    "No LLM provider configured. Set at least one API key in .env"
                )
            log.warning("provider_fallback", requested=provider_name, used=fallback[0])
            return fallback[1], model_name
        return provider, model_name

    def _guess_provider(self, model: str) -> str:
        lowered = model.lower()
        if lowered.startswith("claude"):
            return "anthropic"
        if lowered.startswith("gemini"):
            return "google"
        if lowered.startswith(("gpt", "o1", "o3", "o4", "text-embedding")):
            return "openai"
        if lowered.startswith("deepseek"):
            return "deepseek"
        if lowered.startswith(("llama", "mixtral", "qwen")):
            return "groq"
        return "openrouter"

    def _first_available(self) -> tuple[str, LLMProvider] | None:
        for name in ("anthropic", "openai", "google", "deepseek", "groq", "mistral", "openrouter", "ollama"):
            if name in self._providers:
                return name, self._providers[name]
        return None

    # ----------------------------------------------------------------- calls
    async def stream(
        self,
        messages: Sequence[Message],
        model: str | None = None,
        task: TaskClass = "default",
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        provider, model_name = self.resolve(model, task)
        async for chunk in provider.stream(
            messages,
            model_name,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            system=system,
        ):
            yield chunk

    async def complete(
        self,
        messages: Sequence[Message],
        model: str | None = None,
        task: TaskClass = "default",
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
        retries: int = 1,
    ) -> LLMResponse:
        provider, model_name = self.resolve(model, task)
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return await provider.complete(
                    messages,
                    model_name,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system=system,
                )
            except ProviderError as exc:
                last_error = exc
                log.warning("provider_call_failed", provider=provider.name, attempt=attempt, error=str(exc))
        raise last_error or ProviderError("LLM call failed")

    async def embed(self, texts: Sequence[str], model: str | None = None) -> list[list[float]]:
        provider, model_name = self.resolve(model, "embedding")
        return await provider.embed(texts, model_name)


@lru_cache
def get_router() -> ModelRouter:
    return ModelRouter()
