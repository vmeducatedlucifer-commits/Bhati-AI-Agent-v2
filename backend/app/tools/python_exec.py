"""Python code execution inside the sandbox (data analysis, scripting)."""

from __future__ import annotations

import uuid

from app.sandbox.runner import get_sandbox
from app.tools.base import Permission, Tool, ToolContext, ToolResult, tool_schema


async def run_python(ctx: ToolContext, code: str, timeout: int = 120) -> ToolResult:
    script = ctx.resolve(f".bhati/scripts/{uuid.uuid4().hex}.py")
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(code, encoding="utf-8")
    sandbox = get_sandbox()
    result = await sandbox.exec(f"python3 {script}", workdir=ctx.workspace, timeout=timeout)
    output = result.stdout + (f"\n[stderr]\n{result.stderr}" if result.stderr else "")
    if result.exit_code != 0:
        return ToolResult.failure(output or "python execution failed", exit_code=result.exit_code)
    return ToolResult.success(output or "(no output)")


PYTHON_TOOLS = [
    Tool(
        name="run_python",
        description="Execute Python code in the sandbox. Use for computation, data work and scripting.",
        parameters=tool_schema(
            code={"type": "string", "required": True},
            timeout={"type": "integer", "default": 120},
        ),
        handler=run_python,
        permission=Permission.DANGEROUS,
        tags=["code", "data"],
    )
]
