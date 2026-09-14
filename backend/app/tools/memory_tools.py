"""Memory tools so the agent can persist and recall knowledge across sessions."""

from __future__ import annotations

from app.memory.store import get_memory_store
from app.tools.base import Permission, Tool, ToolContext, ToolResult, tool_schema


async def remember(ctx: ToolContext, content: str, kind: str = "semantic", scope: str = "session") -> ToolResult:
    session_id = ctx.session_id if scope == "session" else "global"
    record = await get_memory_store().remember(content, session_id=session_id, kind=kind)  # type: ignore[arg-type]
    return ToolResult.success(f"Stored memory {record.id}", id=record.id)


async def recall(ctx: ToolContext, query: str, limit: int = 5) -> ToolResult:
    records = await get_memory_store().recall(query, session_id=ctx.session_id, limit=limit)
    if not records:
        return ToolResult.success("No relevant memories found")
    lines = [f"- ({record.kind}, {record.score:.2f}) {record.content[:500]}" for record in records]
    return ToolResult.success("\n".join(lines), count=len(records))


async def index_repository(ctx: ToolContext, path: str = ".") -> ToolResult:
    from app.memory.rag import index_path

    count = await index_path(ctx.resolve(path), session_id=ctx.session_id)
    return ToolResult.success(f"Indexed {count} files from {path} into project memory")


MEMORY_TOOLS = [
    Tool(
        name="remember",
        description="Persist an important fact, decision or user preference for later sessions.",
        parameters=tool_schema(
            content={"type": "string", "required": True},
            kind={"type": "string", "enum": ["episodic", "semantic", "project", "preference"], "default": "semantic"},
            scope={"type": "string", "enum": ["session", "global"], "default": "session"},
        ),
        handler=remember,
        permission=Permission.WRITE,
        tags=["memory"],
    ),
    Tool(
        name="recall",
        description="Search long-term memory for relevant prior knowledge.",
        parameters=tool_schema(
            query={"type": "string", "required": True}, limit={"type": "integer", "default": 5}
        ),
        handler=recall,
        permission=Permission.SAFE,
        tags=["memory"],
    ),
    Tool(
        name="index_repository",
        description="Index a repo/folder into project memory for RAG retrieval.",
        parameters=tool_schema(path={"type": "string", "default": "."}),
        handler=index_repository,
        permission=Permission.WRITE,
        tags=["memory", "coding"],
    ),
]
