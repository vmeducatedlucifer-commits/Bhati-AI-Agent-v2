"""Task board - the separate panel where the user assigns work.

You drop tasks in; the swarm picks them up and MUST complete them. Each task
carries its own priority, assignee (role, team or a specific agent), and
acceptance criteria, and it tracks its own live progress log.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from app.core.events import EventType, event_bus
from app.core.logging import get_logger

log = get_logger("tasks.board")

Status = Literal["queued", "assigned", "running", "blocked", "review", "done", "failed", "cancelled"]


@dataclass
class BoardTask:
    session_id: str
    title: str
    description: str = ""
    acceptance: str = ""
    priority: int = 5                    # 1 = highest
    assignee: str = "auto"               # auto | role name | team:<name> | agent id
    mode: str = "swarm"                  # swarm | single
    size: int | None = None              # swarm size override for this task
    model: str | None = None             # per-task model override (incl. custom:<alias>)
    depends_on: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: Status = "queued"
    progress: int = 0
    agent_ids: list[str] = field(default_factory=list)
    run_id: str | None = None
    result: str = ""
    log: list[dict[str, Any]] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def note(self, message: str, author: str = "system") -> None:
        self.log.append({"at": time.time(), "author": author, "message": message[:2000]})
        self.log = self.log[-200:]
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "title": self.title,
            "description": self.description,
            "acceptance": self.acceptance,
            "priority": self.priority,
            "assignee": self.assignee,
            "mode": self.mode,
            "size": self.size,
            "model": self.model,
            "depends_on": self.depends_on,
            "tags": self.tags,
            "status": self.status,
            "progress": self.progress,
            "agent_ids": self.agent_ids,
            "run_id": self.run_id,
            "result": self.result,
            "log": self.log[-30:],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskBoard:
    def __init__(self) -> None:
        self._tasks: dict[str, BoardTask] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._auto_run: dict[str, bool] = defaultdict(lambda: True)

    # ------------------------------------------------------------------ crud
    def add(self, task: BoardTask) -> BoardTask:
        self._tasks[task.id] = task
        task.note(f"Task created and queued (priority {task.priority}).", author="user")
        return task

    def get(self, task_id: str) -> BoardTask | None:
        return self._tasks.get(task_id)

    def list(self, session_id: str | None = None, status: str | None = None) -> list[BoardTask]:
        tasks = list(self._tasks.values())
        if session_id:
            tasks = [task for task in tasks if task.session_id == session_id]
        if status:
            tasks = [task for task in tasks if task.status == status]
        return sorted(tasks, key=lambda task: (task.priority, task.created_at))

    def update(self, task_id: str, **changes: Any) -> BoardTask | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        for key, value in changes.items():
            if value is not None and hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = time.time()
        return task

    def delete(self, task_id: str) -> bool:
        worker = self._workers.pop(task_id, None)
        if worker:
            worker.cancel()
        return self._tasks.pop(task_id, None) is not None

    async def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        worker = self._workers.pop(task_id, None)
        if worker:
            worker.cancel()
        if task.run_id:
            from app.swarm.swarm import get_swarm

            await get_swarm().cancel(task.run_id)
        task.status = "cancelled"
        task.note("Cancelled by user.", author="user")
        return True

    # -------------------------------------------------------------- execution
    def ready(self, session_id: str) -> list[BoardTask]:
        done = {task.id for task in self.list(session_id) if task.status == "done"}
        return [
            task
            for task in self.list(session_id, status="queued")
            if all(dependency in done for dependency in task.depends_on)
        ]

    async def start(self, task_id: str) -> BoardTask | None:
        """Dispatch one board task to the swarm (or a single agent)."""
        task = self._tasks.get(task_id)
        if task is None or task.status in {"running", "done"}:
            return task
        task.status = "assigned"
        task.note("Dispatched to the swarm.")
        self._workers[task.id] = asyncio.create_task(self._execute(task))
        return task

    async def start_all(self, session_id: str) -> int:
        started = 0
        for task in self.ready(session_id):
            await self.start(task.id)
            started += 1
        return started

    async def _execute(self, task: BoardTask) -> None:
        from app.agents.loop import AgentLoop
        from app.agents.profiles import get_profile
        from app.swarm.swarm import get_swarm

        task.status = "running"
        task.progress = 5
        await event_bus.emit(EventType.TASK_UPDATED, task.session_id, {"board_task": task.to_dict()})
        instruction = (
            f"TASK: {task.title}\n\n{task.description}\n\n"
            f"ACCEPTANCE CRITERIA: {task.acceptance or 'Deliver the task fully and verify it.'}\n"
            "This task was assigned by the user and must be completed."
        )
        try:
            if task.mode == "single":
                role = task.assignee if task.assignee not in {"auto", ""} else "general"
                loop = AgentLoop(
                    session_id=task.session_id,
                    agent_id=f"task-{task.id}",
                    profile=get_profile(role.split(":")[-1]),
                    model=task.model,
                )
                task.agent_ids = [f"task-{task.id}"]
                result = await loop.run(instruction, stream_text=False)
                task.result = result.output
            else:
                swarm = get_swarm()
                run = await swarm.launch(
                    session_id=task.session_id,
                    goal=instruction,
                    size=task.size,
                    model=task.model,
                )
                task.run_id = run.id
                task.note(f"Swarm run {run.id} started with up to {run.size} agents.")
                while run.status == "running":
                    await asyncio.sleep(2)
                    if run.plan:
                        total = len(run.plan.tasks) or 1
                        done = sum(1 for item in run.plan.tasks if item.status == "done")
                        task.progress = min(95, int(done / total * 100))
                        task.agent_ids = [
                            record.id
                            for record in swarm.registry.list(task.session_id)
                            if record.status == "working"
                        ][:50]
                        await event_bus.emit(
                            EventType.TASK_UPDATED,
                            task.session_id,
                            {"board_task": task.to_dict()},
                        )
                task.result = run.output
                if run.status != "completed":
                    raise RuntimeError(f"Swarm run {run.status}")

            task.status = "review" if task.acceptance else "done"
            task.progress = 100
            task.note("Completed.", author="swarm")
        except asyncio.CancelledError:
            task.status = "cancelled"
            raise
        except Exception as exc:
            task.status = "failed"
            task.note(f"Failed: {exc}", author="swarm")
            log.warning("board_task_failed", task=task.id, error=str(exc))
        finally:
            self._workers.pop(task.id, None)
            await event_bus.emit(
                EventType.TASK_UPDATED, task.session_id, {"board_task": task.to_dict()}
            )

    # ------------------------------------------------------------- dashboard
    def stats(self, session_id: str) -> dict[str, Any]:
        tasks = self.list(session_id)
        counts: dict[str, int] = defaultdict(int)
        for task in tasks:
            counts[task.status] += 1
        return {
            "total": len(tasks),
            "by_status": dict(counts),
            "active_agents": sum(len(task.agent_ids) for task in tasks if task.status == "running"),
        }


@lru_cache
def get_task_board() -> TaskBoard:
    return TaskBoard()
