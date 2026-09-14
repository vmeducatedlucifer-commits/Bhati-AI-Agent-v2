"""Agent-to-agent (A2A) message mesh.

Every message is persisted in a ring buffer so the dashboard can replay the
conversation between agents, and simultaneously routed to the recipients'
inboxes so agents can actually talk to each other.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any

from app.core.events import EventType, event_bus
from app.core.logging import get_logger

log = get_logger("swarm.bus")

BROADCAST = "*"


class MessageKind(str, Enum):
    CHAT = "chat"                 # free-form discussion between agents
    REQUEST = "request"           # asking another agent to do something
    RESPONSE = "response"         # reply to a request
    PROPOSAL = "proposal"         # a suggested plan/answer in a debate
    CRITIQUE = "critique"         # objection or review of a proposal
    VOTE = "vote"                 # consensus vote
    HANDOFF = "handoff"           # transferring a task to another agent
    STATUS = "status"             # progress heartbeat
    HELP = "help"                 # asking the swarm for assistance
    ANNOUNCE = "announce"         # broadcast to everyone
    RESULT = "result"             # final artifact/answer


@dataclass(slots=True)
class AgentMessage:
    session_id: str
    sender: str
    recipient: str = BROADCAST
    kind: MessageKind = MessageKind.CHAT
    content: str = ""
    topic: str = "general"
    task_id: str | None = None
    thread_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "kind": self.kind.value,
            "content": self.content,
            "topic": self.topic,
            "task_id": self.task_id,
            "thread_id": self.thread_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    def render(self) -> str:
        target = "everyone" if self.recipient == BROADCAST else self.recipient
        return f"[{self.kind.value}] {self.sender} -> {target}: {self.content}"


class SwarmBus:
    """Routes messages between agents and mirrors them to the live dashboard."""

    def __init__(self, history_size: int = 20_000, inbox_size: int = 200) -> None:
        self._history: dict[str, deque[AgentMessage]] = defaultdict(
            lambda: deque(maxlen=history_size)
        )
        self._inboxes: dict[str, asyncio.Queue[AgentMessage]] = {}
        self._subscribers: dict[str, set[str]] = defaultdict(set)  # topic -> agent ids
        self._watchers: dict[str, set[asyncio.Queue[AgentMessage]]] = defaultdict(set)
        self._inbox_size = inbox_size
        self._counts: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------- membership
    def join(self, agent_id: str, topics: list[str] | None = None) -> asyncio.Queue[AgentMessage]:
        inbox: asyncio.Queue[AgentMessage] = asyncio.Queue(maxsize=self._inbox_size)
        self._inboxes[agent_id] = inbox
        for topic in topics or ["general"]:
            self._subscribers[topic].add(agent_id)
        return inbox

    def leave(self, agent_id: str) -> None:
        self._inboxes.pop(agent_id, None)
        for members in self._subscribers.values():
            members.discard(agent_id)

    def subscribe_topic(self, agent_id: str, topic: str) -> None:
        self._subscribers[topic].add(agent_id)

    def watch(self, session_id: str) -> asyncio.Queue[AgentMessage]:
        """Dashboard stream of everything agents say to each other."""
        queue: asyncio.Queue[AgentMessage] = asyncio.Queue(maxsize=2000)
        self._watchers[session_id].add(queue)
        return queue

    def unwatch(self, session_id: str, queue: asyncio.Queue[AgentMessage]) -> None:
        self._watchers[session_id].discard(queue)

    # --------------------------------------------------------------- sending
    async def send(self, message: AgentMessage) -> None:
        self._history[message.session_id].append(message)
        self._counts[message.sender] += 1

        targets: list[str]
        if message.recipient == BROADCAST:
            targets = [
                agent_id
                for agent_id in self._subscribers.get(message.topic, set())
                if agent_id != message.sender
            ]
        else:
            targets = [message.recipient]

        for agent_id in targets:
            inbox = self._inboxes.get(agent_id)
            if inbox is None:
                continue
            try:
                inbox.put_nowait(message)
            except asyncio.QueueFull:
                # Drop the oldest message rather than blocking the sender.
                try:
                    inbox.get_nowait()
                    inbox.put_nowait(message)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    log.warning("inbox_overflow", agent=agent_id)

        for queue in list(self._watchers.get(message.session_id, set())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass

        await event_bus.emit(
            EventType.MESSAGE_COMPLETE,
            message.session_id,
            {"a2a": message.to_dict()},
            agent_id=message.sender,
        )

    async def say(
        self,
        session_id: str,
        sender: str,
        content: str,
        recipient: str = BROADCAST,
        kind: MessageKind = MessageKind.CHAT,
        topic: str = "general",
        **metadata: Any,
    ) -> AgentMessage:
        message = AgentMessage(
            session_id=session_id,
            sender=sender,
            recipient=recipient,
            kind=kind,
            content=content,
            topic=topic,
            metadata=metadata,
        )
        await self.send(message)
        return message

    # -------------------------------------------------------------- receiving
    async def receive(self, agent_id: str, timeout: float = 0.0) -> list[AgentMessage]:
        """Drain an agent's inbox (optionally waiting `timeout` seconds for the first item)."""
        inbox = self._inboxes.get(agent_id)
        if inbox is None:
            return []
        messages: list[AgentMessage] = []
        if timeout > 0:
            try:
                messages.append(await asyncio.wait_for(inbox.get(), timeout=timeout))
            except TimeoutError:
                return []
        while not inbox.empty():
            messages.append(inbox.get_nowait())
        return messages

    # ---------------------------------------------------------------- queries
    def history(
        self, session_id: str, limit: int = 200, topic: str | None = None, agent_id: str | None = None
    ) -> list[AgentMessage]:
        messages = list(self._history.get(session_id, []))
        if topic:
            messages = [message for message in messages if message.topic == topic]
        if agent_id:
            messages = [
                message
                for message in messages
                if agent_id in (message.sender, message.recipient)
            ]
        return messages[-limit:]

    def stats(self, session_id: str) -> dict[str, Any]:
        messages = self._history.get(session_id, deque())
        by_kind: dict[str, int] = defaultdict(int)
        for message in messages:
            by_kind[message.kind.value] += 1
        return {
            "total_messages": len(messages),
            "by_kind": dict(by_kind),
            "talkers": sorted(self._counts.items(), key=lambda item: -item[1])[:20],
            "topics": {topic: len(members) for topic, members in self._subscribers.items()},
        }

    def clear(self, session_id: str) -> None:
        self._history.pop(session_id, None)


@lru_cache
def get_swarm_bus() -> SwarmBus:
    return SwarmBus()
