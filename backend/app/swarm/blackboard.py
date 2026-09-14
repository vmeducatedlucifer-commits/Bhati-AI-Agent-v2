"""Shared blackboard: the swarm's common working memory.

Agents post facts, artifacts, claims and open questions here instead of
re-deriving them. Entries are versioned and attributable, so the dashboard can
show who contributed what.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


@dataclass(slots=True)
class Entry:
    key: str
    value: Any
    author: str
    kind: str = "fact"  # fact | artifact | question | decision | risk | metric
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    version: int = 1
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "author": self.author,
            "kind": self.kind,
            "confidence": self.confidence,
            "tags": self.tags,
            "version": self.version,
            "updated_at": self.updated_at,
        }


class Blackboard:
    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Entry]] = defaultdict(dict)

    def post(
        self,
        session_id: str,
        key: str,
        value: Any,
        author: str,
        kind: str = "fact",
        confidence: float = 1.0,
        tags: list[str] | None = None,
    ) -> Entry:
        existing = self._entries[session_id].get(key)
        entry = Entry(
            key=key,
            value=value,
            author=author,
            kind=kind,
            confidence=confidence,
            tags=tags or [],
            version=(existing.version + 1) if existing else 1,
        )
        self._entries[session_id][key] = entry
        return entry

    def read(self, session_id: str, key: str) -> Entry | None:
        return self._entries.get(session_id, {}).get(key)

    def search(
        self, session_id: str, query: str = "", kind: str | None = None, limit: int = 50
    ) -> list[Entry]:
        entries = list(self._entries.get(session_id, {}).values())
        needle = query.lower()
        if needle:
            entries = [
                entry
                for entry in entries
                if needle in entry.key.lower() or needle in str(entry.value).lower()
            ]
        if kind:
            entries = [entry for entry in entries if entry.kind == kind]
        entries.sort(key=lambda entry: -entry.updated_at)
        return entries[:limit]

    def digest(self, session_id: str, limit: int = 25) -> str:
        """Compact text view injected into agent prompts."""
        entries = self.search(session_id, limit=limit)
        if not entries:
            return ""
        lines = [
            f"- ({entry.kind}, by {entry.author}) {entry.key}: {str(entry.value)[:300]}"
            for entry in entries
        ]
        return "SHARED BLACKBOARD:\n" + "\n".join(lines)

    def all(self, session_id: str) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.search(session_id, limit=1000)]

    def clear(self, session_id: str) -> None:
        self._entries.pop(session_id, None)


@lru_cache
def get_blackboard() -> Blackboard:
    return Blackboard()
