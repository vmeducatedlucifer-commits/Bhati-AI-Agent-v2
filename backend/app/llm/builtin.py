"""Built-in keyless LLM provider (Gemini web tunnel).

This is the v2 port of the v1 `gateway` model. Differences from v1:
- no separate loopback HTTP server and no shared secret; the tunnel is called
  in-process, so it works on Render free tier (one port, one worker)
- tool calling is bridged to v2's `ToolCall` / `StreamChunk` contract

Models served:
- `gemini-2.0-flash` (General)
- `gemini-1.5-pro`   (Pro)

It needs **no API key**. If `GEMINI_API_KEY` is present the tunnel uses the
official REST API first and falls back to the keyless tunnel automatically.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from app.core.logging import get_logger
from app.gateway.config import BUILTIN_GENERAL_MODEL, BUILTIN_MODELS
from app.gateway.tools import extract_tool_calls_and_text, serialize_openai_messages
from app.gateway.tunnel import GeminiTunnel, resolve_model
from app.llm.base import LLMProvider, Message, StreamChunk, ToolCall, Usage

log = get_logger("llm.builtin")

_TOOL_MARKERS = ("<tool_call", "<tool_use")


def _first_marker(text: str) -> int:
    """Index of the first tool-call marker, or -1 when the text is clean."""
    positions = [text.find(m) for m in _TOOL_MARKERS]
    found = [p for p in positions if p != -1]
    return min(found) if found else -1


class BuiltinProvider(LLMProvider):
    """Zero-config provider. Always available, used as the final fallback."""

    name = "builtin"
    supports_tools = True

    def __init__(self) -> None:
        self._tunnel = GeminiTunnel()

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _message_dict(message: Message) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": getattr(message.role, "value", message.role),
            "content": message.content or "",
        }
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.name:
            payload["name"] = message.name
        return payload

    def _serialize(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None,
        system: str | None,
    ) -> str:
        return serialize_openai_messages(
            [self._message_dict(m) for m in messages],
            tools=list(tools) if tools else None,
            system_prompt=system,
        )

    @staticmethod
    def _normalize(model: str | None) -> str:
        if model and model in BUILTIN_MODELS:
            return model
        return resolve_model(model or BUILTIN_GENERAL_MODEL)

    @staticmethod
    def _to_tool_calls(raw: list[dict[str, Any]]) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for item in raw:
            fn = item.get("function", {})
            calls.append(
                ToolCall(
                    id=item.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=ToolCall.parse_arguments(fn.get("arguments", "{}")),
                )
            )
        return calls

    # ---------------------------------------------------------------- stream
    async def stream(
        self,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        prompt = self._serialize(messages, tools, system)
        model_name = self._normalize(model)

        accumulated = ""
        streamed = ""
        sent = 0

        async for delta in self._tunnel.stream_tokens(
            prompt=prompt,
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            accumulated += delta
            # Hold back everything from the first tool-call marker onwards so
            # raw XML never leaks into the user-visible narration.
            marker = _first_marker(accumulated)
            safe_end = marker if marker != -1 else len(accumulated)
            if safe_end > sent:
                piece = accumulated[sent:safe_end]
                sent = safe_end
                streamed += piece
                yield StreamChunk(type="text", text=piece)

        if not accumulated:
            # Streaming produced nothing (session rotation exhausted) -> retry
            # once via the non-streaming path before giving up.
            log.warning("builtin_stream_empty_retrying_complete", model=model_name)
            accumulated = await self._tunnel.complete(
                prompt=prompt,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        text, raw_calls = extract_tool_calls_and_text(
            accumulated, available_tools=list(tools) if tools else None
        )

        if raw_calls:
            yield StreamChunk(type="tool_call", tool_calls=self._to_tool_calls(raw_calls))
        else:
            remainder = ""
            if not streamed:
                remainder = text
            elif text.startswith(streamed):
                remainder = text[len(streamed) :]
            if remainder:
                yield StreamChunk(type="text", text=remainder)

        yield StreamChunk(
            type="usage",
            usage=Usage(
                prompt_tokens=max(1, len(prompt) // 4),
                completion_tokens=max(1, len(accumulated) // 4),
            ),
        )
        yield StreamChunk(type="done")

    async def aclose(self) -> None:
        await self._tunnel.aclose()
