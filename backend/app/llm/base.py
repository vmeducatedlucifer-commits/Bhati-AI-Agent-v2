"""Vendor-neutral LLM abstractions: messages, tool calls, streaming chunks."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        raw = raw.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}
        return parsed if isinstance(parsed, dict) else {"value": parsed}


@dataclass(slots=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": [
                {"id": c.id, "name": c.name, "arguments": c.arguments} for c in self.tool_calls
            ],
            "tool_call_id": self.tool_call_id,
            "name": self.name,
        }


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def merge(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


ChunkType = Literal["text", "thinking", "tool_call", "usage", "done"]


@dataclass(slots=True)
class StreamChunk:
    type: ChunkType
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None


@dataclass(slots=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""

    def as_message(self) -> Message:
        return Message(role="assistant", content=self.content, tool_calls=self.tool_calls)


class LLMProvider(ABC):
    """Every provider implements streaming chat with tool calling."""

    name: str = "base"
    supports_tools: bool = True

    @abstractmethod
    def stream(
        self,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Yield incremental chunks. Must end with a `done` chunk."""

    async def complete(
        self,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> LLMResponse:
        content: list[str] = []
        calls: list[ToolCall] = []
        usage = Usage()
        async for chunk in self.stream(
            messages, model, tools=tools, temperature=temperature, max_tokens=max_tokens, system=system
        ):
            if chunk.type == "text":
                content.append(chunk.text)
            elif chunk.type == "tool_call":
                calls.extend(chunk.tool_calls)
            elif chunk.usage:
                usage = usage.merge(chunk.usage)
        return LLMResponse(content="".join(content), tool_calls=calls, usage=usage, model=model)

    async def embed(self, texts: Sequence[str], model: str) -> list[list[float]]:
        raise NotImplementedError(f"{self.name} does not support embeddings")
