"""Issue #329: delta-oriented progress projection.
Issue #387: multi-kind aggregation + decision-relevant promotion.

Every user-visible update is derived from canonical state delta. Repeated
unchanged context collapses with counts and provenance. Recoverable tool
failures remain internal unless they change scope, evidence level, cost,
authority, or expected completion.

Failure routing: aggregate_failures returns one ProjectedFailureGroup per kind
(sorted by kind for determinism). project_delta then routes each group into
decision_relevant_failures when its authority is in DECISION_RELEVANT_AUTHORITIES,
otherwise into internal_failures.
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
    failures: tuple[FailureRecord, ...] = ()

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
class FailureRecord:
    """One raw tool failure with severity, count, optional receipt ref and authority.

    authority, when non-empty and a member of DECISION_RELEVANT_AUTHORITIES, is the
    signal project_delta uses to promote the resulting ProjectedFailureGroup into
    decision_relevant_failures instead of internal_failures.
    """

    kind: str
    severity: str
    count: int
    receipt_ref: str = ""
    authority: str = ""


@dataclass(frozen=True, slots=True)
class ProjectedFailureGroup:
    """Aggregated recoverable tool failures with raw receipt refs."""

    kind: str
    severity: str
    count: int
    receipt_refs: tuple[str, ...]
    first_seen: str
    last_seen: str
    authority: str = ""


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
    """Pure projection: returns what the user should see.

    Earlier implementation declared internal_failures and decision_relevant_failures
    fields but never populated them — they were decorative. Failures now route
    based on authority against DECISION_RELEVANT_AUTHORITIES.
    """

    raw = delta.to_dict()
    surfaced: list[str] = []
    for key, values in raw.items():
        if values:
            surfaced.append(key)
    internal: list[ProjectedFailureGroup] = []
    decision_relevant: list[ProjectedFailureGroup] = []
    phase = delta.changed_phase[0] if delta.changed_phase else ""
    if delta.failures:
        for group in aggregate_failures(delta.failures):
            if group.authority in DECISION_RELEVANT_AUTHORITIES:
                decision_relevant.append(group)
            else:
                internal.append(group)
    if not surfaced and not delta.changed_authority and not internal and not decision_relevant:
        return ProjectedProgress(deltas=(), phase=phase)
    return ProjectedProgress(
        deltas=tuple(surfaced),
        phase=phase,
        internal_failures=tuple(internal),
        decision_relevant_failures=tuple(decision_relevant),
    )


def aggregate_failures(failures: Sequence[FailureRecord]) -> tuple[ProjectedFailureGroup, ...]:
    """Group FailureRecord entries by kind, returning one ProjectedFailureGroup per kind.

    Earlier implementation dropped all but the first kind
    (first_kind = next(iter(grouped))) which silently lost multi-kind information.
    Now every kind is preserved, sorted by kind for determinism. Empty input is a
    contract violation and raises ValueError.
    """

    if not failures:
        raise ValueError("aggregate_failures requires at least one entry")
    grouped: dict[str, list[tuple[str, int, str, str]]] = {}
    for record in failures:
        grouped.setdefault(record.kind, []).append(
            (record.severity, record.count, record.receipt_ref, record.authority)
        )
    now = _now_iso()
    groups: list[ProjectedFailureGroup] = []
    for kind in sorted(grouped):
        records = grouped[kind]
        severity = records[0][0]
        total = sum(record[1] for record in records)
        receipt_refs = tuple(record[2] for record in records if record[2])
        authority = records[0][3]
        groups.append(
            ProjectedFailureGroup(
                kind=kind,
                severity=severity,
                count=total,
                receipt_refs=receipt_refs,
                first_seen=now,
                last_seen=now,
                authority=authority,
            )
        )
    return tuple(groups)
