"""In-process async event bus used to stream agent activity to every surface."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    SESSION_START = "session.start"
    SESSION_END = "session.end"
    PLAN_CREATED = "plan.created"
    TASK_UPDATED = "task.updated"
    AGENT_START = "agent.start"
    AGENT_END = "agent.end"
    MESSAGE_DELTA = "message.delta"
    MESSAGE_COMPLETE = "message.complete"
    THINKING = "agent.thinking"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    APPROVAL_REQUIRED = "approval.required"
    TERMINAL_OUTPUT = "terminal.output"
    USAGE = "usage"
    ERROR = "error"


@dataclass(slots=True)
class Event:
    type: EventType
    session_id: str
    data: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": str(self.type),
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "ts": self.ts,
            "data": self.data,
        }


class EventBus:
    """Fan-out pub/sub keyed by session id. Replaces polling everywhere."""

    def __init__(self, history_limit: int = 500) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[Event]]] = defaultdict(list)
        self._history: dict[str, list[Event]] = defaultdict(list)
        self._history_limit = history_limit
        self._lock = asyncio.Lock()

    async def publish(self, event: Event) -> None:
        async with self._lock:
            history = self._history[event.session_id]
            history.append(event)
            if len(history) > self._history_limit:
                del history[: len(history) - self._history_limit]
            queues = list(self._subscribers[event.session_id])
        for queue in queues:
            queue.put_nowait(event)

    async def emit(
        self,
        type_: EventType,
        session_id: str,
        data: dict[str, Any] | None = None,
        agent_id: str | None = None,
    ) -> None:
        await self.publish(Event(type=type_, session_id=session_id, data=data or {}, agent_id=agent_id))

    async def subscribe(self, session_id: str, replay: bool = False) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        async with self._lock:
            self._subscribers[session_id].append(queue)
            if replay:
                for event in self._history[session_id]:
                    queue.put_nowait(event)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue[Event]) -> None:
        async with self._lock:
            if queue in self._subscribers[session_id]:
                self._subscribers[session_id].remove(queue)

    def history(self, session_id: str) -> list[Event]:
        return list(self._history.get(session_id, []))


event_bus = EventBus()
