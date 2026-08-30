"""Issue #330: Human Brief adds organizational operating-model projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    role: str
    owner: str
    capacity: float
    unit: str

    def to_dict(self) -> dict[str, object]:
        return {"role": self.role, "owner": self.owner, "capacity": self.capacity, "unit": self.unit}


@dataclass(frozen=True, slots=True)
class SLATier:
    tier: str
    target_response: str
    escalation_after: str

    def to_dict(self) -> dict[str, object]:
        return {
            "tier": self.tier,
            "target_response": self.target_response,
            "escalation_after": self.escalation_after,
        }


@dataclass(frozen=True, slots=True)
class OperatingModelProjection:
    """Per #330: roles, SLA, escalation, concurrent-project limits, meeting
    replacement, and adoption metrics.
    """

    roles: tuple[RoleAssignment, ...] = ()
    sla: SLATier = field(default_factory=lambda: SLATier("none", "n/a", "n/a"))
    concurrent_project_limit: int = 0
    meeting_replacement_per_week: float = 0.0
    adoption_metrics: Mapping[str, float] = field(
        default_factory=lambda: {"weekly_run_count": 0, "median_satisfaction": 0.0, "knowledge_reuse_pct": 0.0}
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "roles": [role.to_dict() for role in self.roles],
            "sla": self.sla.to_dict(),
            "concurrent_project_limit": self.concurrent_project_limit,
            "meeting_replacement_per_week": self.meeting_replacement_per_week,
            "adoption_metrics": dict(self.adoption_metrics),
        }


def build_operating_model(
    *,
    roles: Sequence[RoleAssignment] = (),
    sla: SLATier = SLATier("none", "n/a", "n/a"),
    concurrent_project_limit: int = 0,
    meeting_replacement_per_week: float = 0.0,
) -> OperatingModelProjection:
    """Construct the projection. Adoption metrics start at zero (not fabricated)."""

    return OperatingModelProjection(
        roles=tuple(roles),
        sla=sla,
        concurrent_project_limit=concurrent_project_limit,
        meeting_replacement_per_week=meeting_replacement_per_week,
    )
