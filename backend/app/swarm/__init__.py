"""Swarm layer: large-scale multi-agent coordination.

Components
----------
- `bus`       : agent-to-agent (A2A) message mesh with topics, direct messages and broadcasts
- `blackboard`: shared memory where agents publish findings, artifacts and claims
- `registry`  : live roster of agents, their role, team, status and load
- `teams`     : team/squad definitions with leads and shared objectives
- `debate`    : structured discussion + voting/consensus between agents
- `scheduler` : work-stealing queue that keeps up to `swarm_max_agents` workers busy
- `swarm`     : the facade used by the API and the dashboard
"""

from app.swarm.blackboard import Blackboard, get_blackboard
from app.swarm.bus import AgentMessage, MessageKind, SwarmBus, get_swarm_bus
from app.swarm.registry import AgentRecord, AgentRegistry, get_agent_registry
from app.swarm.swarm import Swarm, get_swarm
from app.swarm.teams import Team, TeamSpec

__all__ = [
    "AgentMessage",
    "MessageKind",
    "SwarmBus",
    "get_swarm_bus",
    "Blackboard",
    "get_blackboard",
    "AgentRecord",
    "AgentRegistry",
    "get_agent_registry",
    "Team",
    "TeamSpec",
    "Swarm",
    "get_swarm",
]
