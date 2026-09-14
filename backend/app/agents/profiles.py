"""Agent profiles — each specialist gets its own prompt, tools and limits."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings
from app.tools.base import Permission


@dataclass(slots=True)
class AgentProfile:
    name: str
    title: str
    role_prompt: str
    tags: list[str] = field(default_factory=list)
    max_permission: Permission = Permission.DANGEROUS
    model: str | None = None
    max_steps: int = 0
    temperature: float = 0.3

    def steps(self) -> int:
        return self.max_steps or settings.max_steps


PROFILES: dict[str, AgentProfile] = {
    "general": AgentProfile(
        name="general",
        title="General Agent",
        role_prompt=(
            "You handle any task end-to-end: research, writing, automation, analysis and code. "
            "Choose the shortest reliable path to a verified result."
        ),
        tags=[],
        temperature=0.4,
    ),
    "coder": AgentProfile(
        name="coder",
        title="Autonomous Coder",
        role_prompt=(
            "You are a senior software engineer. You explore the repository, implement changes, "
            "run tests and iterate until the build is green. You leave the codebase cleaner than you found it."
        ),
        tags=["files", "coding", "shell", "git", "code", "memory"],
        temperature=0.2,
    ),
    "researcher": AgentProfile(
        name="researcher",
        title="Deep Researcher",
        role_prompt=(
            "You gather and verify information from the web and the workspace. "
            "You cite sources, cross-check claims and produce structured findings."
        ),
        tags=["web", "research", "files", "memory"],
        max_permission=Permission.WRITE,
        temperature=0.3,
    ),
    "operator": AgentProfile(
        name="operator",
        title="Computer Operator",
        role_prompt=(
            "You operate computers: browsers, desktop apps and Android devices. "
            "You observe state before acting, act in small steps and confirm each result."
        ),
        tags=["browser", "computer", "device", "android", "desktop", "shell"],
        max_permission=Permission.SYSTEM,
        temperature=0.2,
    ),
    "reviewer": AgentProfile(
        name="reviewer",
        title="Reviewer",
        role_prompt=(
            "You verify other agents' work against acceptance criteria: correctness, tests, "
            "security and completeness. You are concise and uncompromising."
        ),
        tags=["files", "coding", "shell", "git"],
        max_permission=Permission.WRITE,
        temperature=0.1,
    ),
    "planner": AgentProfile(
        name="planner",
        title="Planner",
        role_prompt="You decompose goals into executable task graphs. You never execute tasks yourself.",
        tags=["memory"],
        max_permission=Permission.SAFE,
        max_steps=3,
        temperature=0.2,
    ),
}


def get_profile(name: str | None) -> AgentProfile:
    return PROFILES.get((name or "general").lower(), PROFILES["general"])
