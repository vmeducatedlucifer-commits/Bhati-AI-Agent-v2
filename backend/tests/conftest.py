from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.tools.base import ToolContext


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(session_id="test", agent_id="test", workspace=tmp_path)
