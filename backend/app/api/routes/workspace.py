"""Workspace API: browse, preview, download and export agent files."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.workspace.manager import get_workspace_manager

router = APIRouter(prefix="/workspace", tags=["workspace"])


def _manager():
    return get_workspace_manager()


@router.get("")
async def list_workspaces() -> dict[str, Any]:
    """All session workspaces on disk."""
    return {"sessions": _manager().list_sessions()}


@router.get("/{session_id}")
async def workspace_overview(session_id: str) -> dict[str, Any]:
    """Stats plus one entry per agent folder (and shared / downloads)."""
    return _manager().stats(session_id)


@router.get("/{session_id}/tree")
async def workspace_tree(
    session_id: str,
    path: str = Query("", description="Relative path inside the session workspace"),
    agent_id: str | None = Query(None, description="Scope the tree to one agent folder"),
    depth: int = Query(6, ge=1, le=12),
) -> dict[str, Any]:
    manager = _manager()
    relative = path
    if agent_id and not path:
        relative = manager.relative_home(agent_id)
        relative = "" if relative == "." else relative
    try:
        nodes = manager.tree(session_id, relative, depth=depth)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session_id": session_id, "path": relative, "nodes": nodes}


@router.get("/{session_id}/file")
async def workspace_file(session_id: str, path: str = Query(...)) -> dict[str, Any]:
    try:
        return _manager().preview(session_id, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {path}") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}/download")
async def download_file(session_id: str, path: str = Query(...)) -> FileResponse:
    manager = _manager()
    try:
        target = manager.resolve(session_id, path)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Not found: {path}")
    return FileResponse(target, filename=target.name, media_type="application/octet-stream")


@router.get("/{session_id}/archive")
async def download_archive(
    session_id: str,
    path: str = Query("", description="Sub-folder to zip; empty means the whole session"),
    agent_id: str | None = Query(None),
) -> StreamingResponse:
    manager = _manager()
    relative = path
    if agent_id and not path:
        relative = manager.relative_home(agent_id)
        relative = "" if relative == "." else relative
    try:
        buffer, filename = manager.archive(session_id, relative)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {relative}") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{session_id}/upload")
async def upload_file(
    session_id: str, file: UploadFile, path: str = Query("", description="Destination folder")
) -> dict[str, Any]:
    manager = _manager()
    destination = f"{path.rstrip('/')}/{file.filename}" if path else (file.filename or "upload.bin")
    try:
        return manager.write(session_id, destination, await file.read())
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{session_id}/file")
async def delete_file(session_id: str, path: str = Query(...)) -> dict[str, Any]:
    try:
        removed = _manager().delete(session_id, path)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail=f"Not found: {path}")
    return {"deleted": path}
