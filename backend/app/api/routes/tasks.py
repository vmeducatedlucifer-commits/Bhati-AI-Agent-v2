"""Task panel API: the user assigns work here and the swarm executes it."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.tasks.board import BoardTask, get_task_board

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CreateTask(BaseModel):
    session_id: str
    title: str
    description: str = ""
    acceptance: str = ""
    priority: int = Field(default=5, ge=1, le=10)
    assignee: str = "auto"
    mode: str = "swarm"
    size: int | None = Field(default=None, ge=1, le=1200)
    model: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    autostart: bool = True


class UpdateTask(BaseModel):
    title: str | None = None
    description: str | None = None
    acceptance: str | None = None
    priority: int | None = None
    assignee: str | None = None
    status: str | None = None
    model: str | None = None
    size: int | None = None


@router.get("")
async def list_tasks(session_id: str | None = None, status: str | None = None) -> dict:
    board = get_task_board()
    tasks = board.list(session_id, status)
    return {
        "tasks": [task.to_dict() for task in tasks],
        "stats": board.stats(session_id) if session_id else {},
    }


@router.post("")
async def create_task(request: CreateTask) -> dict:
    board = get_task_board()
    task = board.add(
        BoardTask(
            session_id=request.session_id,
            title=request.title,
            description=request.description,
            acceptance=request.acceptance,
            priority=request.priority,
            assignee=request.assignee,
            mode=request.mode,
            size=request.size,
            model=request.model,
            depends_on=request.depends_on,
            tags=request.tags,
        )
    )
    if request.autostart and not request.depends_on:
        await board.start(task.id)
    return task.to_dict()


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    task = get_task_board().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.patch("/{task_id}")
async def update_task(task_id: str, request: UpdateTask) -> dict:
    task = get_task_board().update(task_id, **request.model_dump(exclude_none=True))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.post("/{task_id}/start")
async def start_task(task_id: str) -> dict:
    task = await get_task_board().start(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    return {"cancelled": await get_task_board().cancel(task_id)}


@router.delete("/{task_id}")
async def delete_task(task_id: str) -> dict:
    return {"deleted": get_task_board().delete(task_id)}


@router.post("/start-all/{session_id}")
async def start_all(session_id: str) -> dict:
    return {"started": await get_task_board().start_all(session_id)}
