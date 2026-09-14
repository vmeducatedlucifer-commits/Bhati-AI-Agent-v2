"""Anthropic Messages API provider with streaming + tool use."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.core.errors import ProviderError
from app.llm.base import LLMProvider, Message, StreamChunk, ToolCall, Usage

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


def _to_wire(messages: Sequence[Message]) -> tuple[str | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    wire: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "system":
            if msg.content:
                system_parts.append(msg.content)
            continue
        if msg.role == "tool":
            wire.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id or "",
                            "content": msg.content or "",
                        }
                    ],
                }
            )
            continue
        blocks: list[dict[str, Any]] = []
        if msg.content:
            blocks.append({"type": "text", "text": msg.content})
        for call in msg.tool_calls:
            blocks.append(
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
            )
        wire.append({"role": msg.role, "content": blocks or [{"type": "text", "text": ""}]})
    return ("\n\n".join(system_parts) or None), wire


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, timeout: float = 300.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    async def stream(
        self,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        inline_system, wire = _to_wire(messages)
        merged_system = "\n\n".join(part for part in (system, inline_system) if part) or None
        payload: dict[str, Any] = {
            "model": model,
            "messages": wire,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if merged_system:
            payload["system"] = merged_system
        if tools:
            payload["tools"] = [
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters", {"type": "object", "properties": {}}),
                }
                for tool in tools
            ]

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        blocks: dict[int, dict[str, Any]] = {}
        usage = Usage()
        calls: list[ToolCall] = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", API_URL, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")
                    raise ProviderError(f"anthropic error {response.status_code}: {body[:500]}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type")
                    if etype == "content_block_start":
                        block = event.get("content_block", {})
                        blocks[event.get("index", 0)] = {
                            "type": block.get("type"),
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "json": "",
                        }
                    elif etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield StreamChunk(type="text", text=delta.get("text", ""))
                        elif delta.get("type") == "thinking_delta":
                            yield StreamChunk(type="thinking", text=delta.get("thinking", ""))
                        elif delta.get("type") == "input_json_delta":
                            slot = blocks.setdefault(
                                event.get("index", 0), {"type": "tool_use", "id": "", "name": "", "json": ""}
                            )
                            slot["json"] += delta.get("partial_json", "")
                    elif etype == "content_block_stop":
                        slot = blocks.get(event.get("index", 0))
                        if slot and slot.get("type") == "tool_use" and slot.get("name"):
                            calls.append(
                                ToolCall(
                                    id=slot["id"] or f"call_{len(calls)}",
                                    name=slot["name"],
                                    arguments=ToolCall.parse_arguments(slot["json"]),
                                )
                            )
                    elif etype in {"message_start", "message_delta"}:
                        raw = event.get("usage") or event.get("message", {}).get("usage") or {}
                        usage = Usage(
                            prompt_tokens=raw.get("input_tokens", usage.prompt_tokens),
                            completion_tokens=raw.get("output_tokens", usage.completion_tokens),
                        )

        if calls:
            yield StreamChunk(type="tool_call", tool_calls=calls)
        yield StreamChunk(type="usage", usage=usage)
        yield StreamChunk(type="done", usage=usage)
