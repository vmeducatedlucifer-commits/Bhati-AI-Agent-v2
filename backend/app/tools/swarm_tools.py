"""Tools that let an agent talk to the rest of the swarm."""

from __future__ import annotations

from app.swarm.blackboard import get_blackboard
from app.swarm.bus import BROADCAST, MessageKind, get_swarm_bus
from app.swarm.registry import get_agent_registry
from app.tools.base import Permission, Tool, ToolContext, ToolResult, tool_schema


async def swarm_say(ctx: ToolContext, content: str, topic: str = "general") -> ToolResult:
    await get_swarm_bus().say(
        ctx.session_id, ctx.agent_id, content, recipient=BROADCAST, topic=topic
    )
    return ToolResult.success("Broadcast sent to the swarm")


async def swarm_ask(ctx: ToolContext, agent_id: str, question: str, wait: int = 20) -> ToolResult:
    bus = get_swarm_bus()
    await bus.say(
        ctx.session_id, ctx.agent_id, question, recipient=agent_id, kind=MessageKind.REQUEST
    )
    replies = await bus.receive(ctx.agent_id, timeout=float(wait))
    if not replies:
        return ToolResult.success(f"Asked {agent_id}; no reply within {wait}s. Continue and check later.")
    return ToolResult.success("\n".join(reply.render() for reply in replies))


async def swarm_inbox(ctx: ToolContext, wait: int = 0) -> ToolResult:
    messages = await get_swarm_bus().receive(ctx.agent_id, timeout=float(wait))
    if not messages:
        return ToolResult.success("Inbox empty")
    return ToolResult.success("\n".join(message.render() for message in messages))


async def swarm_roster(ctx: ToolContext, team: str | None = None) -> ToolResult:
    records = get_agent_registry().list(ctx.session_id, team=team)
    if not records:
        return ToolResult.success("No other agents registered")
    lines = [
        f"- {record.id} ({record.role}, team {record.team}) status={record.status} {record.current_action[:60]}"
        for record in records[:200]
    ]
    return ToolResult.success("\n".join(lines), count=len(records))


async def blackboard_post(
    ctx: ToolContext, key: str, value: str, kind: str = "fact", confidence: float = 1.0
) -> ToolResult:
    entry = get_blackboard().post(
        ctx.session_id, key, value, author=ctx.agent_id, kind=kind, confidence=confidence
    )
    return ToolResult.success(f"Posted '{key}' (v{entry.version}) to the shared blackboard")


async def blackboard_read(ctx: ToolContext, query: str = "", kind: str | None = None) -> ToolResult:
    entries = get_blackboard().search(ctx.session_id, query=query, kind=kind)
    if not entries:
        return ToolResult.success("Blackboard empty for that query")
    lines = [f"- [{entry.kind}] {entry.key} (by {entry.author}): {str(entry.value)[:400]}" for entry in entries]
    return ToolResult.success("\n".join(lines))


async def swarm_debate(ctx: ToolContext, question: str, participants: int = 4) -> ToolResult:
    from app.swarm.debate import run_debate

    roster = get_agent_registry().list(ctx.session_id)[:participants]
    if len(roster) < 2:
        return ToolResult.failure("Need at least 2 agents to debate")
    result = await run_debate(
        ctx.session_id,
        question,
        [(record.id, record.role) for record in roster],
        context=get_blackboard().digest(ctx.session_id),
    )
    return ToolResult.success(
        f"Consensus ({result.winner}): {result.decision}", votes=result.votes
    )


SWARM_TOOLS = [
    Tool(
        name="swarm_say",
        description="Broadcast a message to the swarm (or a topic) so other agents can react.",
        parameters=tool_schema(
            content={"type": "string", "required": True},
            topic={"type": "string", "default": "general"},
        ),
        handler=swarm_say,
        permission=Permission.SAFE,
        tags=["swarm"],
    ),
    Tool(
        name="swarm_ask",
        description="Ask a specific agent a question and wait briefly for their reply.",
        parameters=tool_schema(
            agent_id={"type": "string", "required": True},
            question={"type": "string", "required": True},
            wait={"type": "integer", "default": 20},
        ),
        handler=swarm_ask,
        permission=Permission.SAFE,
        tags=["swarm"],
    ),
    Tool(
        name="swarm_inbox",
        description="Read messages other agents sent you.",
        parameters=tool_schema(wait={"type": "integer", "default": 0}),
        handler=swarm_inbox,
        permission=Permission.SAFE,
        tags=["swarm"],
    ),
    Tool(
        name="swarm_roster",
        description="List the agents in the swarm with their role, team and current status.",
        parameters=tool_schema(team={"type": "string"}),
        handler=swarm_roster,
        permission=Permission.SAFE,
        tags=["swarm"],
    ),
    Tool(
        name="blackboard_post",
        description="Publish a fact, artifact, risk or decision to the swarm's shared blackboard.",
        parameters=tool_schema(
            key={"type": "string", "required": True},
            value={"type": "string", "required": True},
            kind={
                "type": "string",
                "enum": ["fact", "artifact", "question", "decision", "risk", "metric"],
                "default": "fact",
            },
            confidence={"type": "number", "default": 1.0},
        ),
        handler=blackboard_post,
        permission=Permission.WRITE,
        tags=["swarm", "memory"],
    ),
    Tool(
        name="blackboard_read",
        description="Search what the rest of the swarm has already discovered.",
        parameters=tool_schema(query={"type": "string"}, kind={"type": "string"}),
        handler=blackboard_read,
        permission=Permission.SAFE,
        tags=["swarm", "memory"],
    ),
    Tool(
        name="swarm_debate",
        description="Run a propose/critique/vote debate among agents and return the consensus.",
        parameters=tool_schema(
            question={"type": "string", "required": True},
            participants={"type": "integer", "default": 4},
        ),
        handler=swarm_debate,
        permission=Permission.SAFE,
        tags=["swarm"],
    ),
]
