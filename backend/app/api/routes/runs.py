"""Autonomous run control: start, inspect the task graph, cancel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agents.orchestrator import get_orchestrator
from app.api.deps import current_user, new_session_id
from app.api.schemas import RunRequest

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("")
async def start_run(request: RunRequest, _user: dict = Depends(current_user)) -> dict:
    session_id = request.session_id or new_session_id()
    run = await get_orchestrator().start(
        session_id, request.goal, model=request.model, autonomous=request.autonomous
    )
    return run.to_dict()


@router.get("")
async def list_runs(session_id: str | None = None, _user: dict = Depends(current_user)) -> list[dict]:
    return [run.to_dict() for run in get_orchestrator().list(session_id)]


@router.get("/{run_id}")
async def get_run(run_id: str, _user: dict = Depends(current_user)) -> dict:
    run = get_orchestrator().get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run.to_dict()


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, _user: dict = Depends(current_user)) -> dict:
    ok = await get_orchestrator().cancel(run_id)
    if not ok:
        raise HTTPException(404, "Run not found")
    return {"cancelled": True}
