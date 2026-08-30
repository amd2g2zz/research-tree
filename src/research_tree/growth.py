"""Growth-aware alignment: readiness is delta-driven and budgets are per-branch.

Unresolved nodes are not a readiness violation. A vague objective legitimately
grows more nodes, revisions, supersessions, and roots as the researcher learns;
readiness advances when a genuine delta lands, and a branch can hand off without
forcing its siblings closed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from .domain import validate_identifier

BRANCH_STATUSES = ("active", "stalled", "handed_off", "blocked", "complete")
BRANCH_OUTCOMES = ("resolved", "continue", "branch", "blocked")
DELTA_KINDS = (
    "evidence",
    "model",
    "decision",
    "phase",
    "blocker",
    "authority",
    "next_action",
)
BRANCH_TURN_LIMITS = {
    "active": 50,
    "stalled": 10,
    "blocked": 5,
    "handed_off": 0,
    "complete": 0,
}
OUTCOME_STATUS = {
    "resolved": "complete",
    "continue": "active",
    "branch": "active",
    "blocked": "blocked",
}


class GrowthError(ValueError):
    """Raised when growth-aware branch state or handoff input is invalid."""


def _member(value: Any, allowed: Sequence[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise GrowthError(f"{label} must be one of {', '.join(allowed)}")
    return value


def _count(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise GrowthError(f"{label} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class BranchState:
    branch_id: str
    status: str
    node_count: int
    revision: int
    last_delta_at: str
    per_branch_turn_count: int

    @classmethod
    def create(
        cls,
        *,
        branch_id: str,
        status: str = "active",
        node_count: int = 0,
        revision: int = 1,
        last_delta_at: str,
        per_branch_turn_count: int = 0,
    ) -> "BranchState":
        return cls(
            branch_id=validate_identifier(branch_id, "branch_id"),
            status=_member(status, BRANCH_STATUSES, "status"),
            node_count=_count(node_count, "node_count"),
            revision=_count(revision, "revision"),
            last_delta_at=str(last_delta_at),
            per_branch_turn_count=_count(per_branch_turn_count, "per_branch_turn_count"),
        )

    def with_growth(self, *, node_count: int, last_delta_at: str) -> "BranchState":
        """Return a grown copy — growth is a normal signal, never a violation."""

        return replace(
            self,
            node_count=_count(node_count, "node_count"),
            revision=self.revision + 1,
            last_delta_at=str(last_delta_at),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "status": self.status,
            "node_count": self.node_count,
            "revision": self.revision,
            "last_delta_at": self.last_delta_at,
            "per_branch_turn_count": self.per_branch_turn_count,
        }


@dataclass(frozen=True, slots=True)
class BranchHandoff:
    branch_id: str
    outcome: str
    lineage_refs: tuple[str, ...]
    delta_summary: str

    @classmethod
    def create(
        cls,
        *,
        branch_id: str,
        outcome: str,
        lineage_refs: Sequence[str] = (),
        delta_summary: str = "",
    ) -> "BranchHandoff":
        return cls(
            branch_id=validate_identifier(branch_id, "branch_id"),
            outcome=_member(outcome, BRANCH_OUTCOMES, "outcome"),
            lineage_refs=tuple(str(item) for item in lineage_refs),
            delta_summary=str(delta_summary),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "outcome": self.outcome,
            "lineage_refs": list(self.lineage_refs),
            "delta_summary": self.delta_summary,
        }


@dataclass(frozen=True, slots=True)
class ReadinessDelta:
    delta_count: int
    kinds: tuple[str, ...]
    branch_deltas: Mapping[str, tuple[str, ...]]
    violations: tuple[str, ...]

    @property
    def is_progress(self) -> bool:
        return self.delta_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "delta_count": self.delta_count,
            "kinds": list(self.kinds),
            "branch_deltas": {key: list(value) for key, value in self.branch_deltas.items()},
            "violations": list(self.violations),
            "is_progress": self.is_progress,
        }


def _structural_deltas(before: BranchState | None, after: BranchState) -> tuple[str, ...]:
    if before is None:
        return ("model",)
    kinds: list[str] = []
    if after.node_count != before.node_count or after.revision != before.revision:
        kinds.append("model")
    if after.status != before.status:
        kinds.append("blocker" if after.status == "blocked" else "phase")
    return tuple(kinds)


def compute_readiness_delta(
    branches_before: Sequence[BranchState],
    branches_after: Sequence[BranchState],
    evidence_deltas: Mapping[str, Sequence[str]],
) -> ReadinessDelta:
    """Count genuine deltas across a growth step.

    Replaces the "unresolved nodes == readiness violation" rule: more nodes,
    revisions, or new roots are progress, and only declared delta kinds count.
    """

    prior = {item.branch_id: item for item in branches_before}
    branch_deltas: dict[str, tuple[str, ...]] = {}
    kinds: list[str] = []
    for item in branches_after:
        declared = tuple(_member(kind, DELTA_KINDS, "delta kind") for kind in evidence_deltas.get(item.branch_id, ()))
        found = _structural_deltas(prior.get(item.branch_id), item) + declared
        if found:
            branch_deltas[item.branch_id] = found
            kinds.extend(found)
    ordered = tuple(sorted(set(kinds), key=DELTA_KINDS.index))
    return ReadinessDelta(
        delta_count=len(kinds),
        kinds=ordered,
        branch_deltas=branch_deltas,
        violations=(),
    )


def per_branch_turn_limit(branch: BranchState) -> int:
    """Per-branch turn budget — siblings never consume each other's budget."""

    return BRANCH_TURN_LIMITS[branch.status]


def branch_turn_limit_exceeded(branch: BranchState) -> bool:
    return branch.per_branch_turn_count >= per_branch_turn_limit(branch)


def seal_branch(branches: Sequence[BranchState], handoff: BranchHandoff) -> tuple[BranchState, ...]:
    """Seal exactly the handed-off branch; siblings keep their own status."""

    if not any(item.branch_id == handoff.branch_id for item in branches):
        raise GrowthError(f"unknown branch: {handoff.branch_id}")
    status = "handed_off" if handoff.outcome == "resolved" else OUTCOME_STATUS[handoff.outcome]
    return tuple(replace(item, status=status) if item.branch_id == handoff.branch_id else item for item in branches)


__all__ = [
    "BRANCH_OUTCOMES",
    "BRANCH_STATUSES",
    "BRANCH_TURN_LIMITS",
    "DELTA_KINDS",
    "BranchHandoff",
    "BranchState",
    "GrowthError",
    "ReadinessDelta",
    "branch_turn_limit_exceeded",
    "compute_readiness_delta",
    "per_branch_turn_limit",
    "seal_branch",
]
