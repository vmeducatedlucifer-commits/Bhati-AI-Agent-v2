"""Voice control: speech-to-text, command execution and text-to-speech.

STT/TTS use OpenAI-compatible endpoints when a key is configured; the browser's
Web Speech API is the zero-config fallback used by the dashboard.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.agents.orchestrator import get_orchestrator
from app.api.deps import current_user, new_session_id
from app.api.schemas import VoiceCommand
from app.core.config import settings

router = APIRouter(prefix="/voice", tags=["voice"])
OPENAI_BASE = "https://api.openai.com/v1"


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), _user: dict = Depends(current_user)) -> dict:
    if not settings.openai_api_key:
        raise HTTPException(400, "OPENAI_API_KEY required for server-side STT; use browser STT instead")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{OPENAI_BASE}/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            files={"file": (file.filename or "audio.webm", await file.read(), file.content_type)},
            data={"model": "whisper-1"},
        )
    if response.status_code >= 400:
        raise HTTPException(response.status_code, response.text[:500])
    return {"text": response.json().get("text", "")}


@router.post("/speak")
async def speak(text: str, voice: str = "alloy", _user: dict = Depends(current_user)) -> Response:
    if not settings.openai_api_key:
        raise HTTPException(400, "OPENAI_API_KEY required for server-side TTS; use browser TTS instead")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{OPENAI_BASE}/audio/speech",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": "gpt-4o-mini-tts", "voice": voice, "input": text[:4000]},
        )
    if response.status_code >= 400:
        raise HTTPException(response.status_code, response.text[:500])
    return Response(content=response.content, media_type="audio/mpeg")


@router.post("/command")
async def command(payload: VoiceCommand, _user: dict = Depends(current_user)) -> dict:
    """Run a spoken instruction through the operator agent (device/browser control)."""
    session_id = payload.session_id or new_session_id()
    output = await get_orchestrator().run_single(session_id, payload.text, profile="operator")
    return {"session_id": session_id, "content": output}
