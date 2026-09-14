from __future__ import annotations

from pathlib import Path

import pytest

from app.sandbox.runner import LocalSandbox


@pytest.mark.asyncio
async def test_local_exec(tmp_path: Path) -> None:
    result = await LocalSandbox().exec("echo bhati", workdir=tmp_path, timeout=20)
    assert result.exit_code == 0
    assert "bhati" in result.stdout


@pytest.mark.asyncio
async def test_blocked_command(tmp_path: Path) -> None:
    result = await LocalSandbox().exec("rm -rf /", workdir=tmp_path)
    assert result.exit_code == 126
    assert "Blocked" in result.stderr
