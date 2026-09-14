"""Workspace file browsing, reading, writing and upload."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import current_user
from app.core.config import settings

router = APIRouter(prefix="/files", tags=["files"])


def _root(session_id: str) -> Path:
    root = (settings.workspace_path / session_id).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe(session_id: str, relative: str) -> Path:
    root = _root(session_id)
    target = (root / relative.lstrip("/")).resolve()
    if not str(target).startswith(str(root)):
        raise HTTPException(400, "Path escapes the workspace")
    return target


@router.get("/tree")
async def tree(session_id: str, path: str = ".", _user: dict = Depends(current_user)) -> list[dict]:
    target = _safe(session_id, path)
    if not target.exists():
        return []
    return sorted(
        (
            {
                "name": child.name,
                "path": str(child.relative_to(_root(session_id))),
                "type": "dir" if child.is_dir() else "file",
                "size": child.stat().st_size if child.is_file() else 0,
            }
            for child in target.iterdir()
            if child.name not in {".git", "node_modules", "__pycache__"}
        ),
        key=lambda item: (item["type"] != "dir", item["name"]),
    )


@router.get("/read")
async def read(session_id: str, path: str, _user: dict = Depends(current_user)) -> dict:
    target = _safe(session_id, path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    return {"path": path, "content": target.read_text(encoding="utf-8", errors="replace")[:500_000]}


@router.get("/download")
async def download(session_id: str, path: str, _user: dict = Depends(current_user)) -> FileResponse:
    target = _safe(session_id, path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(target, filename=target.name)


@router.post("/upload")
async def upload(
    session_id: str, file: UploadFile = File(...), _user: dict = Depends(current_user)
) -> dict:
    target = _safe(session_id, file.filename or "upload.bin")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(await file.read())
    return {"path": str(target.relative_to(_root(session_id))), "size": target.stat().st_size}
