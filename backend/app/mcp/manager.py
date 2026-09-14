"""MCP hub: connect Model Context Protocol servers and expose them as tools.

Supports stdio and streamable HTTP servers defined in `mcp.config.json`:

```json
{
  "servers": {
    "github":   {"transport": "http", "url": "https://api.githubcopilot.com/mcp/", "headers": {"Authorization": "Bearer ..."}},
    "filesystem": {"transport": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "./workspaces"]}
  }
}
```
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.tools.base import Permission, Tool, ToolResult

log = get_logger("mcp")


@dataclass
class MCPServerConfig:
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


class MCPManager:
    """Lazily connects to MCP servers and converts their tools into Bhati tools."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or Path("mcp.config.json")
        self.servers: dict[str, MCPServerConfig] = {}
        self._sessions: dict[str, Any] = {}
        self._exit_stacks: dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> None:
        if not self.config_path.exists():
            return
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            log.warning("mcp_config_invalid", error=str(exc))
            return
        for name, spec in (raw.get("servers") or {}).items():
            self.servers[name] = MCPServerConfig(name=name, **spec)
        log.info("mcp_config_loaded", servers=list(self.servers))

    def add_server(self, config: MCPServerConfig) -> None:
        self.servers[config.name] = config

    async def connect(self, name: str) -> bool:
        config = self.servers.get(name)
        if not config or not config.enabled:
            return False
        if name in self._sessions:
            return True
        from contextlib import AsyncExitStack

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        stack = AsyncExitStack()
        try:
            if config.transport == "stdio":
                params = StdioServerParameters(
                    command=config.command or "", args=config.args, env=config.env or None
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            else:
                from mcp.client.streamable_http import streamablehttp_client

                read, write, _ = await stack.enter_async_context(
                    streamablehttp_client(config.url or "", headers=config.headers)
                )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except Exception as exc:
            await stack.aclose()
            log.warning("mcp_connect_failed", server=name, error=str(exc))
            return False
        self._sessions[name] = session
        self._exit_stacks[name] = stack
        log.info("mcp_connected", server=name)
        return True

    async def list_tools(self, name: str) -> list[Tool]:
        if not await self.connect(name):
            return []
        session = self._sessions[name]
        listing = await session.list_tools()
        tools: list[Tool] = []
        for mcp_tool in listing.tools:
            tools.append(self._wrap(name, mcp_tool))
        return tools

    def _wrap(self, server: str, mcp_tool: Any) -> Tool:
        tool_name = f"{server}__{mcp_tool.name}"

        async def handler(**kwargs: Any) -> ToolResult:
            session = self._sessions.get(server)
            if session is None:
                return ToolResult.failure(f"MCP server '{server}' not connected")
            try:
                response = await session.call_tool(mcp_tool.name, kwargs)
            except Exception as exc:
                return ToolResult.failure(f"MCP call failed: {exc}")
            parts: list[str] = []
            for item in getattr(response, "content", []) or []:
                text = getattr(item, "text", None)
                parts.append(text if text else str(item))
            return ToolResult.success("\n".join(parts) or "(no content)")

        return Tool(
            name=tool_name,
            description=f"[MCP:{server}] {mcp_tool.description or mcp_tool.name}",
            parameters=getattr(mcp_tool, "inputSchema", None) or {"type": "object", "properties": {}},
            handler=handler,
            permission=Permission.DANGEROUS,
            tags=["mcp", server],
            source=f"mcp:{server}",
        )

    async def load_all(self) -> list[Tool]:
        tools: list[Tool] = []
        for name in self.servers:
            tools.extend(await self.list_tools(name))
        return tools

    async def shutdown(self) -> None:
        for name, stack in list(self._exit_stacks.items()):
            try:
                await stack.aclose()
            except Exception:  # pragma: no cover
                pass
            self._exit_stacks.pop(name, None)
            self._sessions.pop(name, None)


@lru_cache
def get_mcp_manager() -> MCPManager:
    return MCPManager()
