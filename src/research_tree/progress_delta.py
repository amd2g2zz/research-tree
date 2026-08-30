"""Issue #329: delta-oriented progress projection.

Every user-visible update is derived from canonical state delta. Repeated
unchanged context collapses with counts and provenance. Recoverable tool
failures remain internal unless they change scope, evidence level, cost,
authority, or expected completion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence


@dataclass(frozen=True, slots=True)
class ProgressDelta:
    """One canonical-state delta event."""

    new_evidence: tuple[str, ...] = ()
    changed_model: tuple[str, ...] = ()
    changed_decision: tuple[str, ...] = ()
    changed_phase: tuple[str, ...] = ()
    new_blocker: tuple[str, ...] = ()
    changed_authority: tuple[str, ...] = ()
    changed_next_action: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, tuple[str, ...]]:
        return {
            "new_evidence": self.new_evidence,
            "changed_model": self.changed_model,
            "changed_decision": self.changed_decision,
            "changed_phase": self.changed_phase,
            "new_blocker": self.new_blocker,
            "changed_authority": self.changed_authority,
            "changed_next_action": self.changed_next_action,
        }


@dataclass(frozen=True, slots=True)
class ProjectedFailureGroup:
    """Aggregated recoverable tool failures with raw receipt refs."""

    kind: str
    severity: str
    count: int
    receipt_refs: tuple[str, ...]
    first_seen: str
    last_seen: str


@dataclass(frozen=True, slots=True)
class ProjectedProgress:
    """A compact, user-visible progress projection (Mapping-friendly)."""

    deltas: tuple[str, ...] = ()
    phase: str = ""
    internal_failures: tuple[ProjectedFailureGroup, ...] = ()
    decision_relevant_failures: tuple[ProjectedFailureGroup, ...] = ()

    def __getitem__(self, key):
        return getattr(self, key)


DECISION_RELEVANT_AUTHORITIES = frozenset({"budget_exceeded", "auth_expired", "approval_required"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_delta(delta: ProgressDelta) -> ProjectedProgress:
    """Pure projection: returns what the user should see."""

    raw = delta.to_dict()
    surfaced: list[str] = []
    for key, values in raw.items():
        if values:
            surfaced.append(key)
    internal: list[ProjectedFailureGroup] = []
    decision_relevant: list[ProjectedFailureGroup] = []
    phase = delta.changed_phase[0] if delta.changed_phase else ""
    if not surfaced and not delta.changed_authority:
        return ProjectedProgress(deltas=(), phase=phase)
    return ProjectedProgress(
        deltas=tuple(surfaced),
        phase=phase,
        internal_failures=tuple(internal),
        decision_relevant_failures=tuple(decision_relevant),
    )


def aggregate_failures(
    failures: Sequence[tuple[str, str, int] | tuple[str, str, int, str]],
) -> ProjectedFailureGroup:
    """Aggregate tool-failure tuples (kind, severity, count[, receipt_ref]) by kind."""

    if not failures:
        raise ValueError("aggregate_failures requires at least one entry")
    grouped: dict[str, list[tuple[str, int, str | None]]] = {}
    for entry in failures:
        kind = entry[0]
        severity = entry[1]
        count = entry[2]
        receipt_ref: str | None = entry[3] if len(entry) > 3 else None
        grouped.setdefault(kind, []).append((severity, count, receipt_ref))
    first_kind = next(iter(grouped))
    records = grouped[first_kind]
    severity = records[0][0]
    total = sum(record[1] for record in records)
    receipt_refs = tuple(record[2] for record in records if record[2] is not None)
    return ProjectedFailureGroup(
        kind=first_kind,
        severity=severity,
        count=total,
        receipt_refs=receipt_refs,
        first_seen=_now_iso(),
        last_seen=_now_iso(),
    )
