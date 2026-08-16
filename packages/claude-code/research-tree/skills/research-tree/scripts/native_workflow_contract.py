"""Dependency-free host capability and native workflow contract."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

HOSTS = ("codex", "claude-code", "hermes")
CAPABILITIES = (
    "native_dynamic_workflow",
    "dynamic_delegation",
    "parallel_workers",
    "lifecycle_hooks",
    "background_execution",
    "durable_resume",
    "scheduled_drain",
    "structured_event_transport",
    "claude-agent-children",
    "claude-native-workflow",
    "claude-hybrid-workflow",
)
CAPABILITY_STATES = frozenset({"available", "unavailable", "partial", "denied", "failed", "unknown"})
REQUIRED = ("native_dynamic_workflow", "dynamic_delegation", "durable_resume", "structured_event_transport")
HOST_SURFACES = {
    "claude-code": "claude-dynamic-phases",
    "codex": "codex-concurrent-ready",
    "hermes": "hermes-delegation-batch",
}
EXECUTION_MODES = ("agent", "workflow", "hybrid")
MODE_REQUIREMENTS = {
    "agent": ("dynamic_delegation", "claude-agent-children"),
    "workflow": ("native_dynamic_workflow", "claude-native-workflow"),
    "hybrid": ("native_dynamic_workflow", "dynamic_delegation", "claude-hybrid-workflow"),
}
FALLBACK_ID = "coordinator-dispatch-v1"
CAPABILITY_FALLBACKS = {
    "parallel_workers": "bounded-sequential-dispatch-v1",
    "lifecycle_hooks": "host-event-observation-v1",
    "background_execution": "foreground-checkpoint-v1",
    "scheduled_drain": "checkpoint-resume-v1",
}
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class HostCapabilityError(ValueError):
    """Raised when adapter input violates the portable contract."""


WorkflowContractError = HostCapabilityError


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _identifier(value: Any, label: str) -> str:
    text = str(value)
    if not IDENTIFIER.fullmatch(text):
        raise HostCapabilityError(f"{label} must be a valid identifier")
    return text


def _opaque_identifier(value: Any, label: str) -> str:
    text = str(value)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", text):
        raise HostCapabilityError(f"{label} must be a valid host identifier")
    return text


def _sha256(value: Any, label: str) -> str:
    text = str(value)
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise HostCapabilityError(f"{label} must be a lowercase SHA-256 digest")
    return text


def capability_manifest(host: str) -> dict[str, Any]:
    if host not in HOSTS:
        raise HostCapabilityError(f"unsupported host: {host}")
    return {
        "schema_version": 1,
        "host": host,
        "capabilities": list(CAPABILITIES),
        "required_for_native": list(REQUIRED),
        "fallback_id": FALLBACK_ID,
        "unknown_rule": "unsupported_until_observed_available",
    }


def probe_host(host: str, observations: Mapping[str, Any]) -> dict[str, Any]:
    capability_manifest(host)
    if not isinstance(observations, Mapping):
        raise HostCapabilityError("capability observations must be an object")
    unknown = set(observations) - set(CAPABILITIES)
    if unknown:
        raise HostCapabilityError(f"unsupported capability: {sorted(unknown)[0]}")
    normalized = {name: str(observations.get(name, "unknown")) for name in CAPABILITIES}
    invalid = [name for name, state in normalized.items() if state not in CAPABILITY_STATES]
    if invalid:
        raise HostCapabilityError(f"invalid capability state for {invalid[0]}")
    mode = "native" if all(normalized[name] == "available" for name in REQUIRED) else "fallback"
    execution_modes = {}
    for execution_mode, requirements in MODE_REQUIREMENTS.items():
        states = [normalized[name] for name in requirements]
        execution_modes[execution_mode] = (
            "available"
            if all(state == "available" for state in states)
            else "partial"
            if "partial" in states
            else "unavailable"
            if any(state in {"unavailable", "denied", "failed"} for state in states)
            else "unavailable"
        )
    result = {
        "schema_version": 1,
        "host": host,
        "observations": normalized,
        "mode": mode,
        "execution_modes": execution_modes,
        "fallback_id": None if mode == "native" else FALLBACK_ID,
        "failure_codes": {},
        "selected_fallbacks": {
            capability: fallback
            for capability, fallback in CAPABILITY_FALLBACKS.items()
            if normalized[capability] != "available"
        },
    }
    return {**result, "semantic_digest": _digest(result)}


def validate_probe(value: Mapping[str, Any]) -> dict[str, Any]:
    observations = value.get("observations")
    if not isinstance(observations, Mapping):
        raise HostCapabilityError("capability probe observations must be an object")
    expected = probe_host(str(value.get("host", "")), observations)
    failures = value.get("failure_codes", {})
    if not isinstance(failures, Mapping):
        raise HostCapabilityError("failure_codes must be an object")
    expected["failure_codes"] = {str(key): str(code) for key, code in failures.items()}
    semantic = {key: child for key, child in expected.items() if key != "semantic_digest"}
    expected["semantic_digest"] = _digest(semantic)
    if value.get("semantic_digest") != expected["semantic_digest"]:
        raise HostCapabilityError("capability probe semantic digest does not match")
    return expected


def record_probe_failure(probe: Mapping[str, Any], capability: str, code: str) -> dict[str, Any]:
    current = validate_probe(probe)
    if capability not in CAPABILITIES:
        raise HostCapabilityError(f"unsupported capability: {capability}")
    observations = dict(current["observations"])
    observations[capability] = "failed"
    failed = probe_host(str(current["host"]), observations)
    failed["failure_codes"] = {**current["failure_codes"], capability: str(code)}
    semantic = {key: value for key, value in failed.items() if key != "semantic_digest"}
    failed["semantic_digest"] = _digest(semantic)
    return failed


def _workflow(value: Any, expected_host: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise HostCapabilityError("workflow must be an object")
    workflow = dict(value)
    if workflow.get("host") != expected_host:
        raise HostCapabilityError("workflow host does not match adapter")
    if workflow.pop("semantic_digest", None) != _digest(workflow):
        raise HostCapabilityError("workflow semantic digest does not match")
    return workflow


def _children(actions: Sequence[Mapping[str, Any]], workflow_id: str) -> tuple[list[str], list[dict[str, Any]]]:
    phases: list[str] = []
    children = []
    for index, action in enumerate(actions, 1):
        action_id = _identifier(action.get("action_id"), "action_id")
        phase_id = _identifier(action.get("phase_id"), "phase_id")
        if phase_id not in phases:
            phases.append(phase_id)
        dependencies = action.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise HostCapabilityError("action dependencies must be a list")
        children.append(
            {
                "action_id": action_id,
                "phase_id": phase_id,
                "attempt_id": f"{workflow_id}-child-{index}",
                "dependencies": [_identifier(item, "dependency") for item in dependencies],
                "status": "projected",
            }
        )
    return phases, children


def project_workflow(request: Mapping[str, Any], expected_host: str) -> dict[str, Any]:
    probe_value, actions = request.get("capability_probe"), request.get("actions")
    if not isinstance(probe_value, Mapping) or not isinstance(actions, Sequence) or isinstance(actions, (str, bytes)):
        raise HostCapabilityError("projection requires capability_probe and actions")
    probe = validate_probe(probe_value)
    if probe["host"] != expected_host:
        raise HostCapabilityError("capability probe host does not match adapter")
    workflow_id = _identifier(request.get("workflow_id"), "workflow_id")
    execution_mode = str(request.get("execution_mode", "workflow"))
    if execution_mode not in EXECUTION_MODES:
        raise HostCapabilityError(f"unsupported execution mode: {execution_mode}")
    phases, children = _children(actions, workflow_id)
    max_phases, max_children = int(request.get("max_phases", 0)), int(request.get("max_children", 0))
    if max_phases < 1 or len(phases) > max_phases:
        raise HostCapabilityError("workflow exceeds maximum phases")
    if max_children < 1 or len(children) > max_children:
        raise HostCapabilityError("workflow exceeds maximum children")
    native_surface = HOST_SURFACES[expected_host] if probe["mode"] == "native" else "coordinator-dispatch"
    workflow_evidence = None
    if expected_host == "claude-code":
        mode_state = probe["execution_modes"][execution_mode]
        if mode_state != "available":
            missing = next(
                name for name in MODE_REQUIREMENTS[execution_mode] if probe["observations"][name] != "available"
            )
            raise HostCapabilityError(f"{missing} is unavailable")
        native_surface = {
            "agent": "claude-agent-children",
            "workflow": "claude-dynamic-phases",
            "hybrid": "claude-hybrid-workflow",
        }[execution_mode]
        if execution_mode in {"workflow", "hybrid"}:
            live = request.get("live_workflow")
            if isinstance(live, Mapping):
                phase_ids = tuple(_identifier(item, "live workflow phase id") for item in live.get("phase_ids", ()))
                child_ids = tuple(_identifier(item, "live workflow child id") for item in live.get("child_ids", ()))
                if len(phase_ids) < 2:
                    raise HostCapabilityError("live workflow evidence requires at least two phases")
                if execution_mode == "hybrid" and not child_ids:
                    raise HostCapabilityError("hybrid live workflow evidence requires child identities")
                workflow_evidence = {
                    "workflow_id": _opaque_identifier(live.get("workflow_id"), "live workflow id"),
                    "task_id": _opaque_identifier(live.get("task_id"), "live workflow task id"),
                    "script_id": _opaque_identifier(live.get("script_id"), "live script id"),
                    "script_sha256": _sha256(live.get("script_sha256"), "live script digest"),
                    "run_id": _identifier(live.get("run_id"), "live run id"),
                    "phase_ids": list(phase_ids),
                    "child_ids": list(child_ids),
                    "receipt_ref": live.get("receipt_ref"),
                }
    result = {
        "schema_version": 1,
        "workflow_id": workflow_id,
        "script_id": _identifier(request.get("script_id"), "script_id"),
        "run_id": _identifier(request.get("run_id"), "run_id"),
        "host": expected_host,
        "run_revision": int(request.get("run_revision", -1)),
        "strategy_revision": _identifier(request.get("strategy_revision"), "strategy_revision"),
        "projection_revision": 1,
        "capability_digest": probe["semantic_digest"],
        "permission_profile": _identifier(request.get("permission_profile"), "permission_profile"),
        "checkpoint_contract": _identifier(request.get("checkpoint_contract"), "checkpoint_contract"),
        "action_refs": [child["action_id"] for child in children],
        "phase_refs": phases,
        "children": children,
        "checkpoint_refs": [_identifier(item, "checkpoint_ref") for item in request.get("checkpoint_refs", [])],
        "mode": probe["mode"],
        "execution_mode": execution_mode,
        "native_surface": native_surface,
        "workflow_evidence": workflow_evidence,
        "fallback_id": probe["fallback_id"],
        "max_phases": max_phases,
        "max_children": max_children,
        "status": "projected",
        "stale_phase_refs": [],
        "replan_event_refs": [],
        "failure_category": None,
        "authoritative": False,
        "completion_authority": "coordinator_only",
        "complete": False,
    }
    return {**result, "semantic_digest": _digest(result)}


def reconcile_workflow(request: Mapping[str, Any], expected_host: str) -> dict[str, Any]:
    workflow, observations = _workflow(request.get("workflow"), expected_host), request.get("host_children")
    if not isinstance(observations, Mapping):
        raise HostCapabilityError("host_children must be an object")
    checkpointed = set(map(str, request.get("checkpoint_child_refs", [])))
    stale = workflow["strategy_revision"] != request.get("current_strategy_revision")
    classifications = {}
    for child in workflow["children"]:
        attempt = _identifier(child["attempt_id"], "attempt_id")
        observed = str(observations.get(attempt, "unknown"))
        if observed not in {"active", "completed", "unknown", "stale", "cancelled", "failed"}:
            raise HostCapabilityError(f"unsupported child observation: {observed}")
        classifications[attempt] = (
            "stale" if stale else "unknown" if observed == "completed" and attempt not in checkpointed else observed
        )
    values = set(classifications.values())
    next_action = (
        "replan"
        if "stale" in values
        else "resume_from_checkpoint"
        if values & {"unknown", "failed", "cancelled"}
        else "coordinator_assess_evidence"
        if values == {"completed"}
        else "wait_for_host_events"
    )
    return {
        "workflow_id": workflow["workflow_id"],
        "classifications": classifications,
        "next_action": next_action,
        "complete": False,
        "authoritative": False,
        "completion_authority": "coordinator_only",
    }


def replan_workflow(request: Mapping[str, Any], expected_host: str) -> dict[str, Any]:
    workflow, actions = _workflow(request.get("workflow"), expected_host), request.get("successor_actions")
    if not isinstance(actions, list):
        raise HostCapabilityError("successor_actions must be a list")
    phases, children = _children(actions, workflow["workflow_id"])
    if len(phases) > workflow["max_phases"] or len(children) > workflow["max_children"]:
        raise HostCapabilityError("workflow exceeds configured bounds")
    workflow.update(
        run_revision=int(request.get("run_revision", -1)),
        strategy_revision=_identifier(request.get("strategy_revision"), "strategy_revision"),
        projection_revision=workflow["projection_revision"] + 1,
        action_refs=[child["action_id"] for child in children],
        phase_refs=phases,
        children=children,
        stale_phase_refs=workflow["phase_refs"],
        replan_event_refs=workflow["replan_event_refs"]
        + [_identifier(request.get("reason_event_ref"), "reason_event_ref")],
        status="projected",
        failure_category=None,
        complete=False,
    )
    return {**workflow, "semantic_digest": _digest(workflow)}


def resume_workflow(request: Mapping[str, Any], expected_host: str) -> dict[str, Any]:
    workflow = _workflow(request.get("workflow"), expected_host)
    checkpoint = _identifier(request.get("checkpoint_ref"), "checkpoint_ref")
    checkpoints = list(workflow["checkpoint_refs"])
    if checkpoint not in checkpoints:
        checkpoints.append(checkpoint)
    workflow.update(
        run_revision=int(request.get("run_revision", -1)),
        projection_revision=workflow["projection_revision"] + 1,
        checkpoint_refs=checkpoints,
        status="active",
        complete=False,
    )
    return {**workflow, "semantic_digest": _digest(workflow)}


__all__ = [
    "CAPABILITIES",
    "CAPABILITY_FALLBACKS",
    "CAPABILITY_STATES",
    "FALLBACK_ID",
    "HOSTS",
    "HOST_SURFACES",
    "EXECUTION_MODES",
    "HostCapabilityError",
    "WorkflowContractError",
    "capability_manifest",
    "probe_host",
    "project_workflow",
    "record_probe_failure",
    "reconcile_workflow",
    "replan_workflow",
    "resume_workflow",
    "validate_probe",
]
