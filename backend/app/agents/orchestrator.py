"""Multi-agent orchestrator: schedules the task graph across parallel workers."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.agents.loop import AgentLoop
from app.agents.planner import Plan, Task, create_plan
from app.agents.profiles import get_profile
from app.agents.prompts import SYNTHESIS_PROMPT
from app.core.config import settings
from app.core.events import EventType, event_bus
from app.core.logging import get_logger
from app.llm.base import Message
from app.llm.router import get_router
from app.memory.rag import format_context, retrieve

log = get_logger("agent.orchestrator")


@dataclass
class Run:
    id: str
    session_id: str
    goal: str
    plan: Plan | None = None
    status: str = "running"
    output: str = ""
    workers: dict[str, AgentLoop] = field(default_factory=dict)
    task: asyncio.Task | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "goal": self.goal,
            "status": self.status,
            "plan": self.plan.to_dict() if self.plan else None,
            "output": self.output,
        }


class Orchestrator:
    """Supervisor that plans, spawns specialists, reviews and synthesises."""

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list(self, session_id: str | None = None) -> list[Run]:
        return [run for run in self._runs.values() if session_id is None or run.session_id == session_id]

    async def cancel(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if not run:
            return False
        for worker in run.workers.values():
            worker.cancel()
        if run.task:
            run.task.cancel()
        run.status = "cancelled"
        return True

    # -------------------------------------------------------------- simple
    async def run_single(
        self, session_id: str, goal: str, profile: str = "general", model: str | None = None
    ) -> str:
        memories = await retrieve(goal, session_id=session_id, limit=5)
        loop = AgentLoop(
            session_id=session_id,
            agent_id=f"{profile}-{uuid.uuid4().hex[:6]}",
            profile=profile,
            model=model,
            extra_context=format_context(memories),
        )
        result = await loop.run(goal)
        return result.output

    # ------------------------------------------------------------ autonomous
    async def start(
        self, session_id: str, goal: str, model: str | None = None, autonomous: bool = True
    ) -> Run:
        run = Run(id=uuid.uuid4().hex[:12], session_id=session_id, goal=goal)
        self._runs[run.id] = run
        run.task = asyncio.create_task(self._execute(run, model=model, autonomous=autonomous))
        return run

    async def _execute(self, run: Run, model: str | None, autonomous: bool) -> None:
        try:
            if not autonomous:
                run.output = await self.run_single(run.session_id, run.goal, model=model)
                run.status = "completed"
                return

            memories = await retrieve(run.goal, session_id=run.session_id, limit=6)
            context = format_context(memories)
            run.plan = await create_plan(run.goal, context=context)
            await event_bus.emit(
                EventType.PLAN_CREATED, run.session_id, {"run_id": run.id, "plan": run.plan.to_dict()}
            )

            semaphore = asyncio.Semaphore(settings.max_parallel_agents)
            results: dict[str, str] = {}

            while run.plan.unfinished() and run.status == "running":
                ready = run.plan.ready()
                if not ready:
                    break
                await asyncio.gather(
                    *(self._run_task(run, task, results, context, model, semaphore) for task in ready)
                )

            run.output = await self._synthesise(run, results)
            run.status = "completed"
        except asyncio.CancelledError:
            run.status = "cancelled"
            raise
        except Exception as exc:
            log.error("run_failed", run=run.id, error=str(exc))
            run.status = "failed"
            run.output = f"Run failed: {exc}"
            await event_bus.emit(EventType.ERROR, run.session_id, {"run_id": run.id, "error": str(exc)})
        finally:
            await event_bus.emit(
                EventType.SESSION_END, run.session_id, {"run_id": run.id, "status": run.status}
            )

    async def _run_task(
        self,
        run: Run,
        task: Task,
        results: dict[str, str],
        context: str,
        model: str | None,
        semaphore: asyncio.Semaphore,
    ) -> None:
        async with semaphore:
            task.status = "running"
            await event_bus.emit(
                EventType.TASK_UPDATED, run.session_id, {"run_id": run.id, "task": task.to_dict()}
            )
            dependency_context = "\n\n".join(
                f"Result of {dep}:\n{results.get(dep, '')[:2000]}" for dep in task.depends_on
            )
            agent_id = f"{task.agent}-{task.id}"
            worker = AgentLoop(
                session_id=run.session_id,
                agent_id=agent_id,
                profile=get_profile(task.agent),
                model=model,
                extra_context="\n\n".join(part for part in (context, dependency_context) if part),
            )
            run.workers[agent_id] = worker
            instruction = (
                f"TASK: {task.title}\n\n{task.description}\n\n"
                f"ACCEPTANCE CRITERIA: {task.acceptance or 'Task is fully completed and verified.'}\n\n"
                f"OVERALL GOAL: {run.goal}"
            )
            try:
                result = await worker.run(instruction)
                task.result = result.output
                results[task.id] = result.output
                task.status = "done" if result.stopped_reason != "error" else "failed"
            except Exception as exc:
                task.status = "failed"
                task.result = str(exc)
            await event_bus.emit(
                EventType.TASK_UPDATED, run.session_id, {"run_id": run.id, "task": task.to_dict()}
            )

    async def _synthesise(self, run: Run, results: dict[str, str]) -> str:
        if not run.plan:
            return ""
        transcript = "\n\n".join(
            f"[{task.id}] {task.title} ({task.status})\n{task.result[:2500]}" for task in run.plan.tasks
        )
        response = await get_router().complete(
            [Message(role="user", content=f"GOAL: {run.goal}\n\nRESULTS:\n{transcript}")],
            system=SYNTHESIS_PROMPT,
            temperature=0.3,
            max_tokens=2000,
        )
        return response.content


@lru_cache
def get_orchestrator() -> Orchestrator:
    return Orchestrator()
