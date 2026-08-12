"""Runtime wrappers for non-authoritative native workflow projections."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .host_capabilities import (
    HOST_SURFACES,
    HostCapabilityError,
    project_workflow,
    reconcile_workflow,
    replan_workflow,
    resume_workflow,
)
from .host_events import HostEvent, normalize_host_payload, payload_digest

WORKFLOW_STATUSES = frozenset({"projected", "active", "paused", "stale", "failed", "completed", "reconciled"})
CHILD_OBSERVATIONS = frozenset({"active", "completed", "unknown", "stale", "cancelled", "failed"})
NativeWorkflowError = HostCapabilityError
NativeWorkflowRun = dict[str, Any]
WorkflowChild = dict[str, Any]
WorkflowReconciliation = dict[str, Any]


def project_native_workflow(
    *, capability_probe: Mapping[str, Any], actions: Sequence[Mapping[str, Any]], **values: Any
) -> NativeWorkflowRun:
    return project_workflow(
        {**values, "capability_probe": capability_probe, "actions": list(actions)}, str(capability_probe["host"])
    )


def replan_native_workflow(workflow: Mapping[str, Any], **values: Any) -> NativeWorkflowRun:
    if "successor_actions" in values:
        values["successor_actions"] = list(values["successor_actions"])
    return replan_workflow({**values, "workflow": workflow}, str(workflow["host"]))


def resume_native_workflow(workflow: Mapping[str, Any], **values: Any) -> NativeWorkflowRun:
    return resume_workflow({**values, "workflow": workflow}, str(workflow["host"]))


def reconcile_native_workflow(workflow: Mapping[str, Any], **values: Any) -> WorkflowReconciliation:
    return reconcile_workflow({**values, "workflow": workflow}, str(workflow["host"]))


def workflow_host_event(
    workflow: Mapping[str, Any],
    *,
    event_id: str,
    kind: str,
    attempt_id: str,
    sequence: int,
    created_at: str,
    **details: Any,
) -> HostEvent:
    common = {
        key: workflow[key]
        for key in (
            "workflow_id",
            "script_id",
            "capability_digest",
            "strategy_revision",
            "action_refs",
            "phase_refs",
            "checkpoint_refs",
            "fallback_id",
        )
    }
    required = {
        "workflow_phase_completed": (
            "phase_id",
            "child_attempt_refs",
            "produced_artifact_refs",
            "successor_disposition",
        ),
        "provider_failure": ("category", "provider", "model", "opaque_code", "safe_log_ref"),
        "reconciliation_detected": ("classifications", "next_action"),
    }.get(kind, ())
    missing = [field for field in required if field not in details]
    if missing:
        raise NativeWorkflowError(f"{kind} details missing: {', '.join(missing)}")
    payload = normalize_host_payload(
        {**common, "authoritative": False, "completion_authority": "coordinator_only", "complete": False, **details}
    )
    return HostEvent(
        event_id=event_id,
        kind=kind,
        run_id=str(workflow["run_id"]),
        round_id=str(workflow["run_id"]),
        attempt_id=attempt_id,
        expected_revision=int(workflow["run_revision"]),
        sequence=sequence,
        actor=str(workflow["host"]),
        created_at=created_at,
        payload=payload,
        payload_digest=payload_digest(payload),
    )


__all__ = [
    "CHILD_OBSERVATIONS",
    "HOST_SURFACES",
    "WORKFLOW_STATUSES",
    "NativeWorkflowError",
    "NativeWorkflowRun",
    "WorkflowChild",
    "WorkflowReconciliation",
    "project_native_workflow",
    "reconcile_native_workflow",
    "replan_native_workflow",
    "resume_native_workflow",
    "workflow_host_event",
]
