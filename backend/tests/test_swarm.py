"""Swarm layer tests: A2A bus, blackboard, scheduler, task board, custom models."""

from __future__ import annotations

import asyncio

import pytest

from app.llm.custom import CustomModel, CustomModelRegistry
from app.swarm.blackboard import Blackboard
from app.swarm.bus import BROADCAST, MessageKind, SwarmBus
from app.swarm.registry import AgentRecord, AgentRegistry
from app.swarm.scheduler import SwarmScheduler
from app.tasks.board import BoardTask, TaskBoard


@pytest.mark.asyncio
async def test_direct_message_reaches_recipient():
    bus = SwarmBus()
    bus.join("alpha")
    bus.join("beta")
    await bus.say("s1", "alpha", "can you review this?", recipient="beta", kind=MessageKind.REQUEST)

    inbox = await bus.receive("beta")
    assert len(inbox) == 1
    assert inbox[0].sender == "alpha"
    assert inbox[0].kind is MessageKind.REQUEST
    assert await bus.receive("alpha") == []  # sender does not get its own message


@pytest.mark.asyncio
async def test_broadcast_fans_out_to_topic_members_only():
    bus = SwarmBus()
    bus.join("a", topics=["team:build"])
    bus.join("b", topics=["team:build"])
    bus.join("c", topics=["team:research"])

    await bus.say("s1", "a", "build started", recipient=BROADCAST, topic="team:build")

    assert len(await bus.receive("b")) == 1
    assert await bus.receive("c") == []


@pytest.mark.asyncio
async def test_history_and_stats_power_the_dashboard():
    bus = SwarmBus()
    bus.join("a")
    bus.join("b")
    await bus.say("s1", "a", "hello")
    await bus.say("s1", "b", "vote: a", kind=MessageKind.VOTE)

    assert len(bus.history("s1")) == 2
    assert bus.stats("s1")["by_kind"]["vote"] == 1
    assert len(bus.history("s1", agent_id="b")) == 1


@pytest.mark.asyncio
async def test_watcher_receives_live_messages():
    bus = SwarmBus()
    bus.join("a")
    queue = bus.watch("s1")
    await bus.say("s1", "a", "live update")
    message = await asyncio.wait_for(queue.get(), timeout=1)
    assert message.content == "live update"


def test_blackboard_versions_and_digest():
    board = Blackboard()
    board.post("s1", "api_url", "http://x", author="researcher-1")
    entry = board.post("s1", "api_url", "http://y", author="researcher-2")

    assert entry.version == 2
    assert board.read("s1", "api_url").value == "http://y"
    assert "api_url" in board.digest("s1")
    assert board.search("s1", query="api")


def test_registry_summary_counts_by_status_role_team():
    registry = AgentRegistry()
    registry.register(AgentRecord(id="a", session_id="s1", role="coder", team="build"))
    registry.register(AgentRecord(id="b", session_id="s1", role="coder", team="build"))
    registry.update("a", status="working", steps=3, tokens=100)

    summary = registry.summary("s1")
    assert summary["total"] == 2
    assert summary["active"] == 1
    assert summary["by_team"]["build"] == 2
    assert summary["tokens"] == 100


@pytest.mark.asyncio
async def test_scheduler_processes_large_batch_with_bounded_concurrency():
    scheduler = SwarmScheduler(max_agents=50, llm_concurrency=8)
    peak = {"value": 0}
    live = {"value": 0}

    async def handler(payload: int) -> int:
        live["value"] += 1
        peak["value"] = max(peak["value"], live["value"])
        await asyncio.sleep(0.001)
        live["value"] -= 1
        return payload * 2

    await scheduler.start(handler)
    for index in range(500):
        await scheduler.submit(index)
    results = await scheduler.drain()
    await scheduler.stop()

    assert len(results) == 500
    assert scheduler.stats.completed == 500
    assert peak["value"] <= 8  # llm concurrency is respected


@pytest.mark.asyncio
async def test_scheduler_survives_failing_tasks():
    scheduler = SwarmScheduler(max_agents=4, llm_concurrency=2)

    async def handler(payload: int) -> int:
        if payload % 2 == 0:
            raise RuntimeError("boom")
        return payload

    await scheduler.start(handler)
    for index in range(10):
        await scheduler.submit(index)
    await scheduler.drain()
    await scheduler.stop()

    assert scheduler.stats.failed == 5
    assert scheduler.stats.completed == 5


def test_task_board_orders_by_priority_and_respects_dependencies():
    board = TaskBoard()
    first = board.add(BoardTask(session_id="s1", title="low", priority=9))
    urgent = board.add(BoardTask(session_id="s1", title="urgent", priority=1))
    blocked = board.add(
        BoardTask(session_id="s1", title="blocked", priority=2, depends_on=[first.id])
    )

    assert board.list("s1")[0].id == urgent.id
    ready_ids = {task.id for task in board.ready("s1")}
    assert urgent.id in ready_ids
    assert blocked.id not in ready_ids

    board.update(first.id, status="done")
    assert blocked.id in {task.id for task in board.ready("s1")}


def test_task_board_stats_and_delete():
    board = TaskBoard()
    task = board.add(BoardTask(session_id="s1", title="work"))
    assert board.stats("s1")["total"] == 1
    assert board.delete(task.id) is True
    assert board.stats("s1")["total"] == 0


def test_custom_model_registry_roundtrip(tmp_path):
    registry = CustomModelRegistry(path=tmp_path / "custom_models.json")
    registry.add(
        CustomModel(
            alias="my-vllm",
            base_url="http://localhost:8001/v1",
            model="Qwen2.5-72B",
            format="openai",
        )
    )
    assert registry.resolve("custom:my-vllm").model == "Qwen2.5-72B"
    assert registry.resolve("my-vllm") is not None
    assert registry.list()[0].public()["api_key"] == ""

    reloaded = CustomModelRegistry(path=tmp_path / "custom_models.json")
    assert reloaded.resolve("custom:my-vllm") is not None
    assert reloaded.remove("my-vllm") is True


def test_custom_model_rejects_bad_base_url(tmp_path):
    from app.core.errors import ConfigurationError

    registry = CustomModelRegistry(path=tmp_path / "m.json")
    with pytest.raises(ConfigurationError):
        registry.add(CustomModel(alias="bad", base_url="localhost:8001", model="x"))


def test_anthropic_gateway_url_building():
    from app.llm.anthropic import _messages_url

    assert _messages_url(None).endswith("api.anthropic.com/v1/messages")
    assert _messages_url("https://gw.example.com") == "https://gw.example.com/v1/messages"
    assert _messages_url("https://gw.example.com/v1") == "https://gw.example.com/v1/messages"
    assert _messages_url("https://gw.example.com/v1/messages") == "https://gw.example.com/v1/messages"
