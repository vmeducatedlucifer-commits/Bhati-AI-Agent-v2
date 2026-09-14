from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_and_info() -> None:
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        info = client.get("/api/info").json()
        assert info["name"] == "Bhati AI Agent v2"
        assert info["tools"] > 0


def test_tool_catalogue() -> None:
    with TestClient(app) as client:
        tools = client.get("/api/tools").json()
        assert any(tool["name"] == "run_command" for tool in tools)
