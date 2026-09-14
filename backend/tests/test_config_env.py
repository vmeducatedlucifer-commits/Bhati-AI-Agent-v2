"""Regression tests for environment parsing that broke production deploys."""

from __future__ import annotations

import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("*", ["*"]),
        ("https://a.com", ["https://a.com"]),
        ("https://a.com, https://b.com", ["https://a.com", "https://b.com"]),
        ('["https://a.com"]', ["https://a.com"]),
        ("", ["*"]),
    ],
)
def test_cors_origins_env_never_crashes(monkeypatch, value, expected):
    """CORS_ORIGINS=* used to raise SettingsError on boot (JSON decode)."""
    monkeypatch.setenv("CORS_ORIGINS", value)
    assert Settings(_env_file=None).cors_origins == expected


def test_cors_origins_defaults_to_wildcard(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert Settings(_env_file=None).cors_origins == ["*"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("postgresql://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("postgresql+psycopg2://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("postgresql://u:p@host/db?sslmode=require", "postgresql+asyncpg://u:p@host/db"),
        ("sqlite:///./data/bhati.db", "sqlite+aiosqlite:///./data/bhati.db"),
        ("postgresql+asyncpg://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
    ],
)
def test_database_url_is_normalized_for_async_driver(monkeypatch, raw, expected):
    monkeypatch.setenv("DATABASE_URL", raw)
    assert Settings(_env_file=None).database_url == expected


def test_swarm_agent_cap_is_enforced(monkeypatch):
    monkeypatch.setenv("SWARM_MAX_AGENTS", "99999")
    assert Settings(_env_file=None).swarm_max_agents == 1200
