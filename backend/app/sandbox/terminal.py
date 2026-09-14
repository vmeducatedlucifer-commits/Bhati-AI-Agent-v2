"""Interactive PTY terminals — one per agent, streamed to the dashboard."""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core.events import EventType, event_bus
from app.core.logging import get_logger

log = get_logger("terminal")


@dataclass
class TerminalSession:
    id: str
    session_id: str
    agent_id: str
    cwd: Path
    process: asyncio.subprocess.Process
    buffer: list[str] = field(default_factory=list)
    reader_task: asyncio.Task | None = None

    @property
    def alive(self) -> bool:
        return self.process.returncode is None


class TerminalManager:
    """Spawns long-lived shells so multiple agents can work in parallel terminals."""

    def __init__(self, max_buffer: int = 2000) -> None:
        self._sessions: dict[str, TerminalSession] = {}
        self._max_buffer = max_buffer

    async def create(self, session_id: str, agent_id: str = "main", cwd: str | None = None) -> TerminalSession:
        workdir = Path(cwd) if cwd else settings.workspace_path / session_id
        workdir.mkdir(parents=True, exist_ok=True)
        shell = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
        process = await asyncio.create_subprocess_exec(
            shell,
            "-i",
            cwd=str(workdir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "TERM": "xterm-256color", "PS1": "bhati$ "},
        )
        terminal = TerminalSession(
            id=uuid.uuid4().hex[:12],
            session_id=session_id,
            agent_id=agent_id,
            cwd=workdir,
            process=process,
        )
        terminal.reader_task = asyncio.create_task(self._pump(terminal))
        self._sessions[terminal.id] = terminal
        log.info("terminal_created", terminal=terminal.id, agent=agent_id)
        return terminal

    async def _pump(self, terminal: TerminalSession) -> None:
        assert terminal.process.stdout is not None
        while True:
            chunk = await terminal.process.stdout.read(1024)
            if not chunk:
                break
            text = chunk.decode(errors="replace")
            terminal.buffer.append(text)
            if len(terminal.buffer) > self._max_buffer:
                del terminal.buffer[: len(terminal.buffer) - self._max_buffer]
            await event_bus.emit(
                EventType.TERMINAL_OUTPUT,
                terminal.session_id,
                {"terminal_id": terminal.id, "chunk": text},
                agent_id=terminal.agent_id,
            )

    async def write(self, terminal_id: str, data: str) -> bool:
        terminal = self._sessions.get(terminal_id)
        if not terminal or not terminal.alive or terminal.process.stdin is None:
            return False
        terminal.process.stdin.write(data.encode())
        await terminal.process.stdin.drain()
        return True

    def get(self, terminal_id: str) -> TerminalSession | None:
        return self._sessions.get(terminal_id)

    def list(self, session_id: str | None = None) -> list[TerminalSession]:
        return [
            terminal
            for terminal in self._sessions.values()
            if session_id is None or terminal.session_id == session_id
        ]

    async def kill(self, terminal_id: str) -> bool:
        terminal = self._sessions.pop(terminal_id, None)
        if not terminal:
            return False
        if terminal.reader_task:
            terminal.reader_task.cancel()
        if terminal.alive:
            terminal.process.kill()
            await terminal.process.wait()
        return True

    async def shutdown(self) -> None:
        for terminal_id in list(self._sessions):
            await self.kill(terminal_id)


terminal_manager = TerminalManager()
