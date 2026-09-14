"""Tool-calling serializer / parser for the built-in Gemini tunnel.

Ported from Bhati-Ai-Agent v1. The tunnel speaks plain text, so tools are
injected as a Hermes-style system prompt and tool calls are parsed back out of
the model's text (<tool_call>, <tool_use>, or fenced JSON).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def format_tools_system_prompt(tools: List[Any]) -> str:
    """Format tool schemas into a universal tool-calling instruction block."""
    if not tools:
        return ""

    tool_defs: List[Dict[str, Any]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        if "function" in t and isinstance(t["function"], dict):
            fn = t["function"]
            tool_defs.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                }
            )
        elif "name" in t:
            tool_defs.append(
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", t.get("parameters", {})),
                }
            )

    if not tool_defs:
        return ""

    json_tools = json.dumps(tool_defs, indent=2)
    return f"""# TOOL CALLING INSTRUCTIONS & AVAILABLE TOOLS
You have access to the following tools:
<tools>
{json_tools}
</tools>

HOW TO CALL TOOLS:
When you need to call one or more tools, you MUST respond strictly using the following XML format:
<tool_call>
{{"name": "tool_name", "arguments": {{"param1": "value1"}}}}
</tool_call>

RULES:
1. Only call tools listed in the <tools> section above.
2. Arguments must strictly follow each tool's JSON schema.
3. DECISION RULE (critical): read the user's LATEST message. If ANY listed tool can help, you MUST emit a <tool_call> block.
4. Brief reasoning text before the <tool_call> block is allowed, but the block must be present when a tool applies.
5. When you receive a [Tool Result ...] message, use its output: call another tool or give the final answer.
6. NEVER repeat the same tool call with the same arguments twice.
7. One <tool_call> block per call. The JSON inside must be valid.
"""


def extract_tool_calls_and_text(
    text: str, available_tools: Optional[List[Any]] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """Parse tool calls out of model text; return (clean_text, tool_calls)."""
    if not text:
        return "", []

    tool_calls: List[Dict[str, Any]] = []
    cleaned = text

    tool_names = set()
    for t in available_tools or []:
        if isinstance(t, dict):
            if "function" in t and isinstance(t["function"], dict) and "name" in t["function"]:
                tool_names.add(t["function"]["name"])
            elif "name" in t:
                tool_names.add(t["name"])

    def _append(name: str, args: Any, prefix: str = "call") -> None:
        tool_calls.append(
            {
                "id": f"{prefix}_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": args
                    if isinstance(args, str)
                    else json.dumps(args, separators=(",", ":")),
                },
            }
        )

    # 1. Hermes / standard XML: <tool_call>{...}</tool_call>
    for match in re.finditer(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>", text, re.DOTALL):
        cleaned = cleaned.replace(match.group(0), "").strip()
        try:
            parsed = json.loads(match.group(1).strip())
        except Exception:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("tool") or item.get("function")
            args = item.get("arguments") or item.get("parameters") or item.get("input") or {}
            if name:
                _append(str(name), args)

    # 2. Anthropic style: <tool_use><name>..</name><input>..</input></tool_use>
    pattern = r"<tool_use>\s*<name>(.*?)</name>\s*<input>([\s\S]*?)</input>\s*</tool_use>"
    for match in re.finditer(pattern, cleaned, re.DOTALL):
        cleaned = cleaned.replace(match.group(0), "").strip()
        try:
            args_str = json.dumps(json.loads(match.group(2).strip()), separators=(",", ":"))
        except Exception:
            args_str = json.dumps({"input": match.group(2).strip()})
        _append(match.group(1).strip(), args_str, prefix="toolu")

    # 3. Fenced JSON blocks that name a known tool
    for match in re.finditer(r"```(?:tool_call|json)?\s*(\{[\s\S]*?\})\s*```", cleaned, re.DOTALL):
        try:
            parsed = json.loads(match.group(1).strip())
        except Exception:
            continue
        name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
        if name and (not tool_names or name in tool_names):
            cleaned = cleaned.replace(match.group(0), "").strip()
            args = parsed.get("arguments") or parsed.get("parameters") or parsed.get("input") or {}
            _append(str(name), args)

    return cleaned.strip(), tool_calls


def serialize_openai_messages(
    messages: List[Any],
    tools: Optional[List[Any]] = None,
    system_prompt: Optional[str] = None,
) -> str:
    """Flatten an OpenAI-shaped message history into a single Gemini prompt."""
    parts: List[str] = []

    def _get(m: Any, key: str, default: Any = None) -> Any:
        if isinstance(m, dict):
            return m.get(key, default)
        return getattr(m, key, default)

    all_systems: List[str] = []
    if system_prompt:
        all_systems.append(system_prompt.strip())

    for m in messages:
        if _get(m, "role", "") == "system":
            content = _get(m, "content", "")
            if isinstance(content, str) and content:
                all_systems.append(content.strip())
            elif isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        all_systems.append(c.get("text", "").strip())

    tool_instructions = format_tools_system_prompt(tools or [])
    if tool_instructions:
        all_systems.append(tool_instructions)
    if all_systems:
        parts.append("# SYSTEM INSTRUCTIONS\n" + "\n\n".join(all_systems))

    for m in messages:
        role = _get(m, "role", "")
        content = _get(m, "content", "")
        tool_calls = _get(m, "tool_calls")
        tool_call_id = _get(m, "tool_call_id")
        name = _get(m, "name")

        if role == "system":
            continue

        if role == "user":
            if isinstance(content, str):
                user_text = content
            elif isinstance(content, list):
                pieces = []
                for item in content:
                    if isinstance(item, str):
                        pieces.append(item)
                    elif isinstance(item, dict):
                        if item.get("type") == "text":
                            pieces.append(item.get("text", ""))
                        elif item.get("type") == "image_url":
                            pieces.append("[Image attached]")
                user_text = "\n".join(pieces)
            else:
                user_text = ""
            parts.append(f"User: {user_text}")

        elif role == "assistant":
            if isinstance(content, str):
                asst_text = content
            elif isinstance(content, list):
                asst_text = "\n".join(
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            else:
                asst_text = ""

            call_blocks = []
            for tc in tool_calls or []:
                fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", {})
                fn_name = fn.get("name", "") if isinstance(fn, dict) else getattr(fn, "name", "")
                fn_args = (
                    fn.get("arguments", "{}") if isinstance(fn, dict) else getattr(fn, "arguments", "{}")
                )
                try:
                    args_obj = json.loads(fn_args) if isinstance(fn_args, str) else fn_args
                except Exception:
                    args_obj = {"raw": str(fn_args)}
                block = json.dumps({"name": fn_name, "arguments": args_obj}, indent=2)
                call_blocks.append(f"<tool_call>\n{block}\n</tool_call>")

            full_asst = (asst_text + "\n" + "\n".join(call_blocks)).strip()
            parts.append(f"Assistant: {full_asst}")

        elif role in ("tool", "function"):
            tool_label = name or tool_call_id or "tool"
            tool_out = content if isinstance(content, str) else json.dumps(content)
            parts.append(f"[Tool Result for {tool_label}]:\n{tool_out}")

    return "\n\n".join(parts)
