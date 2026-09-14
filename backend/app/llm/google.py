"""Google Gemini provider (generateContent streaming + function calling)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.core.errors import ProviderError
from app.llm.base import LLMProvider, Message, StreamChunk, ToolCall, Usage

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GoogleProvider(LLMProvider):
    name = "google"

    def __init__(self, api_key: str, timeout: float = 300.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    @staticmethod
    def _to_wire(messages: Sequence[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                if msg.content:
                    system_parts.append(msg.content)
                continue
            if msg.role == "tool":
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": msg.name or "tool",
                                    "response": {"result": msg.content},
                                }
                            }
                        ],
                    }
                )
                continue
            parts: list[dict[str, Any]] = []
            if msg.content:
                parts.append({"text": msg.content})
            for call in msg.tool_calls:
                parts.append({"functionCall": {"name": call.name, "args": call.arguments}})
            contents.append(
                {"role": "model" if msg.role == "assistant" else "user", "parts": parts or [{"text": ""}]}
            )
        return ("\n\n".join(system_parts) or None), contents

    async def stream(
        self,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        inline_system, contents = self._to_wire(messages)
        merged_system = "\n\n".join(part for part in (system, inline_system) if part)
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if merged_system:
            payload["systemInstruction"] = {"parts": [{"text": merged_system}]}
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                        }
                        for tool in tools
                    ]
                }
            ]

        url = f"{BASE_URL}/models/{model}:streamGenerateContent?alt=sse&key={self.api_key}"
        calls: list[ToolCall] = []
        usage = Usage()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")
                    raise ProviderError(f"google error {response.status_code}: {body[:500]}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    meta = event.get("usageMetadata") or {}
                    if meta:
                        usage = Usage(
                            prompt_tokens=meta.get("promptTokenCount", usage.prompt_tokens),
                            completion_tokens=meta.get("candidatesTokenCount", usage.completion_tokens),
                        )
                    for candidate in event.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            if "text" in part and part["text"]:
                                yield StreamChunk(type="text", text=part["text"])
                            if "functionCall" in part:
                                fn = part["functionCall"]
                                calls.append(
                                    ToolCall(
                                        id=f"call_{len(calls)}",
                                        name=fn.get("name", ""),
                                        arguments=fn.get("args") or {},
                                    )
                                )

        if calls:
            yield StreamChunk(type="tool_call", tool_calls=calls)
        yield StreamChunk(type="usage", usage=usage)
        yield StreamChunk(type="done", usage=usage)

    async def embed(self, texts: Sequence[str], model: str) -> list[list[float]]:
        url = f"{BASE_URL}/models/{model}:batchEmbedContents?key={self.api_key}"
        requests = [
            {"model": f"models/{model}", "content": {"parts": [{"text": text}]}} for text in texts
        ]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json={"requests": requests})
            if response.status_code >= 400:
                raise ProviderError(f"google embeddings error: {response.text[:300]}")
            payload = response.json()
        return [item.get("values", []) for item in payload.get("embeddings", [])]
