from __future__ import annotations

import pytest

from app.tools.base import Permission, ToolContext
from app.tools.builtin import register_builtin_tools
from app.tools.registry import get_registry


def test_registry_registers_builtins() -> None:
    register_builtin_tools()
    registry = get_registry()
    names = {tool.name for tool in registry.all()}
    assert {"read_file", "write_file", "run_command", "web_search", "remember"} <= names


def test_permission_filtering() -> None:
    register_builtin_tools()
    safe = get_registry().select(max_permission=Permission.SAFE)
    assert all(tool.permission is Permission.SAFE for tool in safe)


@pytest.mark.asyncio
async def test_write_then_read(ctx: ToolContext) -> None:
    register_builtin_tools()
    registry = get_registry()
    write = registry.get("write_file")
    read = registry.get("read_file")
    assert write and read
    written = await write.run(ctx, {"path": "hello.txt", "content": "namaste"})
    assert written.ok
    result = await read.run(ctx, {"path": "hello.txt"})
    assert result.ok and "namaste" in result.output
