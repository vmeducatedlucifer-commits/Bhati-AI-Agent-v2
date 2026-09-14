"""Structured discussion between agents: propose -> critique -> vote -> decide.

This is what makes the swarm more than parallel workers: agents argue, converge
and record the decision on the blackboard. Every message is on the A2A bus, so
the dashboard shows the discussion live.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.llm.base import Message
from app.llm.router import get_router
from app.swarm.blackboard import get_blackboard
from app.swarm.bus import MessageKind, get_swarm_bus

log = get_logger("swarm.debate")

PROPOSE = (
    "You are {agent} ({role}) in a multi-agent swarm.\n"
    "Question: {question}\n\n{context}\n\n"
    "Give your proposed answer in under 150 words. Be specific and decisive."
)

CRITIQUE = (
    "You are {agent} ({role}). Critique the proposals below for the question: {question}\n\n"
    "{proposals}\n\n"
    "In under 120 words: name the strongest proposal, its weakness, and what would fix it."
)

VOTE = (
    "You are {agent} ({role}). Given the question and the discussion, vote for exactly one option.\n"
    "Question: {question}\n\n{proposals}\n\n{critiques}\n\n"
    "Reply with ONLY the proposer's agent id on the first line, then one short reason."
)


@dataclass(slots=True)
class DebateResult:
    question: str
    winner: str | None
    decision: str
    votes: dict[str, int] = field(default_factory=dict)
    proposals: dict[str, str] = field(default_factory=dict)
    critiques: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "winner": self.winner,
            "decision": self.decision,
            "votes": self.votes,
            "proposals": self.proposals,
            "critiques": self.critiques,
        }


async def _ask(prompt: str, model: str | None, temperature: float = 0.5) -> str:
    response = await get_router().complete(
        [Message(role="user", content=prompt)], model=model, temperature=temperature, max_tokens=600
    )
    return response.content.strip()


async def run_debate(
    session_id: str,
    question: str,
    participants: list[tuple[str, str]],  # (agent_id, role)
    context: str = "",
    model: str | None = None,
    rounds: int = 1,
    topic: str = "debate",
) -> DebateResult:
    bus = get_swarm_bus()
    board = get_blackboard()

    await bus.say(
        session_id,
        sender="moderator",
        content=f"Debate opened: {question}",
        kind=MessageKind.ANNOUNCE,
        topic=topic,
    )

    # 1. Proposals (parallel)
    async def propose(agent_id: str, role: str) -> tuple[str, str]:
        text = await _ask(
            PROPOSE.format(agent=agent_id, role=role, question=question, context=context), model
        )
        await bus.say(session_id, agent_id, text, kind=MessageKind.PROPOSAL, topic=topic)
        return agent_id, text

    proposals = dict(await asyncio.gather(*(propose(a, r) for a, r in participants)))
    proposal_text = "\n\n".join(f"{agent}: {text}" for agent, text in proposals.items())

    # 2. Critiques (parallel, optionally multiple rounds)
    critiques: dict[str, str] = {}
    for _ in range(max(1, rounds)):

        async def critique(agent_id: str, role: str) -> tuple[str, str]:
            text = await _ask(
                CRITIQUE.format(
                    agent=agent_id, role=role, question=question, proposals=proposal_text
                ),
                model,
            )
            await bus.say(session_id, agent_id, text, kind=MessageKind.CRITIQUE, topic=topic)
            return agent_id, text

        critiques = dict(await asyncio.gather(*(critique(a, r) for a, r in participants)))

    critique_text = "\n\n".join(f"{agent}: {text}" for agent, text in critiques.items())

    # 3. Vote (parallel)
    async def vote(agent_id: str, role: str) -> str:
        text = await _ask(
            VOTE.format(
                agent=agent_id,
                role=role,
                question=question,
                proposals=proposal_text,
                critiques=critique_text,
            ),
            model,
            temperature=0.1,
        )
        await bus.say(session_id, agent_id, text, kind=MessageKind.VOTE, topic=topic)
        first_line = text.splitlines()[0].strip() if text else ""
        for candidate in proposals:
            if candidate in first_line:
                return candidate
        return first_line[:40]

    ballots = await asyncio.gather(*(vote(a, r) for a, r in participants))
    tally = Counter(ballot for ballot in ballots if ballot)
    winner = tally.most_common(1)[0][0] if tally else None
    decision = proposals.get(winner or "", "")

    if winner:
        board.post(
            session_id,
            key=f"decision:{question[:60]}",
            value=decision,
            author="swarm",
            kind="decision",
            confidence=round(tally[winner] / max(1, len(ballots)), 2),
        )
        await bus.say(
            session_id,
            sender="moderator",
            content=f"Consensus: {winner} ({tally[winner]}/{len(ballots)} votes)",
            kind=MessageKind.ANNOUNCE,
            topic=topic,
        )

    return DebateResult(
        question=question,
        winner=winner,
        decision=decision,
        votes=dict(tally),
        proposals=proposals,
        critiques=critiques,
    )
