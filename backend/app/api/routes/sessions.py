"""Session CRUD + message history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import current_user
from app.api.schemas import SessionCreate
from app.db.models import ChatMessage, Session
from app.db.session import get_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("")
async def create_session(
    payload: SessionCreate,
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(current_user),
) -> dict:
    record = Session(title=payload.title, model=payload.model, mode=payload.mode)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record.model_dump()


@router.get("")
async def list_sessions(
    limit: int = 50, db: AsyncSession = Depends(get_session), _user: dict = Depends(current_user)
) -> list[dict]:
    result = await db.exec(
        select(Session).where(Session.archived == False).order_by(Session.updated_at.desc()).limit(limit)  # noqa: E712
    )
    return [row.model_dump() for row in result.all()]


@router.get("/{session_id}/messages")
async def messages(
    session_id: str,
    limit: int = 200,
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(current_user),
) -> list[dict]:
    result = await db.exec(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).limit(limit)
    )
    return [row.model_dump() for row in result.all()]


@router.delete("/{session_id}")
async def delete_session(
    session_id: str, db: AsyncSession = Depends(get_session), _user: dict = Depends(current_user)
) -> dict:
    record = await db.get(Session, session_id)
    if not record:
        raise HTTPException(404, "Session not found")
    record.archived = True
    db.add(record)
    await db.commit()
    return {"archived": True}
