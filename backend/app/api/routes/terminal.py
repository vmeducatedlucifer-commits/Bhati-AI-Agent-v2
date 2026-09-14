"""WebSocket multi-terminal: every agent can own a live shell in the dashboard."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.api.deps import current_user
from app.api.schemas import TerminalCreate
from app.core.events import EventType, event_bus
from app.core.logging import get_logger
from app.sandbox.terminal import terminal_manager

router = APIRouter(prefix="/terminals", tags=["terminals"])
log = get_logger("api.terminal")


@router.post("")
async def create_terminal(payload: TerminalCreate, _user: dict = Depends(current_user)) -> dict:
    terminal = await terminal_manager.create(payload.session_id, payload.agent_id, payload.cwd)
    return {"id": terminal.id, "agent_id": terminal.agent_id, "cwd": str(terminal.cwd)}


@router.get("")
async def list_terminals(session_id: str | None = None, _user: dict = Depends(current_user)) -> list[dict]:
    return [
        {"id": terminal.id, "agent_id": terminal.agent_id, "cwd": str(terminal.cwd), "alive": terminal.alive}
        for terminal in terminal_manager.list(session_id)
    ]


@router.delete("/{terminal_id}")
async def kill_terminal(terminal_id: str, _user: dict = Depends(current_user)) -> dict:
    if not await terminal_manager.kill(terminal_id):
        raise HTTPException(404, "Terminal not found")
    return {"killed": True}


@router.websocket("/ws/{terminal_id}")
async def terminal_socket(websocket: WebSocket, terminal_id: str) -> None:
    await websocket.accept()
    terminal = terminal_manager.get(terminal_id)
    if terminal is None:
        await websocket.send_text(json.dumps({"type": "error", "message": "terminal not found"}))
        await websocket.close()
        return

    await websocket.send_text(json.dumps({"type": "history", "data": "".join(terminal.buffer[-400:])}))
    queue = event_bus.subscribe(terminal.session_id)

    async def pump_out() -> None:
        while True:
            event = await queue.get()
            if event.type is EventType.TERMINAL_OUTPUT and event.data.get("terminal_id") == terminal_id:
                await websocket.send_text(json.dumps({"type": "output", "data": event.data["chunk"]}))

    task = asyncio.create_task(pump_out())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"type": "input", "data": raw}
            if payload.get("type") == "input":
                await terminal_manager.write(terminal_id, payload.get("data", ""))
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        event_bus.unsubscribe(terminal.session_id, queue)
