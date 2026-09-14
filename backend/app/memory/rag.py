"""RAG over local documents and code: chunk → embed → store → retrieve."""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.memory.store import MemoryRecord, get_memory_store

log = get_logger("rag")

TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".rs", ".go", ".java", ".kt", ".sql", ".sh", ".html", ".css",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", ".next", "build"}


def chunk_text(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


async def index_path(root: Path, session_id: str = "global", max_files: int = 400) -> int:
    """Index a directory (repo, docs folder) into semantic memory."""
    store = get_memory_store()
    indexed = 0
    for file in root.rglob("*"):
        if indexed >= max_files:
            break
        if not file.is_file() or file.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in file.parts):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for position, chunk in enumerate(chunk_text(text)):
            await store.remember(
                content=chunk,
                session_id=session_id,
                kind="project",
                metadata={"path": str(file), "chunk": position},
            )
        indexed += 1
    log.info("rag_indexed", root=str(root), files=indexed)
    return indexed


async def retrieve(query: str, session_id: str = "global", limit: int = 6) -> list[MemoryRecord]:
    return await get_memory_store().recall(query, session_id=session_id, limit=limit)


def format_context(records: list[MemoryRecord]) -> str:
    if not records:
        return ""
    lines = ["<retrieved_context>"]
    for record in records:
        source = record.metadata.get("path", record.kind)
        lines.append(f"[{source}] {record.content[:1200]}")
    lines.append("</retrieved_context>")
    return "\n".join(lines)
