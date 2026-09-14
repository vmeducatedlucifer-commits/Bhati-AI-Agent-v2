"""Tests for the agent-to-agent communication graph."""

from __future__ import annotations

import pytest

from app.swarm.bus import BROADCAST, MessageKind, SwarmBus
from app.swarm.graph import build_graph
from app.swarm.registry import AgentRecord, AgentRegistry


@pytest.fixture()
def wired() -> tuple[SwarmBus, AgentRegistry]:
    bus = SwarmBus()
    registry = AgentRegistry()
    for agent_id, role, team in [
        ("queen", "planner", "core"),
        ("build-lead", "lead", "build"),
        ("build-1", "coder", "build"),
        ("build-2", "coder", "build"),
    ]:
        registry.register(AgentRecord(id=agent_id, session_id="s1", role=role, team=team))
        bus.join(agent_id, topics=[f"team:{team}"])
    return bus, registry


@pytest.mark.asyncio
async def test_graph_has_weighted_directed_edges(wired):
    bus, registry = wired
    await bus.say("s1", "queen", "plan ready", recipient="build-lead")
    await bus.say("s1", "build-lead", "take task A", recipient="build-1")
    await bus.say("s1", "build-lead", "take task B", recipient="build-1")

    graph = build_graph(bus, registry, "s1")
    edges = {edge["id"]: edge for edge in graph["edges"]}

    assert edges["build-lead->build-1"]["count"] == 2
    assert edges["queen->build-lead"]["count"] == 1
    assert "build-1->build-lead" not in edges  # direction is preserved


@pytest.mark.asyncio
async def test_broadcast_collapses_into_topic_hub(wired):
    bus, registry = wired
    await bus.say("s1", "build-lead", "standup", recipient=BROADCAST, topic="team:build")

    graph = build_graph(bus, registry, "s1")
    hub = next(node for node in graph["nodes"] if node["type"] == "topic")
    edge = next(edge for edge in graph["edges"] if edge["target"] == hub["id"])

    assert hub["id"] == "topic:team:build"
    assert edge["broadcast"] is True

    filtered = build_graph(bus, registry, "s1", include_broadcasts=False)
    assert filtered["edges"] == []


@pytest.mark.asyncio
async def test_graph_reports_hubs_and_isolated_agents(wired):
    bus, registry = wired
    for _ in range(5):
        await bus.say("s1", "build-lead", "ping", recipient="build-1", kind=MessageKind.REQUEST)

    graph = build_graph(bus, registry, "s1")
    assert graph["stats"]["hubs"][0]["id"] in {"build-lead", "build-1"}
    assert "build-2" in graph["stats"]["isolated"]  # silent agent surfaces immediately
    assert graph["stats"]["message_count"] == 5


@pytest.mark.asyncio
async def test_time_window_filters_old_traffic(wired):
    bus, registry = wired
    await bus.say("s1", "queen", "old news", recipient="build-lead")
    bus.history("s1")[0].timestamp -= 3600

    recent = build_graph(bus, registry, "s1", window_seconds=60)
    assert recent["stats"]["message_count"] == 0
    assert build_graph(bus, registry, "s1")["stats"]["message_count"] == 1
