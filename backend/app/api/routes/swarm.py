"""Swarm API: launch swarms, watch agents talk, read the shared blackboard."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.swarm.blackboard import get_blackboard
from app.swarm.bus import get_swarm_bus
from app.swarm.debate import run_debate
from app.swarm.graph import build_graph
from app.swarm.registry import get_agent_registry
from app.swarm.swarm import get_swarm
from app.swarm.teams import DEFAULT_TEAMS, TeamSpec

router = APIRouter(prefix="/swarm", tags=["swarm"])


class LaunchRequest(BaseModel):
    session_id: str
    goal: str
    size: int = Field(default=0, ge=0, le=1200)
    model: str | None = None
    debate_on_conflict: bool = True
    teams: list[dict] | None = None


class DebateRequest(BaseModel):
    session_id: str
    question: str
    participants: int = 4
    model: str | None = None


@router.get("/config")
async def swarm_config() -> dict:
    return {
        "enabled": settings.swarm_enabled,
        "max_agents": settings.swarm_max_agents,
        "default_agents": settings.swarm_default_agents,
        "llm_concurrency": settings.swarm_llm_concurrency,
        "default_teams": [team.__dict__ for team in DEFAULT_TEAMS],
    }


@router.post("/launch")
async def launch(request: LaunchRequest) -> dict:
    if not settings.swarm_enabled:
        raise HTTPException(status_code=400, detail="Swarm is disabled")
    team_specs = [TeamSpec(**spec) for spec in request.teams] if request.teams else None
    run = await get_swarm().launch(
        session_id=request.session_id,
        goal=request.goal,
        size=request.size or None,
        model=request.model,
        team_specs=team_specs,
        debate_on_conflict=request.debate_on_conflict,
    )
    return run.to_dict()


@router.get("/runs")
async def list_runs(session_id: str | None = None) -> dict:
    return {"runs": [run.to_dict() for run in get_swarm().list(session_id)]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = get_swarm().get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.to_dict()


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict:
    return {"cancelled": await get_swarm().cancel(run_id)}


@router.get("/snapshot/{session_id}")
async def snapshot(session_id: str) -> dict:
    """Everything the swarm dashboard needs in one call."""
    return get_swarm().snapshot(session_id)


@router.get("/graph/{session_id}")
async def graph(
    session_id: str,
    window: float = Query(default=0, ge=0, description="Only count messages from the last N seconds"),
    limit: int = Query(default=4000, le=20000),
    include_broadcasts: bool = True,
) -> dict:
    """Agent-to-agent communication graph: nodes, weighted edges, hubs."""
    return build_graph(
        get_swarm_bus(),
        get_agent_registry(),
        session_id,
        window_seconds=window,
        limit=limit,
        include_broadcasts=include_broadcasts,
    )


@router.get("/agents/{session_id}")
async def agents(session_id: str, team: str | None = None) -> dict:
    registry = get_agent_registry()
    return {
        "agents": [record.to_dict() for record in registry.list(session_id, team=team)],
        "summary": registry.summary(session_id),
    }


@router.get("/messages/{session_id}")
async def messages(
    session_id: str,
    limit: int = Query(default=200, le=2000),
    topic: str | None = None,
    agent_id: str | None = None,
) -> dict:
    bus = get_swarm_bus()
    return {
        "messages": [
            message.to_dict()
            for message in bus.history(session_id, limit=limit, topic=topic, agent_id=agent_id)
        ],
        "stats": bus.stats(session_id),
    }


@router.get("/stream/{session_id}")
async def stream_conversation(session_id: str) -> StreamingResponse:
    """Live SSE feed of every agent-to-agent message (the 'what are they saying' view)."""
    bus = get_swarm_bus()
    queue = bus.watch(session_id)

    async def generator():
        try:
            for message in bus.history(session_id, limit=50):
                yield f"data: {json.dumps(message.to_dict())}\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(message.to_dict())}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unwatch(session_id, queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/blackboard/{session_id}")
async def blackboard(session_id: str, query: str = "", kind: str | None = None) -> dict:
    entries = get_blackboard().search(session_id, query=query, kind=kind, limit=500)
    return {"entries": [entry.to_dict() for entry in entries]}


@router.post("/debate")
async def debate(request: DebateRequest) -> dict:
    roster = get_agent_registry().list(request.session_id)[: request.participants]
    if len(roster) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 live agents to debate")
    result = await run_debate(
        request.session_id,
        request.question,
        [(record.id, record.role) for record in roster],
        context=get_blackboard().digest(request.session_id),
        model=request.model,
    )
    return result.to_dict()
