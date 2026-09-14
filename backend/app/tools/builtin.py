"""Registers every builtin tool into the global registry (called at startup)."""

from __future__ import annotations

from app.core.logging import get_logger
from app.tools.browser import BROWSER_TOOLS
from app.tools.device import DEVICE_TOOLS
from app.tools.files import FILE_TOOLS
from app.tools.git_tools import GIT_TOOLS
from app.tools.memory_tools import MEMORY_TOOLS
from app.tools.python_exec import PYTHON_TOOLS
from app.tools.registry import get_registry
from app.tools.shell import SHELL_TOOLS
from app.tools.web import WEB_TOOLS

log = get_logger("tools.builtin")


def register_builtin_tools() -> None:
    registry = get_registry()
    registry.register_many(
        [
            *FILE_TOOLS,
            *SHELL_TOOLS,
            *PYTHON_TOOLS,
            *WEB_TOOLS,
            *GIT_TOOLS,
            *BROWSER_TOOLS,
            *DEVICE_TOOLS,
            *MEMORY_TOOLS,
        ]
    )
    log.info("builtin_tools_registered", count=len(registry.all()))


async def register_mcp_tools() -> int:
    from app.mcp.manager import get_mcp_manager

    tools = await get_mcp_manager().load_all()
    get_registry().register_many(tools)
    if tools:
        log.info("mcp_tools_registered", count=len(tools))
    return len(tools)
