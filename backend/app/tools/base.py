"""Typed tool framework with permissions, schemas and audit-friendly results."""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.events import EventType, event_bus


class Permission(StrEnum):
    SAFE = "safe"            # read-only, no side effects
    WRITE = "write"          # writes inside the workspace
    DANGEROUS = "dangerous"  # shell, network mutations, git push
    SYSTEM = "system"        # device / OS level control


@dataclass(slots=True)
class ToolResult:
    ok: bool
    output: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    @classmethod
    def success(cls, output: str = "", **data: Any) -> ToolResult:
        return cls(ok=True, output=output, data=data)

    @classmethod
    def failure(cls, error: str, **data: Any) -> ToolResult:
        return cls(ok=False, error=error, output=error, data=data)

    def to_model_text(self, limit: int = 20000) -> str:
        text = self.output if self.ok else f"ERROR: {self.error}"
        if len(text) > limit:
            head, tail = text[: limit // 2], text[-limit // 2 :]
            text = f"{head}\n\n...[truncated {len(text) - limit} chars]...\n\n{tail}"
        return text


@dataclass(slots=True)
class ToolContext:
    """Everything a tool is allowed to touch."""

    session_id: str
    agent_id: str = "main"
    workspace: Path = field(default_factory=lambda: settings.workspace_path)
    approvals: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolve(self, relative: str) -> Path:
        """Resolve a path, refusing to escape the workspace."""
        target = (self.workspace / relative).resolve() if not Path(relative).is_absolute() else Path(relative).resolve()
        if not str(target).startswith(str(self.workspace.resolve())):
            raise PermissionError(f"Path escapes workspace: {relative}")
        return target

    async def emit(self, type_: EventType, data: dict[str, Any]) -> None:
        await event_bus.emit(type_, self.session_id, data, agent_id=self.agent_id)


Handler = Callable[..., Awaitable[ToolResult]]


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler
    permission: Permission = Permission.SAFE
    tags: list[str] = field(default_factory=list)
    source: str = "builtin"

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    async def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()
        try:
            signature = inspect.signature(self.handler)
            kwargs = dict(arguments)
            if "ctx" in signature.parameters:
                kwargs["ctx"] = ctx
            accepted = {
                key: value
                for key, value in kwargs.items()
                if key in signature.parameters
                or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values())
            }
            result = await self.handler(**accepted)
        except Exception as exc:  # tools must never crash the loop
            result = ToolResult.failure(f"{type(exc).__name__}: {exc}")
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        return result


def tool_schema(**properties: dict[str, Any]) -> dict[str, Any]:
    """Helper to build a JSON schema object from property definitions."""
    required = [name for name, spec in properties.items() if spec.pop("required", False)]
    return {"type": "object", "properties": properties, "required": required}
