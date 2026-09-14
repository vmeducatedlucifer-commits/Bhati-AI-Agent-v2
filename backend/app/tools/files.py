"""Workspace file tools: read, write, edit, list, search, delete."""

from __future__ import annotations

import re
from pathlib import Path

import aiofiles

from app.tools.base import Permission, Tool, ToolContext, ToolResult, tool_schema

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", ".next", "build"}


async def read_file(ctx: ToolContext, path: str, offset: int = 0, limit: int = 2000) -> ToolResult:
    target = ctx.resolve(path)
    if not target.exists():
        return ToolResult.failure(f"File not found: {path}")
    async with aiofiles.open(target, encoding="utf-8", errors="replace") as handle:
        lines = (await handle.read()).splitlines()
    window = lines[offset : offset + limit]
    numbered = "\n".join(f"{i + offset + 1:>5}│{line}" for i, line in enumerate(window))
    return ToolResult.success(numbered, total_lines=len(lines), returned=len(window))


async def write_file(ctx: ToolContext, path: str, content: str) -> ToolResult:
    target = ctx.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(target, "w", encoding="utf-8") as handle:
        await handle.write(content)
    return ToolResult.success(f"Wrote {len(content)} chars to {path}", path=str(target))


async def edit_file(
    ctx: ToolContext, path: str, old_string: str, new_string: str, replace_all: bool = False
) -> ToolResult:
    target = ctx.resolve(path)
    if not target.exists():
        return ToolResult.failure(f"File not found: {path}")
    async with aiofiles.open(target, encoding="utf-8") as handle:
        content = await handle.read()
    occurrences = content.count(old_string)
    if occurrences == 0:
        return ToolResult.failure("old_string not found; read the file again and copy it exactly")
    if occurrences > 1 and not replace_all:
        return ToolResult.failure(
            f"old_string appears {occurrences} times; add more context or set replace_all=true"
        )
    content = content.replace(old_string, new_string, -1 if replace_all else 1)
    async with aiofiles.open(target, "w", encoding="utf-8") as handle:
        await handle.write(content)
    return ToolResult.success(f"Applied {occurrences if replace_all else 1} edit(s) to {path}")


async def list_files(ctx: ToolContext, path: str = ".", depth: int = 2) -> ToolResult:
    root = ctx.resolve(path)
    if not root.exists():
        return ToolResult.failure(f"Path not found: {path}")
    entries: list[str] = []

    def walk(directory: Path, level: int, prefix: str) -> None:
        if level > depth:
            return
        for item in sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name)):
            if item.name in SKIP_DIRS or item.name.startswith(".") and item.is_dir():
                continue
            entries.append(f"{prefix}{item.name}{'/' if item.is_dir() else ''}")
            if item.is_dir():
                walk(item, level + 1, prefix + "  ")

    walk(root, 1, "")
    return ToolResult.success("\n".join(entries) or "(empty)", count=len(entries))


async def search_files(
    ctx: ToolContext, pattern: str, path: str = ".", glob: str = "*", max_results: int = 60
) -> ToolResult:
    root = ctx.resolve(path)
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return ToolResult.failure(f"Invalid regex: {exc}")
    hits: list[str] = []
    for file in root.rglob(glob):
        if not file.is_file() or any(part in SKIP_DIRS for part in file.parts):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                hits.append(f"{file.relative_to(root)}:{number}: {line.strip()[:200]}")
                if len(hits) >= max_results:
                    return ToolResult.success("\n".join(hits), truncated=True)
    return ToolResult.success("\n".join(hits) or "No matches", count=len(hits))


async def delete_path(ctx: ToolContext, path: str) -> ToolResult:
    import shutil

    target = ctx.resolve(path)
    if not target.exists():
        return ToolResult.failure(f"Path not found: {path}")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return ToolResult.success(f"Deleted {path}")


FILE_TOOLS = [
    Tool(
        name="read_file",
        description="Read a workspace file with line numbers. Use offset/limit for large files.",
        parameters=tool_schema(
            path={"type": "string", "required": True},
            offset={"type": "integer", "default": 0},
            limit={"type": "integer", "default": 2000},
        ),
        handler=read_file,
        permission=Permission.SAFE,
        tags=["files", "coding"],
    ),
    Tool(
        name="write_file",
        description="Create or overwrite a workspace file. Parent dirs are created automatically.",
        parameters=tool_schema(
            path={"type": "string", "required": True},
            content={"type": "string", "required": True},
        ),
        handler=write_file,
        permission=Permission.WRITE,
        tags=["files", "coding"],
    ),
    Tool(
        name="edit_file",
        description="Exact string replacement in a file. Prefer this over rewriting whole files.",
        parameters=tool_schema(
            path={"type": "string", "required": True},
            old_string={"type": "string", "required": True},
            new_string={"type": "string", "required": True},
            replace_all={"type": "boolean", "default": False},
        ),
        handler=edit_file,
        permission=Permission.WRITE,
        tags=["files", "coding"],
    ),
    Tool(
        name="list_files",
        description="List the workspace tree up to a given depth.",
        parameters=tool_schema(
            path={"type": "string", "default": "."}, depth={"type": "integer", "default": 2}
        ),
        handler=list_files,
        permission=Permission.SAFE,
        tags=["files", "coding"],
    ),
    Tool(
        name="search_files",
        description="Regex search across workspace files (ripgrep-like).",
        parameters=tool_schema(
            pattern={"type": "string", "required": True},
            path={"type": "string", "default": "."},
            glob={"type": "string", "default": "*"},
            max_results={"type": "integer", "default": 60},
        ),
        handler=search_files,
        permission=Permission.SAFE,
        tags=["files", "coding"],
    ),
    Tool(
        name="delete_path",
        description="Delete a file or directory inside the workspace.",
        parameters=tool_schema(path={"type": "string", "required": True}),
        handler=delete_path,
        permission=Permission.DANGEROUS,
        tags=["files"],
    ),
]
