"""Workspace manager.

Layout on disk (root = `WORKSPACE_DIR`, `/tmp/workspaces` on Render free):

    <root>/<session_id>/                 main agent workspace (session root)
    <root>/<session_id>/agents/<id>/     one private home per swarm agent
    <root>/<session_id>/shared/          deliverables every agent can read
    <root>/<session_id>/downloads/       final artifacts surfaced in the UI

Every agent's tool sandbox is the *session* root, so agents can collaborate by
reading each other's folders, while each one still owns a private home dir.
Escaping the session root is blocked by `ToolContext.resolve`.
"""

from __future__ import annotations

import io
import mimetypes
import shutil
import time
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("workspace")

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".next", "dist", "build", ".cache"}
TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".csv", ".tsv", ".html", ".htm", ".css", ".scss", ".sh", ".bash",
    ".sql", ".xml", ".env", ".gitignore", ".dockerfile", ".go", ".rs", ".java", ".kt", ".rb",
    ".php", ".c", ".h", ".cpp", ".hpp", ".swift", ".log", ".conf", ".svg",
}
PREVIEW_LIMIT = 400_000  # chars


@dataclass(slots=True)
class FileNode:
    name: str
    path: str            # relative to the session root
    type: str            # "file" | "dir"
    size: int = 0
    modified: float = 0.0
    mime: str | None = None
    children: list["FileNode"] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "size": self.size,
            "modified": self.modified,
        }
        if self.mime:
            data["mime"] = self.mime
        if self.children is not None:
            data["children"] = [child.to_dict() for child in self.children]
        return data


class WorkspaceManager:
    """Create, inspect, export and clean per-session / per-agent workspaces."""

    # ------------------------------------------------------------- locations
    @property
    def root(self) -> Path:
        root = settings.workspace_path
        root.mkdir(parents=True, exist_ok=True)
        return root

    def session_dir(self, session_id: str, create: bool = True) -> Path:
        safe = self._safe_name(session_id)
        path = self.root / safe
        if create:
            for sub in ("", "agents", "shared", "downloads"):
                (path / sub).mkdir(parents=True, exist_ok=True)
        return path

    def agent_dir(self, session_id: str, agent_id: str, create: bool = True) -> Path:
        if not agent_id or agent_id == "main":
            return self.session_dir(session_id, create=create)
        path = self.session_dir(session_id, create=create) / "agents" / self._safe_name(agent_id)
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def shared_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "shared"

    def downloads_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "downloads"

    def relative_home(self, agent_id: str) -> str:
        """Path of an agent's private home, relative to the session root."""
        if not agent_id or agent_id == "main":
            return "."
        return f"agents/{self._safe_name(agent_id)}"

    def briefing(self, session_id: str, agent_id: str) -> str:
        """Prompt snippet telling an agent where to put its work."""
        home = self.relative_home(agent_id)
        return (
            "WORKSPACE RULES\n"
            f"- Your private folder: `{home}/` (create all scratch files here).\n"
            "- Shared folder every agent can read: `shared/`.\n"
            "- Final deliverables the user will download: `downloads/`.\n"
            "- Always use relative paths with the file tools; never write outside the workspace.\n"
            "- When a task produces an artifact (code, report, csv, doc), write it to a real "
            "file so the user can download it, then mention the filename in your answer."
        )

    # ----------------------------------------------------------------- safety
    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = "".join(ch for ch in (value or "default") if ch.isalnum() or ch in "-_.")
        cleaned = cleaned.strip(".") or "default"
        return cleaned[:128]

    def resolve(self, session_id: str, relative: str = "") -> Path:
        base = self.session_dir(session_id).resolve()
        target = (base / (relative or "")).resolve()
        if not str(target).startswith(str(base)):
            raise PermissionError(f"Path escapes workspace: {relative}")
        return target

    # ------------------------------------------------------------- inspection
    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for entry in sorted(self.root.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            files, size, newest = self._usage(entry)
            sessions.append(
                {
                    "session_id": entry.name,
                    "files": files,
                    "bytes": size,
                    "modified": newest,
                    "agents": len(list((entry / "agents").iterdir()))
                    if (entry / "agents").is_dir()
                    else 0,
                }
            )
        return sorted(sessions, key=lambda s: s["modified"], reverse=True)

    def list_agents(self, session_id: str) -> list[dict[str, Any]]:
        agents_root = self.session_dir(session_id) / "agents"
        out: list[dict[str, Any]] = []
        if agents_root.is_dir():
            for entry in sorted(agents_root.iterdir(), key=lambda p: p.name):
                if not entry.is_dir():
                    continue
                files, size, newest = self._usage(entry)
                out.append(
                    {
                        "agent_id": entry.name,
                        "path": f"agents/{entry.name}",
                        "files": files,
                        "bytes": size,
                        "modified": newest,
                    }
                )
        for special in ("shared", "downloads"):
            path = self.session_dir(session_id) / special
            if path.is_dir():
                files, size, newest = self._usage(path)
                out.append(
                    {
                        "agent_id": special,
                        "path": special,
                        "files": files,
                        "bytes": size,
                        "modified": newest,
                        "special": True,
                    }
                )
        return out

    def tree(self, session_id: str, relative: str = "", depth: int = 6) -> list[dict[str, Any]]:
        base = self.resolve(session_id, relative)
        if not base.exists():
            return []
        session_root = self.session_dir(session_id).resolve()

        def walk(directory: Path, level: int) -> list[FileNode]:
            nodes: list[FileNode] = []
            try:
                entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            except OSError:
                return nodes
            for item in entries:
                if item.name in SKIP_DIRS:
                    continue
                try:
                    stat = item.stat()
                except OSError:
                    continue
                rel = str(item.resolve().relative_to(session_root))
                if item.is_dir():
                    nodes.append(
                        FileNode(
                            name=item.name,
                            path=rel,
                            type="dir",
                            modified=stat.st_mtime,
                            children=walk(item, level + 1) if level < depth else [],
                        )
                    )
                else:
                    nodes.append(
                        FileNode(
                            name=item.name,
                            path=rel,
                            type="file",
                            size=stat.st_size,
                            modified=stat.st_mtime,
                            mime=mimetypes.guess_type(item.name)[0] or "application/octet-stream",
                        )
                    )
            return nodes

        if base.is_file():
            stat = base.stat()
            return [
                FileNode(
                    name=base.name,
                    path=str(base.relative_to(session_root)),
                    type="file",
                    size=stat.st_size,
                    modified=stat.st_mtime,
                    mime=mimetypes.guess_type(base.name)[0],
                ).to_dict()
            ]
        return [node.to_dict() for node in walk(base, 1)]

    def is_text(self, path: Path) -> bool:
        if path.suffix.lower() in TEXT_SUFFIXES:
            return True
        try:
            chunk = path.open("rb").read(2048)
        except OSError:
            return False
        return b"\x00" not in chunk

    def preview(self, session_id: str, relative: str) -> dict[str, Any]:
        target = self.resolve(session_id, relative)
        if not target.is_file():
            raise FileNotFoundError(relative)
        stat = target.stat()
        info: dict[str, Any] = {
            "path": relative,
            "name": target.name,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "mime": mimetypes.guess_type(target.name)[0] or "application/octet-stream",
            "text": None,
            "binary": True,
            "truncated": False,
        }
        if self.is_text(target):
            content = target.read_text(encoding="utf-8", errors="replace")
            info["binary"] = False
            info["truncated"] = len(content) > PREVIEW_LIMIT
            info["text"] = content[:PREVIEW_LIMIT]
        return info

    def write(self, session_id: str, relative: str, content: str | bytes) -> dict[str, Any]:
        target = self.resolve(session_id, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            target.write_text(content, encoding="utf-8")
        else:
            target.write_bytes(content)
        stat = target.stat()
        return {"path": relative, "size": stat.st_size, "modified": stat.st_mtime}

    def delete(self, session_id: str, relative: str) -> bool:
        target = self.resolve(session_id, relative)
        if target == self.session_dir(session_id).resolve():
            raise PermissionError("Refusing to delete the session root")
        if not target.exists():
            return False
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return True

    # ---------------------------------------------------------------- export
    def archive(self, session_id: str, relative: str = "") -> tuple[io.BytesIO, str]:
        base = self.resolve(session_id, relative)
        if not base.exists():
            raise FileNotFoundError(relative or session_id)
        buffer = io.BytesIO()
        label = (relative.strip("/").replace("/", "-") or session_id)
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
            if base.is_file():
                bundle.write(base, arcname=base.name)
            else:
                for file in base.rglob("*"):
                    if file.is_dir() or any(part in SKIP_DIRS for part in file.parts):
                        continue
                    try:
                        bundle.write(file, arcname=str(file.relative_to(base)))
                    except OSError:
                        continue
        buffer.seek(0)
        return buffer, f"{label}.zip"

    def stats(self, session_id: str) -> dict[str, Any]:
        base = self.session_dir(session_id)
        files, size, newest = self._usage(base)
        return {
            "session_id": session_id,
            "path": str(base),
            "files": files,
            "bytes": size,
            "modified": newest,
            "ephemeral": settings.ephemeral_workspace,
            "agents": self.list_agents(session_id),
        }

    @staticmethod
    def _usage(path: Path) -> tuple[int, int, float]:
        files = 0
        size = 0
        newest = 0.0
        for item in path.rglob("*"):
            if item.is_dir() or any(part in SKIP_DIRS for part in item.parts):
                continue
            try:
                stat = item.stat()
            except OSError:
                continue
            files += 1
            size += stat.st_size
            newest = max(newest, stat.st_mtime)
        return files, size, newest or time.time()


@lru_cache
def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


workspaces = get_workspace_manager()
