"""Streaming chat endpoint (SSE) driven by the event bus."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agents.orchestrator import get_orchestrator
from app.api.deps import current_user, new_session_id
from app.api.schemas import ChatRequest
from app.core.events import event_bus
from app.core.logging import get_logger

router = APIRouter(prefix="/chat", tags=["chat"])
log = get_logger("api.chat")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/stream")
async def chat_stream(request: ChatRequest, _user: dict = Depends(current_user)) -> StreamingResponse:
    session_id = request.session_id or new_session_id()
    orchestrator = get_orchestrator()
    # NOTE: EventBus.subscribe/unsubscribe are async — they must be awaited,
    # otherwise `queue` is a coroutine and the stream blows up on first use.
    queue = await event_bus.subscribe(session_id)

    async def generate() -> AsyncGenerator[str, None]:
        yield _sse("session", {"session_id": session_id})
        worker: asyncio.Task | None = None
        if request.mode == "autonomous":
            run = await orchestrator.start(session_id, request.message, model=request.model)
            worker = run.task
            yield _sse("run", {"run_id": run.id})
        else:
            worker = asyncio.create_task(
                orchestrator.run_single(session_id, request.message, profile=request.profile, model=request.model)
            )
        try:
            while True:
                if worker is not None and worker.done() and queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield _sse(str(event.type), event.to_dict())
            if worker is not None and not worker.cancelled():
                error = worker.exception()
                if error is not None:
                    yield _sse("error", {"error": str(error)})
                else:
                    result = worker.result()
                    if isinstance(result, str) and result:
                        yield _sse("final", {"content": result})
        except asyncio.CancelledError:  # client disconnected
            if worker is not None:
                worker.cancel()
            raise
        finally:
            await event_bus.unsubscribe(session_id, queue)
            yield _sse("done", {"session_id": session_id})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("")
async def chat_once(request: ChatRequest, _user: dict = Depends(current_user)) -> dict:
    session_id = request.session_id or new_session_id()
    output = await get_orchestrator().run_single(
        session_id, request.message, profile=request.profile, model=request.model
    )
    return {"session_id": session_id, "content": output}
