"""Persistence models (SQLModel) — works on SQLite locally and Postgres in prod."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


def _uid() -> str:
    return uuid.uuid4().hex[:16]


def _now() -> datetime:
    return datetime.now(UTC)


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(default_factory=_uid, primary_key=True)
    title: str = "New session"
    user_id: str = "local"
    model: str | None = None
    mode: str = "chat"  # chat | autonomous
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    archived: bool = False


class ChatMessage(SQLModel, table=True):
    __tablename__ = "messages"

    id: str = Field(default_factory=_uid, primary_key=True)
    session_id: str = Field(index=True, foreign_key="sessions.id")
    role: str = "user"
    content: str = Field(default="", sa_column=Column(Text))
    agent_id: str | None = None
    tool_calls: list = Field(default_factory=list, sa_column=Column(JSON))
    tokens: int = 0
    created_at: datetime = Field(default_factory=_now)


class RunRecord(SQLModel, table=True):
    __tablename__ = "runs"

    id: str = Field(default_factory=_uid, primary_key=True)
    session_id: str = Field(index=True)
    goal: str = Field(default="", sa_column=Column(Text))
    status: str = "running"
    plan: dict = Field(default_factory=dict, sa_column=Column(JSON))
    output: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_now)


class ToolAudit(SQLModel, table=True):
    __tablename__ = "tool_audit"

    id: str = Field(default_factory=_uid, primary_key=True)
    session_id: str = Field(index=True)
    agent_id: str = "main"
    tool: str = ""
    arguments: dict = Field(default_factory=dict, sa_column=Column(JSON))
    ok: bool = True
    duration_ms: int = 0
    created_at: datetime = Field(default_factory=_now)
