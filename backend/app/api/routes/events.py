"""Global event stream for the dashboard (all agents, tasks, tools, terminals)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import current_user
from app.core.events import event_bus

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/{session_id}")
async def stream_events(session_id: str, _user: dict = Depends(current_user)) -> StreamingResponse:
    queue = event_bus.subscribe(session_id)

    async def generate() -> AsyncGenerator[str, None]:
        for event in event_bus.history(session_id)[-50:]:
            yield f"event: {event.type.value}\ndata: {json.dumps(event.to_dict(), default=str)}\n\n"
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {event.type.value}\ndata: {json.dumps(event.to_dict(), default=str)}\n\n"
        finally:
            event_bus.unsubscribe(session_id, queue)

    return StreamingResponse(generate(), media_type="text/event-stream")
