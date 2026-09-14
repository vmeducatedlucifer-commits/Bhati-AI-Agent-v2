"""Swarm facade: spawn, coordinate and observe hundreds of agents.

Topology
--------
    user goal
        |
     [queen]            <- decomposes, forms teams, resolves conflicts
      /  |  \\
  [lead][lead][lead]    <- one per team, talks on the `leads` topic
    /|\\   /|\\   /|\\
  workers workers ...   <- do the actual tool work, talk on their team topic

All chatter flows through `SwarmBus`, shared knowledge through `Blackboard`,
and disagreement is resolved by `debate.run_debate`.
"""

from __future__ import annotations

import asyncio
import time
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
from app.swarm.blackboard import get_blackboard
from app.swarm.bus import BROADCAST, MessageKind, get_swarm_bus
from app.swarm.debate import run_debate
from app.swarm.registry import AgentRecord, get_agent_registry
from app.swarm.scheduler import SwarmScheduler
from app.swarm.teams import DEFAULT_TEAMS, Team, TeamSpec

log = get_logger("swarm")


@dataclass
class SwarmRun:
    id: str
    session_id: str
    goal: str
    size: int
    status: str = "running"
    plan: Plan | None = None
    teams: dict[str, Team] = field(default_factory=dict)
    output: str = ""
    started_at: float = field(default_factory=time.time)
    scheduler: SwarmScheduler | None = None
    task: asyncio.Task | None = None
    loops: dict[str, AgentLoop] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "goal": self.goal,
            "size": self.size,
            "status": self.status,
            "teams": [team.to_dict() for team in self.teams.values()],
            "plan": self.plan.to_dict() if self.plan else None,
            "output": self.output,
            "elapsed": round(time.time() - self.started_at, 1),
            "scheduler": self.scheduler.stats.to_dict() if self.scheduler else None,
        }


class Swarm:
    def __init__(self) -> None:
        self._runs: dict[str, SwarmRun] = {}
        self.bus = get_swarm_bus()
        self.board = get_blackboard()
        self.registry = get_agent_registry()

    # ------------------------------------------------------------------ api
    def get(self, run_id: str) -> SwarmRun | None:
        return self._runs.get(run_id)

    def list(self, session_id: str | None = None) -> list[SwarmRun]:
        return [
            run for run in self._runs.values() if session_id is None or run.session_id == session_id
        ]

    async def cancel(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if not run:
            return False
        run.status = "cancelled"
        for loop in run.loops.values():
            loop.cancel()
        if run.scheduler:
            await run.scheduler.stop()
        if run.task:
            run.task.cancel()
        return True

    async def launch(
        self,
        session_id: str,
        goal: str,
        size: int | None = None,
        model: str | None = None,
        team_specs: list[TeamSpec] | None = None,
        debate_on_conflict: bool = True,
    ) -> SwarmRun:
        size = max(1, min(size or settings.swarm_default_agents, settings.swarm_max_agents))
        run = SwarmRun(
            id=uuid.uuid4().hex[:12], session_id=session_id, goal=goal, size=size
        )
        self._runs[run.id] = run
        run.task = asyncio.create_task(
            self._execute(run, model=model, team_specs=team_specs, debate=debate_on_conflict)
        )
        return run

    # -------------------------------------------------------------- internals
    async def _execute(
        self,
        run: SwarmRun,
        model: str | None,
        team_specs: list[TeamSpec] | None,
        debate: bool,
    ) -> None:
        session_id = run.session_id
        try:
            await self.bus.say(
                session_id,
                sender="queen",
                content=f"Swarm launched with up to {run.size} agents. Goal: {run.goal}",
                kind=MessageKind.ANNOUNCE,
            )

            # 1. Queen decomposes the goal.
            run.plan = await create_plan(run.goal, context=self.board.digest(session_id))
            await event_bus.emit(
                EventType.PLAN_CREATED,
                session_id,
                {"run_id": run.id, "plan": run.plan.to_dict(), "swarm": True},
            )
            self.board.post(
                session_id, "goal", run.goal, author="queen", kind="decision"
            )

            # 2. Form teams and leads.
            specs = team_specs or DEFAULT_TEAMS
            run.teams = self._form_teams(run, specs)

            # 3. Scheduler sized to the swarm, capped by settings.
            run.scheduler = SwarmScheduler(
                max_agents=min(run.size, settings.swarm_max_agents),
                llm_concurrency=settings.swarm_llm_concurrency,
            )
            await run.scheduler.start(lambda payload: self._run_task(run, payload, model))

            # 4. Feed ready tasks, wave by wave, until the plan is done.
            while run.plan.unfinished() and run.status == "running":
                ready = run.plan.ready()
                if not ready:
                    break
                for task in ready:
                    task.status = "running"
                    await run.scheduler.submit(task, priority=len(task.depends_on))
                await run.scheduler.queue.join()

            # 5. Resolve any conflicting results by debate.
            if debate and run.plan and self._has_conflict(run.plan):
                participants = [
                    (record.id, record.role) for record in self.registry.list(session_id)[:8]
                ]
                if len(participants) >= 2:
                    await run_debate(
                        session_id,
                        question=f"Which result best achieves: {run.goal}?",
                        participants=participants,
                        context=self.board.digest(session_id),
                        model=model,
                    )

            run.output = await self._synthesise(run)
            run.status = "completed"
            await self.bus.say(
                session_id, "queen", "Swarm finished.", kind=MessageKind.RESULT
            )
        except asyncio.CancelledError:
            run.status = "cancelled"
            raise
        except Exception as exc:
            log.error("swarm_failed", run=run.id, error=str(exc))
            run.status = "failed"
            run.output = f"Swarm failed: {exc}"
            await event_bus.emit(EventType.ERROR, run.session_id, {"error": str(exc)})
        finally:
            if run.scheduler:
                await run.scheduler.stop()

    def _form_teams(self, run: SwarmRun, specs: list[TeamSpec]) -> dict[str, Team]:
        teams: dict[str, Team] = {}
        budget = run.size
        for spec in specs:
            if budget <= 0:
                break
            share = max(1, min(spec.size, budget))
            budget -= share
            team = Team(name=spec.name, objective=spec.objective)
            lead_id = f"{spec.name}-lead"
            team.lead_id = lead_id
            self.bus.join(lead_id, topics=[team.topic, "leads", "general"])
            self.registry.register(
                AgentRecord(
                    id=lead_id, session_id=run.session_id, role=spec.lead_role, team=spec.name
                )
            )
            for index in range(share):
                member_id = f"{spec.name}-{index + 1}"
                role = spec.member_roles[index % len(spec.member_roles)]
                team.member_ids.append(member_id)
                self.bus.join(member_id, topics=[team.topic, "general"])
                self.registry.register(
                    AgentRecord(
                        id=member_id, session_id=run.session_id, role=role, team=spec.name
                    )
                )
            teams[spec.name] = team
        return teams

    def _pick_agent(self, run: SwarmRun, task: Task) -> tuple[str, str]:
        """Choose the least-loaded idle agent whose role matches the task."""
        candidates = [
            record
            for record in self.registry.list(run.session_id)
            if record.role == task.agent and record.status in {"idle", "done"}
        ] or [
            record
            for record in self.registry.list(run.session_id)
            if record.status in {"idle", "done"}
        ]
        if not candidates:
            agent_id = f"{task.agent}-{task.id}"
            self.bus.join(agent_id, topics=["general"])
            self.registry.register(
                AgentRecord(id=agent_id, session_id=run.session_id, role=task.agent, team="core")
            )
            return agent_id, "core"
        chosen = min(candidates, key=lambda record: record.steps)
        return chosen.id, chosen.team

    async def _run_task(self, run: SwarmRun, task: Task, model: str | None) -> str:
        session_id = run.session_id
        agent_id, team_name = self._pick_agent(run, task)
        team = run.teams.get(team_name)
        topic = team.topic if team else "general"

        self.registry.update(
            agent_id, status="working", task_id=task.id, current_action=task.title, model=model
        )
        await self.bus.say(
            session_id,
            agent_id,
            f"Taking task {task.id}: {task.title}",
            kind=MessageKind.STATUS,
            topic=topic,
        )

        inbox_digest = "\n".join(
            message.render() for message in await self.bus.receive(agent_id)
        )
        context_parts = [
            self.board.digest(session_id),
            f"TEAM: {team_name} - {team.objective}" if team else "",
            f"MESSAGES FROM OTHER AGENTS:\n{inbox_digest}" if inbox_digest else "",
            "You are part of a swarm. Use `swarm_say` to coordinate, `swarm_ask` to consult a "
            "specific agent, and `blackboard_post` to publish findings others need.",
        ]

        loop = AgentLoop(
            session_id=session_id,
            agent_id=agent_id,
            profile=get_profile(task.agent),
            model=model,
            extra_context="\n\n".join(part for part in context_parts if part),
        )
        run.loops[agent_id] = loop

        instruction = (
            f"TASK {task.id}: {task.title}\n\n{task.description}\n\n"
            f"ACCEPTANCE: {task.acceptance or 'Completed and verified.'}\n\n"
            f"SWARM GOAL: {run.goal}"
        )
        try:
            result = await loop.run(instruction, stream_text=False)
            task.result = result.output
            task.status = "done"
            self.board.post(
                session_id,
                key=f"result:{task.id}",
                value=result.output[:4000],
                author=agent_id,
                kind="artifact",
            )
            self.registry.update(
                agent_id,
                status="idle",
                steps=result.steps,
                tokens=result.usage.total_tokens,
                current_action="",
                task_id=None,
            )
            await self.bus.say(
                session_id,
                agent_id,
                f"Finished {task.id}. {result.output[:400]}",
                kind=MessageKind.RESULT,
                topic=topic,
            )
            if team and team.lead_id:
                await self.bus.say(
                    session_id,
                    agent_id,
                    f"Task {task.id} done, please review.",
                    recipient=team.lead_id,
                    kind=MessageKind.HANDOFF,
                    topic=topic,
                )
            return result.output
        except Exception as exc:
            task.status = "failed"
            task.result = str(exc)
            self.registry.update(agent_id, status="failed", current_action=str(exc)[:120])
            await self.bus.say(
                session_id,
                agent_id,
                f"Task {task.id} failed: {exc}. Need help.",
                kind=MessageKind.HELP,
                topic=topic,
            )
            return ""
        finally:
            await event_bus.emit(
                EventType.TASK_UPDATED,
                session_id,
                {"run_id": run.id, "task": task.to_dict(), "agent_id": agent_id},
            )

    @staticmethod
    def _has_conflict(plan: Plan) -> bool:
        done = [task for task in plan.tasks if task.status == "done" and task.result]
        return len(done) > 2

    async def _synthesise(self, run: SwarmRun) -> str:
        if not run.plan:
            return ""
        transcript = "\n\n".join(
            f"[{task.id}] {task.title} ({task.status})\n{task.result[:1500]}"
            for task in run.plan.tasks
        )
        board = self.board.digest(run.session_id, limit=30)
        response = await get_router().complete(
            [
                Message(
                    role="user",
                    content=f"GOAL: {run.goal}\n\nSWARM RESULTS:\n{transcript}\n\n{board}",
                )
            ],
            system=SYNTHESIS_PROMPT,
            temperature=0.3,
            max_tokens=2500,
        )
        return response.content

    # ------------------------------------------------------------ dashboard
    def snapshot(self, session_id: str) -> dict[str, Any]:
        return {
            "agents": [record.to_dict() for record in self.registry.list(session_id)],
            "summary": self.registry.summary(session_id),
            "messages": [m.to_dict() for m in self.bus.history(session_id, limit=200)],
            "message_stats": self.bus.stats(session_id),
            "blackboard": self.board.all(session_id),
            "runs": [run.to_dict() for run in self.list(session_id)],
        }


@lru_cache
def get_swarm() -> Swarm:
    return Swarm()
