"""Built-in keyless model tests (no network required)."""

from __future__ import annotations

from app.gateway.config import BUILTIN_GENERAL_MODEL, BUILTIN_MODELS, BUILTIN_PRO_MODEL
from app.gateway.tools import extract_tool_calls_and_text, serialize_openai_messages
from app.gateway.tunnel import resolve_model
from app.llm.builtin import BuiltinProvider
from app.llm.router import ModelRouter


def test_builtin_models_declared() -> None:
    assert BUILTIN_MODELS == (BUILTIN_GENERAL_MODEL, BUILTIN_PRO_MODEL)
    assert BUILTIN_GENERAL_MODEL == "gemini-2.0-flash"
    assert BUILTIN_PRO_MODEL == "gemini-1.5-pro"


def test_router_registers_builtin() -> None:
    router = ModelRouter()
    assert "builtin" in router.providers
    ids = {m["id"] for m in router.available_models()}
    assert f"builtin/{BUILTIN_GENERAL_MODEL}" in ids
    assert f"builtin/{BUILTIN_PRO_MODEL}" in ids


def test_router_resolves_builtin_specs() -> None:
    router = ModelRouter()
    provider, model = router.resolve("builtin/gemini-1.5-pro")
    assert provider.name == "builtin"
    assert model == "gemini-1.5-pro"

    provider, model = router.resolve("builtin")
    assert provider.name == "builtin"
    assert model == BUILTIN_GENERAL_MODEL


def test_unknown_provider_falls_back_instead_of_raising() -> None:
    router = ModelRouter()
    provider, _ = router.resolve("nope-provider/some-model")
    assert provider is not None


def test_model_name_normalization() -> None:
    assert resolve_model("claude-sonnet-4") == "gemini-2.0-flash"
    assert resolve_model("builtin/gemini-1.5-pro") == "gemini-1.5-pro"
    assert resolve_model("pro") == "gemini-1.5-pro"
    assert resolve_model("flash") == "gemini-2.0-flash"


def test_tool_prompt_and_parsing_roundtrip() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
        }
    ]
    prompt = serialize_openai_messages(
        [{"role": "user", "content": "read app.py"}], tools=tools, system_prompt="You are Bhati."
    )
    assert "read_file" in prompt
    assert "User: read app.py" in prompt

    text, calls = extract_tool_calls_and_text(
        'Sure.\n<tool_call>\n{"name": "read_file", "arguments": {"path": "app.py"}}\n</tool_call>',
        available_tools=tools,
    )
    assert text == "Sure."
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "read_file"


def test_builtin_provider_serializes_messages() -> None:
    provider = BuiltinProvider()
    assert provider.name == "builtin"
    assert provider.supports_tools is True
