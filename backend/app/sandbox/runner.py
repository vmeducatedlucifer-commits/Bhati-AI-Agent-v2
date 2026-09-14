"""Command execution sandbox. Local subprocess (dev) or Docker container (prod)."""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("sandbox")

BLOCKED_PATTERNS = (
    "rm -rf /",
    ":(){:|:&};:",
    "mkfs",
    "dd if=/dev/zero of=/dev/",
    "shutdown",
    "reboot",
)


@dataclass(slots=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class BaseSandbox:
    async def exec(self, command: str, workdir: Path, timeout: int | None = None) -> ExecResult:
        raise NotImplementedError

    @staticmethod
    def guard(command: str) -> str | None:
        lowered = command.lower()
        for pattern in BLOCKED_PATTERNS:
            if pattern in lowered:
                return f"Blocked by safety policy: matches '{pattern}'"
        return None


class LocalSandbox(BaseSandbox):
    """Runs commands as a subprocess with a timeout and output caps."""

    async def exec(self, command: str, workdir: Path, timeout: int | None = None) -> ExecResult:
        blocked = self.guard(command)
        if blocked:
            return ExecResult(exit_code=126, stdout="", stderr=blocked)
        workdir.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout or settings.sandbox_timeout
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return ExecResult(124, "", f"Timed out after {timeout or settings.sandbox_timeout}s", True)
        return ExecResult(
            exit_code=process.returncode or 0,
            stdout=stdout.decode(errors="replace")[:200_000],
            stderr=stderr.decode(errors="replace")[:20_000],
        )


class DockerSandbox(BaseSandbox):
    """Runs each command in a disposable container with the workspace mounted."""

    def __init__(self, image: str) -> None:
        self.image = image

    async def exec(self, command: str, workdir: Path, timeout: int | None = None) -> ExecResult:
        blocked = self.guard(command)
        if blocked:
            return ExecResult(exit_code=126, stdout="", stderr=blocked)
        workdir.mkdir(parents=True, exist_ok=True)
        docker_cmd = (
            "docker run --rm --network bridge "
            "--memory 2g --cpus 2 --pids-limit 512 "
            f"-v {shlex.quote(str(workdir))}:/work -w /work {shlex.quote(self.image)} "
            f"bash -lc {shlex.quote(command)}"
        )
        process = await asyncio.create_subprocess_shell(
            docker_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout or settings.sandbox_timeout
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return ExecResult(124, "", "Container timed out", True)
        return ExecResult(
            exit_code=process.returncode or 0,
            stdout=stdout.decode(errors="replace")[:200_000],
            stderr=stderr.decode(errors="replace")[:20_000],
        )


@lru_cache
def get_sandbox() -> BaseSandbox:
    if settings.sandbox_mode.lower() == "docker":
        log.info("sandbox_mode", mode="docker", image=settings.sandbox_image)
        return DockerSandbox(settings.sandbox_image)
    log.info("sandbox_mode", mode="local")
    return LocalSandbox()
