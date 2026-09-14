"""Shared API dependencies: auth and session resolution."""

from __future__ import annotations

import uuid

from fastapi import Header, HTTPException, status

from app.core.config import settings
from app.core.security import decode_token


async def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not settings.auth_enabled:
        return {"sub": "local", "role": "owner"}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        return decode_token(authorization.split(" ", 1)[1])
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc


def new_session_id() -> str:
    return uuid.uuid4().hex[:16]
