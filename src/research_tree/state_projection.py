"""Issue #320: canonical self-state projection for consumers.

CLI, hooks, host adapters, briefs, strategy visualization, and final
responses consume the same projection built from coordinator.self_state().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class StateProjection:
    """One canonical state projection that all consumers share."""

    phase: str
    active_branch: str
    reconciliation_delta: tuple[str, ...] = ()
    current_action: str = ""
    current_action_reason: str = ""
    next_action: str = ""
    blockers: tuple[str, ...] = ()
    authority_waits: tuple[str, ...] = ()
    disputes: tuple[str, ...] = ()
    experiments: tuple[str, ...] = ()
    resumable: bool = True

    @classmethod
    def from_coordinator_snapshot(cls, snapshot: Mapping) -> "StateProjection":
        """Build from coordinator.self_state() output (regions + lineage)."""

        workflow = snapshot.get("workflow", {})
        lineage = snapshot.get("lineage", {})
        return cls(
            phase=str(workflow.get("value", "")),
            active_branch=str(lineage.get("active_branch", "") or ""),
            reconciliation_delta=tuple(lineage.get("reconciliation_delta", ())),
            current_action=str(lineage.get("current_action", "")),
            current_action_reason=str(lineage.get("current_action_reason", "")),
            next_action=str(lineage.get("next_action", "")),
            blockers=tuple(lineage.get("blockers", ())),
            authority_waits=tuple(lineage.get("authority_waits", ())),
            disputes=tuple(lineage.get("disputes", ())),
            experiments=tuple(lineage.get("experiments", ())),
            resumable=bool(lineage.get("resumable", True)),
        )


def render_progress_summary(projection: StateProjection) -> str:
    """Compact human-readable summary for CLI / brief / host adapter surfaces."""

    parts = []
    parts.append(f"phase={projection.phase or 'unknown'}")
    if projection.active_branch:
        parts.append(f"branch={projection.active_branch}")
    if projection.reconciliation_delta:
        parts.append(f"reconciliation_delta=[{', '.join(projection.reconciliation_delta)}]")
    if projection.current_action:
        parts.append(f"action={projection.current_action}")
    if projection.current_action_reason:
        parts.append(f"reason={projection.current_action_reason}")
    if projection.blockers:
        parts.append(f"blockers=[{', '.join(projection.blockers)}]")
    if projection.authority_waits:
        parts.append(f"authority_waits=[{', '.join(projection.authority_waits)}]")
    if projection.disputes:
        parts.append(f"disputes=[{', '.join(projection.disputes)}]")
    if projection.next_action:
        parts.append(f"next={projection.next_action}")
    if not projection.resumable:
        parts.append("resumable=false")
    return " ".join(parts)
