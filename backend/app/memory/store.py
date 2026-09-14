"""Long-term memory: episodic + semantic records with embedding search.

Uses SQLite/Postgres for durability and an in-process numpy index for similarity.
Swap `_similarity` for pgvector in production without touching callers.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.router import get_router

log = get_logger("memory")

MemoryKind = Literal["episodic", "semantic", "project", "preference"]


@dataclass(slots=True)
class MemoryRecord:
    id: str
    session_id: str
    kind: MemoryKind
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: float = field(default_factory=time.time)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "kind": self.kind,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "score": self.score,
        }


class MemoryStore:
    """JSONL-backed store with lazy embeddings — zero infra to run locally."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.workspace_path / ".bhati" / "memory.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[MemoryRecord] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._records.append(
                MemoryRecord(
                    id=raw["id"],
                    session_id=raw.get("session_id", ""),
                    kind=raw.get("kind", "episodic"),
                    content=raw.get("content", ""),
                    metadata=raw.get("metadata", {}),
                    embedding=raw.get("embedding"),
                    created_at=raw.get("created_at", time.time()),
                )
            )
        log.info("memory_loaded", records=len(self._records))

    def _append(self, record: MemoryRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "id": record.id,
                        "session_id": record.session_id,
                        "kind": record.kind,
                        "content": record.content,
                        "metadata": record.metadata,
                        "embedding": record.embedding,
                        "created_at": record.created_at,
                    }
                )
                + "\n"
            )

    async def remember(
        self,
        content: str,
        session_id: str = "global",
        kind: MemoryKind = "semantic",
        metadata: dict[str, Any] | None = None,
        embed: bool = True,
    ) -> MemoryRecord:
        embedding: list[float] | None = None
        if embed:
            try:
                vectors = await get_router().embed([content])
                embedding = vectors[0] if vectors else None
            except Exception as exc:  # embeddings are best-effort
                log.warning("embedding_failed", error=str(exc))
        record = MemoryRecord(
            id=uuid.uuid4().hex,
            session_id=session_id,
            kind=kind,
            content=content,
            metadata=metadata or {},
            embedding=embedding,
        )
        self._records.append(record)
        self._append(record)
        return record

    @staticmethod
    def _similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        denominator = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query) + 1e-9
        return (matrix @ query) / denominator

    async def recall(
        self,
        query: str,
        session_id: str | None = None,
        kind: MemoryKind | None = None,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        candidates = [
            record
            for record in self._records
            if (session_id is None or record.session_id in {session_id, "global"})
            and (kind is None or record.kind == kind)
        ]
        if not candidates:
            return []
        embedded = [record for record in candidates if record.embedding]
        if embedded:
            try:
                vectors = await get_router().embed([query])
                query_vector = np.array(vectors[0], dtype=np.float32)
                matrix = np.array([record.embedding for record in embedded], dtype=np.float32)
                scores = self._similarity(query_vector, matrix)
                for record, score in zip(embedded, scores, strict=False):
                    record.score = float(score)
                return sorted(embedded, key=lambda record: record.score, reverse=True)[:limit]
            except Exception as exc:
                log.warning("recall_embedding_failed", error=str(exc))
        terms = {term for term in query.lower().split() if len(term) > 2}
        for record in candidates:
            lowered = record.content.lower()
            record.score = sum(1 for term in terms if term in lowered) / (len(terms) or 1)
        return sorted(candidates, key=lambda record: (record.score, record.created_at), reverse=True)[:limit]

    def forget(self, record_id: str) -> bool:
        before = len(self._records)
        self._records = [record for record in self._records if record.id != record_id]
        if len(self._records) == before:
            return False
        self.path.write_text("", encoding="utf-8")
        for record in self._records:
            self._append(record)
        return True

    def all(self, session_id: str | None = None) -> list[MemoryRecord]:
        return [
            record
            for record in self._records
            if session_id is None or record.session_id == session_id
        ]


@lru_cache
def get_memory_store() -> MemoryStore:
    return MemoryStore()
