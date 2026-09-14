"""Communication graph: who is talking to whom, how much, and about what.

The A2A bus stores raw messages; this module folds them into a graph the
dashboard can render: nodes (agents) + weighted directed edges (conversations),
plus derived signals like hubs, isolated agents and broadcast load.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from app.swarm.bus import BROADCAST, SwarmBus
from app.swarm.registry import AgentRegistry


def build_graph(
    bus: SwarmBus,
    registry: AgentRegistry,
    session_id: str,
    window_seconds: float = 0.0,
    limit: int = 4000,
    include_broadcasts: bool = True,
) -> dict[str, Any]:
    """Fold recent messages into a renderable graph.

    A broadcast is modelled as an edge from the sender to its topic hub node
    (`topic:<name>`), so the view stays readable instead of drawing n^2 edges.
    """
    messages = bus.history(session_id, limit=limit)
    if window_seconds > 0:
        cutoff = time.time() - window_seconds
        messages = [message for message in messages if message.timestamp >= cutoff]

    records = {record.id: record for record in registry.list(session_id)}

    edges: dict[tuple[str, str], dict[str, Any]] = {}
    sent: dict[str, int] = defaultdict(int)
    received: dict[str, int] = defaultdict(int)
    topics: set[str] = set()

    for message in messages:
        source = message.sender
        if message.recipient == BROADCAST:
            if not include_broadcasts:
                continue
            target = f"topic:{message.topic}"
            topics.add(message.topic)
        else:
            target = message.recipient

        sent[source] += 1
        received[target] += 1
        key = (source, target)
        edge = edges.get(key)
        if edge is None:
            edge = {
                "source": source,
                "target": target,
                "count": 0,
                "kinds": defaultdict(int),
                "last_kind": message.kind.value,
                "last_at": message.timestamp,
                "last_message": "",
                "broadcast": message.recipient == BROADCAST,
            }
            edges[key] = edge
        edge["count"] += 1
        edge["kinds"][message.kind.value] += 1
        edge["last_kind"] = message.kind.value
        edge["last_at"] = message.timestamp
        edge["last_message"] = message.content[:160]

    node_ids = set(records) | {edge["source"] for edge in edges.values()} | {
        edge["target"] for edge in edges.values()
    }

    nodes: list[dict[str, Any]] = []
    for node_id in sorted(node_ids):
        if node_id.startswith("topic:"):
            nodes.append(
                {
                    "id": node_id,
                    "label": node_id.removeprefix("topic:"),
                    "type": "topic",
                    "team": node_id.removeprefix("topic:").removeprefix("team:"),
                    "role": "topic",
                    "status": "idle",
                    "sent": sent.get(node_id, 0),
                    "received": received.get(node_id, 0),
                    "degree": sent.get(node_id, 0) + received.get(node_id, 0),
                }
            )
            continue
        record = records.get(node_id)
        nodes.append(
            {
                "id": node_id,
                "label": node_id,
                "type": "queen"
                if node_id in {"queen", "moderator"}
                else ("lead" if node_id.endswith("-lead") else "agent"),
                "team": record.team if record else "core",
                "role": record.role if record else "unknown",
                "status": record.status if record else "idle",
                "steps": record.steps if record else 0,
                "tokens": record.tokens if record else 0,
                "current_action": record.current_action if record else "",
                "sent": sent.get(node_id, 0),
                "received": received.get(node_id, 0),
                "degree": sent.get(node_id, 0) + received.get(node_id, 0),
            }
        )

    edge_list = [
        {**edge, "kinds": dict(edge["kinds"]), "id": f"{edge['source']}->{edge['target']}"}
        for edge in edges.values()
    ]
    edge_list.sort(key=lambda edge: -edge["count"])

    busiest = sorted(nodes, key=lambda node: -node["degree"])[:10]
    isolated = [
        node["id"] for node in nodes if node["degree"] == 0 and node["type"] == "agent"
    ]

    return {
        "nodes": nodes,
        "edges": edge_list,
        "topics": sorted(topics),
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edge_list),
            "message_count": len(messages),
            "density": round(len(edge_list) / max(1, len(nodes) * (len(nodes) - 1)), 4),
            "hubs": [{"id": node["id"], "degree": node["degree"]} for node in busiest],
            "isolated": isolated[:50],
            "window_seconds": window_seconds,
        },
    }
