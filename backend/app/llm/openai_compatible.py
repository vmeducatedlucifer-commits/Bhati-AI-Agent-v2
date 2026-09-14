"""Provider for every OpenAI-compatible API: OpenAI, Groq, DeepSeek, Mistral,
OpenRouter, Together, Ollama, vLLM, LM Studio."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.core.errors import ProviderError
from app.llm.base import LLMProvider, Message, StreamChunk, ToolCall, Usage


def _to_wire(messages: Sequence[Message]) -> list[dict[str, Any]]:
    wire: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "tool":
            wire.append(
                {"role": "tool", "tool_call_id": msg.tool_call_id or "", "content": msg.content}
            )
            continue
        item: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            item["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in msg.tool_calls
            ]
        wire.append(item)
    return wire


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        api_key: str | None,
        base_url: str,
        extra_headers: dict[str, str] | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.extra_headers = extra_headers or {}
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def stream(
        self,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": _to_wire(
                [Message(role="system", content=system), *messages] if system else messages
            ),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": tool} for tool in tools]
            payload["tool_choice"] = "auto"

        partial: dict[int, dict[str, Any]] = {}
        usage = Usage()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=payload
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")
                    raise ProviderError(f"{self.name} error {response.status_code}: {body[:500]}")
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if event.get("usage"):
                        usage = Usage(
                            prompt_tokens=event["usage"].get("prompt_tokens", 0),
                            completion_tokens=event["usage"].get("completion_tokens", 0),
                        )
                    for choice in event.get("choices", []):
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            yield StreamChunk(type="text", text=delta["content"])
                        if delta.get("reasoning_content"):
                            yield StreamChunk(type="thinking", text=delta["reasoning_content"])
                        for call in delta.get("tool_calls") or []:
                            index = call.get("index", 0)
                            slot = partial.setdefault(index, {"id": "", "name": "", "args": ""})
                            if call.get("id"):
                                slot["id"] = call["id"]
                            fn = call.get("function") or {}
                            if fn.get("name"):
                                slot["name"] = fn["name"]
                            if fn.get("arguments"):
                                slot["args"] += fn["arguments"]

        if partial:
            yield StreamChunk(
                type="tool_call",
                tool_calls=[
                    ToolCall(
                        id=slot["id"] or f"call_{index}",
                        name=slot["name"],
                        arguments=ToolCall.parse_arguments(slot["args"]),
                    )
                    for index, slot in sorted(partial.items())
                    if slot["name"]
                ],
            )
        yield StreamChunk(type="usage", usage=usage)
        yield StreamChunk(type="done", usage=usage)

    async def embed(self, texts: Sequence[str], model: str) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers(),
                json={"model": model, "input": list(texts)},
            )
            if response.status_code >= 400:
                raise ProviderError(f"{self.name} embeddings error: {response.text[:300]}")
            payload = response.json()
        return [item["embedding"] for item in payload.get("data", [])]
