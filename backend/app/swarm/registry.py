"""Live roster of every agent in the swarm (for the dashboard and scheduler)."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


@dataclass(slots=True)
class AgentRecord:
    id: str
    session_id: str
    role: str = "general"
    team: str = "core"
    status: str = "idle"  # idle | working | waiting | blocked | done | failed
    task_id: str | None = None
    current_action: str = ""
    model: str | None = None
    steps: int = 0
    tokens: int = 0
    messages_sent: int = 0
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "team": self.team,
            "status": self.status,
            "task_id": self.task_id,
            "current_action": self.current_action[:200],
            "model": self.model,
            "steps": self.steps,
            "tokens": self.tokens,
            "messages_sent": self.messages_sent,
            "uptime": round(time.time() - self.started_at, 1),
            "updated_at": self.updated_at,
        }


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentRecord] = {}

    def register(self, record: AgentRecord) -> AgentRecord:
        self._agents[record.id] = record
        return record

    def update(self, agent_id: str, **changes: Any) -> AgentRecord | None:
        record = self._agents.get(agent_id)
        if record is None:
            return None
        for key, value in changes.items():
            if hasattr(record, key):
                setattr(record, key, value)
        record.updated_at = time.time()
        return record

    def get(self, agent_id: str) -> AgentRecord | None:
        return self._agents.get(agent_id)

    def remove(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)

    def list(self, session_id: str | None = None, team: str | None = None) -> list[AgentRecord]:
        records = list(self._agents.values())
        if session_id:
            records = [record for record in records if record.session_id == session_id]
        if team:
            records = [record for record in records if record.team == team]
        return records

    def summary(self, session_id: str | None = None) -> dict[str, Any]:
        records = self.list(session_id)
        by_status: dict[str, int] = defaultdict(int)
        by_role: dict[str, int] = defaultdict(int)
        by_team: dict[str, int] = defaultdict(int)
        for record in records:
            by_status[record.status] += 1
            by_role[record.role] += 1
            by_team[record.team] += 1
        return {
            "total": len(records),
            "active": by_status.get("working", 0),
            "by_status": dict(by_status),
            "by_role": dict(by_role),
            "by_team": dict(by_team),
            "tokens": sum(record.tokens for record in records),
            "steps": sum(record.steps for record in records),
        }


@lru_cache
def get_agent_registry() -> AgentRegistry:
    return AgentRegistry()
