"""Teams/squads: how a large swarm stays organised instead of being a mob.

A team has a lead, a set of member roles and a shared objective. Members talk on
the team topic; leads also talk on the `leads` topic, which keeps cross-team
chatter O(teams) instead of O(agents^2).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TeamSpec:
    name: str
    objective: str
    lead_role: str = "planner"
    member_roles: list[str] = field(default_factory=lambda: ["general"])
    size: int = 4


@dataclass(slots=True)
class Team:
    name: str
    objective: str
    lead_id: str | None = None
    member_ids: list[str] = field(default_factory=list)
    topic: str = ""

    def __post_init__(self) -> None:
        self.topic = self.topic or f"team:{self.name}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "objective": self.objective,
            "lead": self.lead_id,
            "members": self.member_ids,
            "topic": self.topic,
            "size": len(self.member_ids),
        }


# Default squad layout used when the planner does not specify its own teams.
DEFAULT_TEAMS: list[TeamSpec] = [
    TeamSpec(
        name="research",
        objective="Gather, verify and summarise all information the swarm needs.",
        lead_role="researcher",
        member_roles=["researcher", "researcher", "reviewer"],
        size=4,
    ),
    TeamSpec(
        name="build",
        objective="Implement the solution: code, configs, infrastructure.",
        lead_role="coder",
        member_roles=["coder", "coder", "coder"],
        size=6,
    ),
    TeamSpec(
        name="verify",
        objective="Test, review and harden whatever the build team produces.",
        lead_role="reviewer",
        member_roles=["reviewer", "coder"],
        size=3,
    ),
    TeamSpec(
        name="ops",
        objective="Operate computers, browsers and devices; deploy and validate.",
        lead_role="operator",
        member_roles=["operator", "general"],
        size=3,
    ),
]
