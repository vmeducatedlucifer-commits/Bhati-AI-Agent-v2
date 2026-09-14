"""Shell execution tools (routed through the sandbox)."""

from __future__ import annotations

from app.core.events import EventType
from app.sandbox.runner import get_sandbox
from app.tools.base import Permission, Tool, ToolContext, ToolResult, tool_schema


async def run_command(ctx: ToolContext, command: str, timeout: int = 120, cwd: str = ".") -> ToolResult:
    sandbox = get_sandbox()
    await ctx.emit(EventType.TERMINAL_OUTPUT, {"command": command, "cwd": cwd})
    result = await sandbox.exec(command, workdir=ctx.resolve(cwd), timeout=timeout)
    output = result.stdout + (f"\n[stderr]\n{result.stderr}" if result.stderr else "")
    await ctx.emit(
        EventType.TERMINAL_OUTPUT, {"command": command, "output": output[-4000:], "exit_code": result.exit_code}
    )
    if result.exit_code != 0:
        return ToolResult.failure(
            f"exit code {result.exit_code}\n{output}", exit_code=result.exit_code
        )
    return ToolResult.success(output or "(no output)", exit_code=0)


SHELL_TOOLS = [
    Tool(
        name="run_command",
        description=(
            "Run a shell command inside the sandboxed workspace. Use for builds, tests, "
            "package installs, git operations and any CLI work. Long output is truncated."
        ),
        parameters=tool_schema(
            command={"type": "string", "description": "Shell command to execute", "required": True},
            cwd={"type": "string", "description": "Working directory relative to workspace", "default": "."},
            timeout={"type": "integer", "description": "Timeout in seconds", "default": 120},
        ),
        handler=run_command,
        permission=Permission.DANGEROUS,
        tags=["shell", "coding", "ops"],
    )
]
