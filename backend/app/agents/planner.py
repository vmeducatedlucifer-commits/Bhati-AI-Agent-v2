"""Planner: turns a goal into a dependency-ordered task graph."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agents.prompts import PLANNER_PROMPT
from app.core.logging import get_logger
from app.llm.base import Message
from app.llm.router import get_router

log = get_logger("agent.planner")

TaskStatus = Literal["pending", "running", "done", "failed", "skipped"]


@dataclass
class Task:
    id: str
    title: str
    description: str = ""
    agent: str = "general"
    depends_on: list[str] = field(default_factory=list)
    acceptance: str = ""
    status: TaskStatus = "pending"
    result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "agent": self.agent,
            "depends_on": self.depends_on,
            "acceptance": self.acceptance,
            "status": self.status,
            "result": self.result[:2000],
        }


@dataclass
class Plan:
    summary: str
    tasks: list[Task] = field(default_factory=list)

    def ready(self) -> list[Task]:
        done = {task.id for task in self.tasks if task.status == "done"}
        return [
            task
            for task in self.tasks
            if task.status == "pending" and all(dep in done for dep in task.depends_on)
        ]

    def unfinished(self) -> bool:
        return any(task.status in {"pending", "running"} for task in self.tasks)

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "tasks": [task.to_dict() for task in self.tasks]}


def _extract_json(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def create_plan(goal: str, context: str = "") -> Plan:
    prompt = f"GOAL:\n{goal}"
    if context:
        prompt += f"\n\nCONTEXT:\n{context[:4000]}"
    response = await get_router().complete(
        [Message(role="user", content=prompt)],
        task="reasoning",
        system=PLANNER_PROMPT,
        temperature=0.2,
        max_tokens=2000,
    )
    payload = _extract_json(response.content)
    if not payload or not payload.get("tasks"):
        log.warning("planner_fallback", goal=goal[:120])
        return Plan(
            summary=goal[:200],
            tasks=[Task(id="t1", title="Complete the goal", description=goal, agent="general")],
        )
    tasks = [
        Task(
            id=str(raw.get("id") or f"t{index + 1}"),
            title=raw.get("title", "Task"),
            description=raw.get("description", ""),
            agent=raw.get("agent", "general"),
            depends_on=[str(dep) for dep in raw.get("depends_on", [])],
            acceptance=raw.get("acceptance", ""),
        )
        for index, raw in enumerate(payload["tasks"])
    ]
    return Plan(summary=payload.get("summary", goal[:200]), tasks=tasks)
