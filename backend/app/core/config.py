"""Application settings loaded from environment / .env."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # App
    app_name: str = "Bhati AI Agent"
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # NOTE: kept as a plain string on purpose.
    # pydantic-settings JSON-decodes any list[...] field coming from the
    # environment *before* validators run, so CORS_ORIGINS=* crashed startup
    # with: error parsing value for field "cors_origins".
    # Read the parsed list through the `cors_origins` property below.
    cors_origins_raw: str = Field(
        default="*",
        validation_alias=AliasChoices("CORS_ORIGINS", "CORS_ORIGINS_RAW", "cors_origins"),
    )

    # Security
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    auth_enabled: bool = False

    # Storage
    database_url: str = "sqlite+aiosqlite:///./data/bhati.db"
    redis_url: str | None = None
    workspace_dir: str = "./workspaces"
    ephemeral_workspace: bool = False

    # Providers
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    groq_api_key: str | None = None
    deepseek_api_key: str | None = None
    mistral_api_key: str | None = None
    openrouter_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"

    # Custom / self-hosted models (added at runtime via /api/models/custom)
    custom_models_file: str = "./data/custom_models.json"
    # Optional single custom endpoint straight from env (OpenAI-compatible)
    custom_openai_base_url: str | None = None
    custom_openai_api_key: str | None = None
    custom_openai_model: str | None = None
    # Optional single custom Anthropic-compatible gateway from env
    custom_anthropic_base_url: str | None = None
    custom_anthropic_api_key: str | None = None
    custom_anthropic_model: str | None = None

    # Models
    default_model: str = "anthropic/claude-sonnet-4"
    fast_model: str = "openai/gpt-4o-mini"
    reasoning_model: str = "openai/o3-mini"
    embedding_model: str = "openai/text-embedding-3-small"

    # Agent limits
    max_steps: int = 40
    max_parallel_agents: int = 4
    step_timeout_seconds: int = 180

    # Swarm
    swarm_enabled: bool = True
    swarm_max_agents: int = 1200          # hard ceiling for one swarm run
    swarm_default_agents: int = 12        # used when the caller does not pass a size
    swarm_llm_concurrency: int = 24       # in-flight model calls (the real bottleneck)
    swarm_message_history: int = 20_000   # A2A messages kept per session for the dashboard
    swarm_agent_max_steps: int = 15       # per-worker step cap inside a swarm
    swarm_debate_rounds: int = 1

    # Sandbox
    sandbox_mode: str = "local"
    sandbox_image: str = "bhati/sandbox:latest"
    sandbox_timeout: int = 120

    # Integrations
    github_token: str | None = None
    telegram_bot_token: str | None = None
    tavily_api_key: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        """Make managed Postgres URLs usable by SQLAlchemy's async engine.

        Render/Heroku/Railway hand out `postgres://` or `postgresql://` URLs that
        point at the *sync* psycopg driver. Booting an async engine with those
        crashes at startup. Normalise them to asyncpg and drop libpq-only query
        args (e.g. `sslmode`) that asyncpg rejects.
        """
        if not isinstance(value, str) or not value.strip():
            return value
        url = value.strip()

        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]
        elif url.startswith("postgresql+psycopg2://"):
            url = "postgresql+asyncpg://" + url[len("postgresql+psycopg2://") :]
        elif url.startswith("sqlite://") and "+aiosqlite" not in url:
            url = "sqlite+aiosqlite://" + url[len("sqlite://") :]

        if url.startswith("postgresql+asyncpg://") and "?" in url:
            base, _, query = url.partition("?")
            kept = [
                part
                for part in query.split("&")
                if part and not part.startswith(("sslmode=", "channel_binding=", "gssencmode="))
            ]
            url = base + ("?" + "&".join(kept) if kept else "")

        return url

    @field_validator("swarm_max_agents")
    @classmethod
    def _cap_agents(cls, value: int) -> int:
        return max(1, min(value, 1200))

    @property
    def cors_origins(self) -> list[str]:
        """Accepts `*`, a comma-separated list, or a JSON array."""
        raw = (self.cors_origins_raw or "*").strip()
        if not raw:
            return ["*"]
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except ValueError:
                pass
        return [item.strip() for item in raw.split(",") if item.strip()] or ["*"]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def workspace_path(self) -> Path:
        """Workspace root, falling back to /tmp when the disk is read-only.

        Render free instances have no persistent disk, so a relative path like
        `./workspaces` can fail on a read-only filesystem. Never crash on boot
        because of it.
        """
        try:
            path = Path(self.workspace_dir).resolve()
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            fallback = Path("/tmp/workspaces")
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def configured_providers(self) -> list[str]:
        mapping = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
            "groq": self.groq_api_key,
            "deepseek": self.deepseek_api_key,
            "mistral": self.mistral_api_key,
            "openrouter": self.openrouter_api_key,
        }
        providers = [name for name, key in mapping.items() if key]
        providers.append("ollama")
        if self.custom_openai_base_url:
            providers.append("custom-openai")
        if self.custom_anthropic_base_url:
            providers.append("custom-anthropic")
        return providers


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
