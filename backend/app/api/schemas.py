"""Request/response models for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    profile: str = "general"
    model: str | None = None
    mode: Literal["chat", "autonomous"] = "chat"


class RunRequest(BaseModel):
    goal: str
    session_id: str | None = None
    model: str | None = None
    autonomous: bool = True


class SessionCreate(BaseModel):
    title: str = "New session"
    model: str | None = None
    mode: Literal["chat", "autonomous"] = "chat"


class SessionOut(BaseModel):
    id: str
    title: str
    model: str | None = None
    mode: str = "chat"
    created_at: str | None = None


class ToolInvokeRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str = "scratch"


class TerminalCreate(BaseModel):
    session_id: str
    agent_id: str = "main"
    cwd: str | None = None


class MCPServerIn(BaseModel):
    name: str
    transport: Literal["stdio", "http"] = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class VoiceCommand(BaseModel):
    text: str
    session_id: str | None = None
    speak: bool = True
