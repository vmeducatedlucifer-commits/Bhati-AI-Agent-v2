"""The ReAct agent loop: think → call tools → observe → repeat, fully streamed."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.context import trim_history
from app.agents.profiles import AgentProfile, get_profile
from app.agents.prompts import build_system_prompt
from app.core.config import settings
from app.core.events import EventType, event_bus
from app.core.logging import get_logger
from app.llm.base import Message, ToolCall, Usage
from app.llm.router import get_router
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import get_registry
from app.workspace.manager import get_workspace_manager

log = get_logger("agent.loop")


@dataclass(slots=True)
class AgentRunResult:
    output: str
    steps: int
    usage: Usage
    messages: list[Message] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    stopped_reason: str = "completed"
    workspace: str = ""
    home: str = ""


class AgentLoop:
    """One autonomous worker. Owns its tool scope, workspace, budget and events.

    Workspace model: the tool sandbox is the *session* folder, so swarm agents
    can read each other's output, while `self.home` (`agents/<agent_id>/`) is
    this agent's private folder. Deliverables go to `downloads/`, shared notes
    to `shared/` - all of it browsable and downloadable from the UI.
    """

    def __init__(
        self,
        session_id: str,
        agent_id: str = "main",
        profile: AgentProfile | str = "general",
        model: str | None = None,
        extra_context: str = "",
        history: list[Message] | None = None,
    ) -> None:
        self.session_id = session_id
        self.agent_id = agent_id
        self.profile = profile if isinstance(profile, AgentProfile) else get_profile(profile)
        self.model = model or self.profile.model
        self.messages: list[Message] = history or []
        self.usage = Usage()

        workspaces = get_workspace_manager()
        session_root = workspaces.session_dir(session_id)
        workspaces.agent_dir(session_id, agent_id)  # ensure the private home exists
        self.home = workspaces.relative_home(agent_id)
        briefing = workspaces.briefing(session_id, agent_id)
        self.extra_context = f"{extra_context}\n\n{briefing}".strip() if extra_context else briefing

        self.ctx = ToolContext(
            session_id=session_id,
            agent_id=agent_id,
            workspace=session_root,
            metadata={"home": self.home},
        )
        self._cancelled = False

    # ----------------------------------------------------------------- tools
    def _tools(self) -> list:
        registry = get_registry()
        return registry.select(tags=self.profile.tags or None, max_permission=self.profile.max_permission)

    def _system_prompt(self, tools: list) -> str:
        return build_system_prompt(
            self.profile.role_prompt,
            tool_names=[tool.name for tool in tools],
            workspace=f"{self.ctx.workspace} (your folder: {self.home})",
            extra_context=self.extra_context,
        )

    def cancel(self) -> None:
        self._cancelled = True

    # ------------------------------------------------------------------- run
    async def run(self, goal: str, stream_text: bool = True) -> AgentRunResult:
        tools = self._tools()
        schemas = [tool.schema() for tool in tools]
        system = self._system_prompt(tools)
        self.messages.append(Message(role="user", content=goal))

        await event_bus.emit(
            EventType.AGENT_START,
            self.session_id,
            {
                "profile": self.profile.name,
                "goal": goal[:400],
                "tools": len(tools),
                "workspace": str(self.ctx.workspace),
                "home": self.home,
            },
            agent_id=self.agent_id,
        )

        router = get_router()
        collected: list[dict[str, Any]] = []
        final_text = ""
        step = 0
        reason = "completed"
        started = time.perf_counter()

        while step < self.profile.steps():
            if self._cancelled:
                reason = "cancelled"
                break
            step += 1
            self.messages = trim_history(self.messages)
            text_parts: list[str] = []
            calls: list[ToolCall] = []

            try:
                async for chunk in router.stream(
                    self.messages,
                    model=self.model,
                    tools=schemas or None,
                    temperature=self.profile.temperature,
                    system=system,
                    max_tokens=8192,
                ):
                    if chunk.type == "text":
                        text_parts.append(chunk.text)
                        if stream_text:
                            await event_bus.emit(
                                EventType.MESSAGE_DELTA,
                                self.session_id,
                                {"text": chunk.text},
                                agent_id=self.agent_id,
                            )
                    elif chunk.type == "thinking":
                        await event_bus.emit(
                            EventType.THINKING, self.session_id, {"text": chunk.text}, agent_id=self.agent_id
                        )
                    elif chunk.type == "tool_call":
                        calls.extend(chunk.tool_calls)
                    elif chunk.usage:
                        self.usage = self.usage.merge(chunk.usage)
            except Exception as exc:
                log.error("llm_stream_failed", error=str(exc), agent=self.agent_id)
                await event_bus.emit(
                    EventType.ERROR, self.session_id, {"error": str(exc)}, agent_id=self.agent_id
                )
                final_text = f"Model call failed: {exc}"
                reason = "error"
                break

            assistant_text = "".join(text_parts)
            self.messages.append(Message(role="assistant", content=assistant_text, tool_calls=calls))

            if not calls:
                final_text = assistant_text
                break

            results = await asyncio.gather(
                *(self._execute(call) for call in calls), return_exceptions=False
            )
            for call, result in zip(calls, results, strict=False):
                collected.append(
                    {
                        "name": call.name,
                        "arguments": call.arguments,
                        "ok": result.ok,
                        "duration_ms": result.duration_ms,
                    }
                )
                self.messages.append(
                    Message(
                        role="tool",
                        content=result.to_model_text(),
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )
        else:
            reason = "max_steps"

        await event_bus.emit(
            EventType.AGENT_END,
            self.session_id,
            {
                "steps": step,
                "reason": reason,
                "tokens": self.usage.total_tokens,
                "seconds": round(time.perf_counter() - started, 2),
                "home": self.home,
            },
            agent_id=self.agent_id,
        )
        return AgentRunResult(
            output=final_text,
            steps=step,
            usage=self.usage,
            messages=self.messages,
            tool_calls=collected,
            stopped_reason=reason,
            workspace=str(self.ctx.workspace),
            home=self.home,
        )

    async def _execute(self, call: ToolCall) -> ToolResult:
        tool = get_registry().get(call.name)
        await event_bus.emit(
            EventType.TOOL_CALL,
            self.session_id,
            {"name": call.name, "arguments": call.arguments},
            agent_id=self.agent_id,
        )
        if tool is None:
            result = ToolResult.failure(f"Unknown tool '{call.name}'")
        else:
            try:
                result = await asyncio.wait_for(
                    tool.run(self.ctx, call.arguments), timeout=settings.step_timeout_seconds
                )
            except TimeoutError:
                result = ToolResult.failure(f"Tool '{call.name}' timed out")
        await event_bus.emit(
            EventType.TOOL_RESULT,
            self.session_id,
            {
                "name": call.name,
                "ok": result.ok,
                "duration_ms": result.duration_ms,
                "preview": result.to_model_text(1200),
            },
            agent_id=self.agent_id,
        )
        return result
