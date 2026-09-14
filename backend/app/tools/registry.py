"""Tool registry: registration, per-agent filtering, MCP injection."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from app.core.logging import get_logger
from app.tools.base import Permission, Tool

log = get_logger("tools.registry")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool, override: bool = False) -> None:
        if tool.name in self._tools and not override:
            log.warning("tool_already_registered", tool=tool.name)
            return
        self._tools[tool.name] = tool

    def register_many(self, tools: Iterable[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return sorted(self._tools)

    def select(
        self,
        include: Iterable[str] | None = None,
        exclude: Iterable[str] | None = None,
        tags: Iterable[str] | None = None,
        max_permission: Permission = Permission.SYSTEM,
    ) -> list[Tool]:
        order = {
            Permission.SAFE: 0,
            Permission.WRITE: 1,
            Permission.DANGEROUS: 2,
            Permission.SYSTEM: 3,
        }
        include_set = set(include) if include else None
        exclude_set = set(exclude or ())
        tag_set = set(tags) if tags else None
        selected: list[Tool] = []
        for tool in self._tools.values():
            if include_set is not None and tool.name not in include_set:
                continue
            if tool.name in exclude_set:
                continue
            if tag_set and not tag_set.intersection(tool.tags):
                continue
            if order[tool.permission] > order[max_permission]:
                continue
            selected.append(tool)
        return selected

    def schemas(self, tools: Iterable[Tool] | None = None) -> list[dict[str, Any]]:
        return [tool.schema() for tool in (tools if tools is not None else self._tools.values())]


@lru_cache
def get_registry() -> ToolRegistry:
    """Global registry, populated by `app.tools.builtin.register_builtin_tools`."""
    return ToolRegistry()
