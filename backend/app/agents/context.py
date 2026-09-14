"""Conversation context management: token budgeting and compaction."""

from __future__ import annotations

from app.llm.base import Message

APPROX_CHARS_PER_TOKEN = 4


def estimate_tokens(messages: list[Message]) -> int:
    total = 0
    for message in messages:
        total += len(message.content) // APPROX_CHARS_PER_TOKEN
        for call in message.tool_calls:
            total += (len(call.name) + len(str(call.arguments))) // APPROX_CHARS_PER_TOKEN
    return total


def trim_history(messages: list[Message], max_tokens: int = 120_000, keep_recent: int = 12) -> list[Message]:
    """Drop the oldest middle turns when the window gets tight, keeping system + recent."""
    if estimate_tokens(messages) <= max_tokens:
        return messages
    system = [m for m in messages[:2] if m.role == "system"]
    body = messages[len(system) :]
    recent = body[-keep_recent:]
    dropped = len(body) - len(recent)
    if dropped <= 0:
        return messages
    note = Message(
        role="system",
        content=f"[context compacted: {dropped} earlier messages summarised away; ask memory tools if details are needed]",
    )
    return [*system, note, *recent]


async def summarize_history(messages: list[Message]) -> str:
    """LLM-based compaction used for long-running autonomous sessions."""
    from app.llm.router import get_router

    transcript = "\n".join(
        f"{message.role}: {message.content[:800]}" for message in messages if message.content
    )[:40_000]
    response = await get_router().complete(
        [Message(role="user", content=f"Summarise this agent session, keeping decisions, file paths, "
                                      f"open problems and next steps:\n\n{transcript}")],
        task="fast",
        temperature=0.2,
        max_tokens=1200,
    )
    return response.content
