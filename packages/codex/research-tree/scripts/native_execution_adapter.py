#!/usr/bin/env python3
"""Durable execution state and Finding Pack validation for native agent hosts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from uuid import uuid4

from host_event_protocol import build_host_event

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if SOURCE_ROOT.is_dir() and str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

try:
    from research_tree.project_workspace import (
        ProjectWorkspaceError,
        initialize_project_run,
        install_project_hooks,
        probe_lifecycle_hook,
    )
except ImportError:
    from project_workspace_contract import (
        ProjectWorkspaceError,
        initialize_project_run,
        install_project_hooks,
        probe_lifecycle_hook,
    )

try:
    from research_tree.host_capabilities import (
        WorkflowContractError,
        probe_host,
        project_workflow,
        reconcile_workflow,
        replan_workflow,
        resume_workflow,
    )
except ImportError:
    from native_workflow_contract import (
        WorkflowContractError,
        probe_host,
        project_workflow,
        reconcile_workflow,
        replan_workflow,
        resume_workflow,
    )


SCHEMA = 1
HOSTS = ("codex", "claude")
PHASES = ("landscape", "deep_dive", "adversarial", "validation")
DELIVERY_SNAPSHOT_SCHEMA = 1
PLAN_PROJECTION_SCHEMA = 1
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TASK_STATUSES = (
    "pending",
    "running",
    "submitted",
    "completed",
    "failed",
    "unknown",
)


class AdapterError(ValueError):
    """Raised for invalid execution state or artifacts."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identifier(value: str, label: str) -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        raise AdapterError(f"invalid {label}: {value!r}")
    return value


def _inside(workspace: Path, candidate: Path, label: str) -> Path:
    workspace = workspace.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise AdapterError(f"{label} must remain inside the workspace") from exc
    return resolved


def _run_dir(workspace: Path, run_id: str) -> Path:
    run_id = _identifier(run_id, "run id")
    candidates = tuple((workspace / ".research-tree" / "projects").glob(f"*/runs/{run_id}"))
    if len(candidates) != 1:
        raise AdapterError("run must resolve to exactly one project workspace")
    return _inside(workspace, candidates[0], "run directory")


def _observed_agent_ids(workspace: Path, run_id: str, host: str) -> set[str]:
    """Return child agent identities the project hook stream observed."""

    observed: set[str] = set()
    for hook_file in sorted((_run_dir(workspace, run_id) / "events").glob("*.json")):
        try:
            record = json.loads(hook_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            not isinstance(record, dict)
            or record.get("source") != "research-tree-lifecycle-hook"
            or record.get("host") != host
        ):
            continue
        agent_id = record.get("agent_id")
        if isinstance(agent_id, str) and agent_id:
            observed.add(agent_id)
    return observed


def _observed_agent_identities(workspace: Path, run_id: str, host: str) -> set[tuple[str, str, str]]:
    """Return hook-observed agent, session, and lease identity tuples."""

    observed: set[tuple[str, str, str]] = set()
    for hook_file in sorted((_run_dir(workspace, run_id) / "events").glob("*.json")):
        try:
            record = json.loads(hook_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            not isinstance(record, dict)
            or record.get("source") != "research-tree-lifecycle-hook"
            or record.get("host") != host
        ):
            continue
        agent_id = record.get("agent_id")
        session_id = record.get("session_id")
        lease_id = record.get("attempt_id")
        if all(isinstance(value, str) and value for value in (agent_id, session_id, lease_id)):
            observed.add((agent_id, session_id, lease_id))
    return observed


def _state_path(workspace: Path, run_id: str) -> Path:
    return _run_dir(workspace, run_id) / "state.json"


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AdapterError(f"missing {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AdapterError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise AdapterError(f"{label} must be a JSON object")
    return value


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_state(workspace: Path, run_id: str, host: str) -> dict[str, Any]:
    state = _read_json(_state_path(workspace, run_id), "execution state")
    if state.get("schema") != SCHEMA:
        raise AdapterError("unsupported execution-state schema")
    if state.get("host") != host or state.get("run_id") != run_id:
        raise AdapterError("execution state identity does not match arguments")
    if not isinstance(state.get("tasks"), dict):
        raise AdapterError("execution state tasks must be an object")
    if not isinstance(state.get("decision_slots"), dict) or not state["decision_slots"]:
        raise AdapterError("execution state is not bound to confirmed Decision Slots")
    if not isinstance(state.get("execution_context"), dict):
        raise AdapterError("execution state is missing confirmed execution context")
    if not isinstance(state.get("deliverables"), dict):
        raise AdapterError("execution state is missing the delivery gate")
    return state


def _save_state(workspace: Path, state: dict[str, Any]) -> None:
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated_at"] = _now()
    _atomic_write(_state_path(workspace, state["run_id"]), state)
    try:
        _write_plan_snapshot(workspace, state)
    except OSError:
        pass


def _load_handoff(workspace: Path, path: Path) -> tuple[dict[str, Any], Path]:
    resolved = _inside(workspace, path, "handoff path")
    handoff = _read_json(resolved, "alignment handoff")
    if handoff.get("schema") != 1 or handoff.get("kind") != "alignment-handoff":
        raise AdapterError("handoff must be a schema-1 alignment-handoff artifact")
    alignment_digest = handoff.get("alignment_digest")
    compiled_digest = handoff.get("compiled_graph_digest")
    if not all(
        isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
        for digest in (alignment_digest, compiled_digest)
    ):
        raise AdapterError("handoff must include alignment confirmation digests")
    if alignment_digest != compiled_digest:
        raise AdapterError("handoff has a stale alignment confirmation")
    if not isinstance(handoff.get("decision_slots"), dict) or not handoff["decision_slots"]:
        raise AdapterError("handoff decision_slots must be a nonempty object")
    if not isinstance(handoff.get("execution_context"), dict):
        raise AdapterError("handoff execution_context must be an object")
    return handoff, resolved


def init_run(workspace: Path, project_id: str, run_id: str, host: str, handoff_path: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    _identifier(project_id, "project id")
    _identifier(run_id, "run id")
    handoff, resolved_handoff = _load_handoff(workspace, handoff_path)
    requested_state = workspace / ".research-tree" / "projects" / project_id / "runs" / run_id / "state.json"
    if requested_state.exists():
        raise AdapterError(f"run already exists: {run_id}")
    try:
        project_workspace = initialize_project_run(workspace, project_id=project_id, run_id=run_id, host=host)
        installation = install_project_hooks(workspace, project_workspace)
        hook_probe = probe_lifecycle_hook(project_workspace, launcher=Path(installation["launcher"]))
    except ProjectWorkspaceError as error:
        raise AdapterError(str(error)) from error
    path = _state_path(workspace, run_id)
    if path.exists():
        raise AdapterError(f"run already exists: {run_id}")
    state: dict[str, Any] = {
        "schema": SCHEMA,
        "host": host,
        "project_id": project_workspace.project_id,
        "project_run_root": str(project_workspace.run_root),
        "lifecycle_hooks": hook_probe.status,
        "run_id": run_id,
        "status": "aligned",
        "revision": 0,
        "created_at": _now(),
        "updated_at": _now(),
        "handoff_path": str(resolved_handoff),
        "handoff_sha256": hashlib.sha256(resolved_handoff.read_bytes()).hexdigest(),
        "alignment_run_id": handoff.get("run_id"),
        "decision_slots": handoff["decision_slots"],
        "execution_context": handoff["execution_context"],
        "deliverables": {
            "technical_research_package": {"status": "pending"},
            "human_research_report": {"status": "pending"},
        },
        "agent_bindings": {},
        "tasks": {},
    }
    _save_state(workspace, state)
    return state


def add_task(
    workspace: Path,
    run_id: str,
    host: str,
    task_id: str,
    decision_slot: str,
    phase: str,
    artifact: Path,
    dependencies: list[str],
) -> dict[str, Any]:
    state = _load_state(workspace, run_id, host)
    task_id = _identifier(task_id, "task id")
    decision_slot = _identifier(decision_slot, "decision slot")
    if decision_slot not in state.get("decision_slots", {}):
        raise AdapterError(f"decision slot is not present in the confirmed handoff: {decision_slot}")
    if phase not in PHASES:
        raise AdapterError(f"invalid phase: {phase}")
    if task_id in state["tasks"]:
        raise AdapterError(f"task already exists: {task_id}")
    for dependency in dependencies:
        _identifier(dependency, "dependency")
        if dependency not in state["tasks"]:
            raise AdapterError(f"dependency has not been added: {dependency}")
    target = _inside(workspace, artifact, "artifact path")
    state["tasks"][task_id] = {
        "task_id": task_id,
        "decision_slot": decision_slot,
        "phase": phase,
        "artifact": str(target),
        "dependencies": dependencies,
        "status": "pending",
        "attempt": 0,
        "attempt_id": None,
        "worker_id": None,
        "agent_id": None,
        "session_id": None,
        "causation_id": None,
        "verified": False,
        "artifact_sha256": None,
        "failure_reason": None,
        "started_at": None,
        "submitted_at": None,
        "reviewed_at": None,
        "reviewed_by": None,
        "review_note": None,
        "checked_anchors": [],
        "reviewer_host": None,
        "reviewer_session_id": None,
        "reviewer_lease_id": None,
        "review_custody_path": None,
        "review_custody_sha256": None,
    }
    state["status"] = "running"
    _save_state(workspace, state)
    return state["tasks"][task_id]


def _artifact_integrity_error(task: dict[str, Any]) -> str | None:
    if task["status"] not in ("submitted", "completed"):
        return None
    artifact = Path(task["artifact"])
    if not artifact.is_file():
        return "artifact missing"
    expected = task.get("artifact_sha256")
    if not isinstance(expected, str) or not expected:
        return "artifact digest missing"
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
        return "artifact hash mismatch"
    return None


def _dependencies_complete(state: dict[str, Any], task: dict[str, Any]) -> bool:
    return all(
        state["tasks"][dependency]["status"] in ("submitted", "completed")
        and state["tasks"][dependency]["verified"] is True
        and _artifact_integrity_error(state["tasks"][dependency]) is None
        for dependency in task["dependencies"]
    )


def start_task(
    workspace: Path,
    run_id: str,
    host: str,
    task_id: str,
    worker_id: str | None,
) -> dict[str, Any]:
    state = _load_state(workspace, run_id, host)
    task = state["tasks"].get(task_id)
    if not isinstance(task, dict):
        raise AdapterError(f"unknown task: {task_id}")
    if task["status"] not in ("pending", "failed", "unknown"):
        raise AdapterError(f"task cannot start from {task['status']}")
    if not _dependencies_complete(state, task):
        raise AdapterError("task dependencies are not complete and verified")
    task["status"] = "running"
    task["attempt"] += 1
    task["attempt_id"] = f"attempt-{uuid4().hex}"
    task["worker_id"] = _identifier(worker_id, "worker id") if worker_id is not None else None
    task["agent_id"] = None
    task["session_id"] = None
    task["causation_id"] = None
    task["verified"] = False
    task["failure_reason"] = None
    task["started_at"] = _now()
    task["submitted_at"] = None
    task["reviewed_at"] = None
    task["reviewed_by"] = None
    task["review_note"] = None
    task["checked_anchors"] = []
    task["reviewer_host"] = None
    task["reviewer_session_id"] = None
    task["reviewer_lease_id"] = None
    task["review_custody_path"] = None
    task["review_custody_sha256"] = None
    _save_state(workspace, state)
    return task


def bind_agent(
    workspace: Path,
    run_id: str,
    host: str,
    task_id: str,
    *,
    attempt_id: str,
    agent_id: str,
    session_id: str,
    causation_id: str,
) -> dict[str, Any]:
    if host not in ("claude", "codex"):
        raise AdapterError("exact agent binding is a Claude/Codex lifecycle contract")
    state = _load_state(workspace, run_id, host)
    task = state["tasks"].get(task_id)
    if not isinstance(task, dict) or task.get("status") != "running":
        raise AdapterError("agent binding requires a running task attempt")
    if task.get("attempt_id") != _identifier(attempt_id, "attempt id"):
        raise AdapterError("agent binding does not match the active attempt")
    agent_id = _identifier(agent_id, "agent id")
    if host == "codex" and agent_id not in _observed_agent_ids(workspace, run_id, host):
        raise AdapterError(f"agent identity {agent_id!r} was not observed by the project hook stream")
    bindings = state.setdefault("agent_bindings", {})
    prior = bindings.get(agent_id)
    if isinstance(prior, dict):
        raise AdapterError(f"agent identity is already bound to {prior.get('task_id')}/{prior.get('attempt_id')}")
    binding = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "agent_id": agent_id,
        "session_id": _identifier(session_id, "session id"),
        "causation_id": _identifier(causation_id, "causation id"),
        "bound_at": _now(),
        "terminal": False,
    }
    bindings[agent_id] = binding
    task.update({"agent_id": agent_id, "session_id": session_id, "causation_id": causation_id})
    _save_state(workspace, state)
    return binding


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"Finding Pack {label} must be a non-empty string")
    return value


def _require_list(value: Any, label: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        suffix = " non-empty" if nonempty else ""
        raise AdapterError(f"Finding Pack {label} must be a{suffix} list")
    return value


def validate_finding(path: Path) -> dict[str, Any]:
    pack = _read_json(path, "Finding Pack")
    for key in ("id", "work_item_id", "decision_slot_id", "attempt_id", "phase"):
        _require_string(pack.get(key), key)
    for key in ("id", "work_item_id", "decision_slot_id", "attempt_id"):
        _identifier(pack[key], f"Finding Pack {key}")
    if pack["phase"] not in PHASES:
        raise AdapterError("Finding Pack phase is invalid")
    observations = _require_list(pack.get("observations"), "observations", nonempty=True)
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            raise AdapterError(f"Finding Pack observation {index} must be an object")
        _require_string(observation.get("claim"), f"observation {index} claim")
        anchor = observation.get("anchor")
        if not isinstance(anchor, dict) or anchor.get("kind") not in (
            "source",
            "repository",
            "input",
            "experiment",
        ):
            raise AdapterError(f"Finding Pack observation {index} anchor is invalid")
        _require_string(anchor.get("ref"), f"observation {index} anchor ref")
        _require_string(observation.get("applicability"), f"observation {index} applicability")
        if observation.get("confidence") not in ("low", "medium", "high"):
            raise AdapterError(f"Finding Pack observation {index} confidence is invalid")
        _require_string(observation.get("limitation"), f"observation {index} limitation")
    effects = _require_list(pack.get("option_effects"), "option_effects", nonempty=True)
    for index, effect in enumerate(effects):
        if not isinstance(effect, dict):
            raise AdapterError(f"Finding Pack option effect {index} must be an object")
        _require_string(effect.get("option"), f"option effect {index} option")
        if effect.get("effect") not in ("supports", "contradicts", "limits"):
            raise AdapterError(f"Finding Pack option effect {index} is invalid")
    _require_list(pack.get("implementation_implications"), "implementation_implications")
    _require_list(pack.get("remaining_uncertainties"), "remaining_uncertainties")
    continuations = pack.get("research_continuations", [])
    _require_list(continuations, "research_continuations")
    for index, continuation in enumerate(continuations):
        if not isinstance(continuation, dict):
            raise AdapterError(f"Finding Pack continuation {index} must be an object")
        if continuation.get("kind") not in (
            "deep_dive",
            "adversarial",
            "validation",
            "method_switch",
        ):
            raise AdapterError(f"Finding Pack continuation {index} kind is invalid")
        for key in ("question", "trigger", "evidence_needed", "oracle"):
            _require_string(continuation.get(key), f"continuation {index} {key}")
        cost = continuation.get("estimated_cost")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost <= 0:
            raise AdapterError(f"Finding Pack continuation {index} estimated_cost must be positive")
    validation_result = pack.get("validation_result")
    if validation_result is not None:
        if not isinstance(validation_result, dict):
            raise AdapterError("Finding Pack validation_result must be an object")
        if validation_result.get("status") not in ("passed", "failed", "inconclusive"):
            raise AdapterError("Finding Pack validation_result status is invalid")
        _require_string(validation_result.get("oracle"), "validation_result oracle")
        _require_string(validation_result.get("evidence_ref"), "validation_result evidence_ref")
    return pack


def finish_task(
    workspace: Path,
    run_id: str,
    host: str,
    task_id: str,
    result: str,
    reason: str | None,
) -> dict[str, Any]:
    state = _load_state(workspace, run_id, host)
    task = state["tasks"].get(task_id)
    if not isinstance(task, dict):
        raise AdapterError(f"unknown task: {task_id}")
    if task["status"] != "running":
        raise AdapterError("only a running task can finish")
    if result == "failed":
        task["status"] = "failed"
        task["failure_reason"] = _require_string(reason, "failure reason")
        task["worker_id"] = None
        _save_state(workspace, state)
        return task

    artifact = Path(task["artifact"])
    pack = validate_finding(artifact)
    expected = {
        "work_item_id": task["task_id"],
        "decision_slot_id": task["decision_slot"],
        "phase": task["phase"],
        "attempt_id": task["attempt_id"],
    }
    for key, value in expected.items():
        if pack[key] != value:
            raise AdapterError(f"Finding Pack {key} does not match active attempt")
    if host == "claude":
        binding = state.get("agent_bindings", {}).get(task.get("agent_id"))
        if not isinstance(binding, dict) or binding.get("attempt_id") != task.get("attempt_id"):
            raise AdapterError("Finding Pack submission requires an exact active agent binding")
    task["status"] = "submitted"
    task["verified"] = False
    task["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    task["submitted_at"] = _now()
    _save_state(workspace, state)
    return task


def verify_task(
    workspace: Path,
    run_id: str,
    host: str,
    task_id: str,
    reviewer_id: str,
    reviewer_host: str,
    reviewer_session_id: str,
    reviewer_lease_id: str,
    review_custody: Path,
    review_note: str,
    checked_anchors: list[str],
) -> dict[str, Any]:
    state = _load_state(workspace, run_id, host)
    task = state["tasks"].get(task_id)
    if not isinstance(task, dict):
        raise AdapterError(f"unknown task: {task_id}")
    if task["status"] != "submitted":
        raise AdapterError("only a submitted task can be verified")
    artifact = Path(task["artifact"])
    pack = validate_finding(artifact)
    if pack["attempt_id"] != task["attempt_id"]:
        raise AdapterError("Finding Pack does not belong to the active attempt")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if digest != task["artifact_sha256"]:
        raise AdapterError("Finding Pack changed after submission")
    validation = pack.get("validation_result")
    if not isinstance(validation, dict) or validation.get("status") != "passed":
        raise AdapterError("Finding Pack requires a passed validation result for review")

    reviewer_id = _identifier(reviewer_id, "reviewer id")
    reviewer_host = _identifier(reviewer_host, "reviewer host")
    reviewer_session_id = _identifier(reviewer_session_id, "reviewer session id")
    reviewer_lease_id = _identifier(reviewer_lease_id, "reviewer lease id")
    if reviewer_host != host:
        raise AdapterError("reviewer must use the same host as the worker")
    worker_identity = (task.get("agent_id"), task.get("session_id"), task.get("attempt_id"))
    if not all(isinstance(value, str) and value for value in worker_identity):
        raise AdapterError("review requires a host-bound worker identity")
    reviewer_identity = (reviewer_id, reviewer_session_id, reviewer_lease_id)
    if reviewer_identity == worker_identity or any(
        reviewer_identity[index] == worker_identity[index] for index in range(3)
    ):
        raise AdapterError("review requires an independent reviewer identity")
    if reviewer_identity not in _observed_agent_identities(workspace, run_id, host):
        raise AdapterError("reviewer identity was not observed by the project hook stream")
    custody = _inside(workspace, review_custody, "review custody path")
    if not custody.is_file():
        raise AdapterError("review custody path must identify a file")
    if custody == artifact.resolve():
        raise AdapterError("review custody must be distinct from the worker artifact")
    custody_digest = hashlib.sha256(custody.read_bytes()).hexdigest()
    if custody_digest != digest:
        raise AdapterError("review custody digest does not match the submitted artifact")
    expected_anchors = {observation["anchor"]["ref"] for observation in pack["observations"]}
    supplied_anchors = {_require_string(anchor, "checked anchor") for anchor in checked_anchors}
    missing = sorted(expected_anchors - supplied_anchors)
    if missing:
        raise AdapterError("evidence review is missing anchors: " + ", ".join(missing))
    task["verified"] = True
    task["reviewed_by"] = reviewer_id
    task["review_note"] = _require_string(review_note, "review note")
    task["checked_anchors"] = sorted(supplied_anchors)
    task["reviewer_host"] = reviewer_host
    task["reviewer_session_id"] = reviewer_session_id
    task["reviewer_lease_id"] = reviewer_lease_id
    task["review_custody_path"] = str(custody)
    task["review_custody_sha256"] = custody_digest
    task["reviewed_at"] = _now()
    _save_state(workspace, state)
    return task


def recover(workspace: Path, run_id: str, host: str) -> dict[str, Any]:
    state = _load_state(workspace, run_id, host)
    reasons: dict[str, str] = {}
    for task_id, task in state["tasks"].items():
        if task["status"] == "running":
            reasons[task_id] = "in-flight attempt has unknown outcome"
        else:
            integrity_error = _artifact_integrity_error(task)
            if integrity_error is not None:
                reasons[task_id] = integrity_error

    changed = True
    while changed:
        changed = False
        for task_id, task in state["tasks"].items():
            if task_id in reasons or task["status"] in ("pending", "failed", "unknown"):
                continue
            invalid_dependencies = [dependency for dependency in task["dependencies"] if dependency in reasons]
            if invalid_dependencies:
                reasons[task_id] = "dependency reopened: " + ", ".join(sorted(invalid_dependencies))
                changed = True

    for task_id in reasons:
        task = state["tasks"][task_id]
        task["status"] = "unknown"
        task["worker_id"] = None
        task["agent_id"] = None
        task["session_id"] = None
        task["causation_id"] = None
        task["verified"] = False
        task["artifact_sha256"] = None
        task["failure_reason"] = reasons[task_id]
        task["submitted_at"] = None
        task["reviewed_at"] = None
        task["reviewed_by"] = None
        task["review_note"] = None
        task["checked_anchors"] = []
        task["reviewer_host"] = None
        task["reviewer_session_id"] = None
        task["reviewer_lease_id"] = None
        task["review_custody_path"] = None
        task["review_custody_sha256"] = None
    if reasons:
        state["status"] = "running"
        _save_state(workspace, state)
    return {
        "recovered_to_unknown": sorted(reasons),
        "reasons": reasons,
        "revision": state["revision"],
    }


def status(workspace: Path, run_id: str, host: str) -> dict[str, Any]:
    state = _load_state(workspace, run_id, host)
    integrity_errors: list[str] = []
    ready: list[str] = []
    counts = {value: 0 for value in TASK_STATUSES}
    for task_id, task in state["tasks"].items():
        counts[task["status"]] += 1
        if task["status"] in ("pending", "failed", "unknown") and _dependencies_complete(state, task):
            ready.append(task_id)
        integrity_error = _artifact_integrity_error(task)
        if integrity_error is not None:
            integrity_errors.append(f"{task_id}: {integrity_error}")
    observed_complete = bool(state["tasks"]) and all(
        task["status"] == "submitted" and task["verified"] is True for task in state["tasks"].values()
    )
    observed_complete = observed_complete and not integrity_errors
    projection = _plan_projection_status(workspace, state)
    return {
        "run_id": run_id,
        "host": host,
        "status": state["status"],
        "revision": state["revision"],
        "counts": counts,
        "ready": sorted(ready),
        "complete": False,
        "observed_complete": observed_complete,
        "completion_authority": "coordinator_only",
        "integrity_errors": integrity_errors,
        "recovery_required": [error.split(":", 1)[0] for error in integrity_errors],
        "plan_projection": projection["state"],
        "plan_snapshot": projection.get("snapshot"),
    }


def _plan_snapshot_path(workspace: Path, run_id: str) -> Path:
    return _run_dir(workspace, run_id) / "codex-plan-snapshot.json"


def _plan_mirror_path(workspace: Path, run_id: str) -> Path:
    return _run_dir(workspace, run_id) / "codex-plan-mirror.json"


def _plan_snapshot(workspace: Path, state: dict[str, Any]) -> dict[str, Any]:
    task_counts = {value: 0 for value in TASK_STATUSES}
    ready: list[str] = []
    obligations: list[str] = []
    for task_id, task in sorted(state["tasks"].items()):
        task_counts[task["status"]] += 1
        if task["status"] in ("pending", "failed", "unknown") and _dependencies_complete(state, task):
            ready.append(task_id)
        if task["status"] != "submitted" or task.get("verified") is not True:
            obligations.append(f"{task_id}:independent_review_or_submission_required")
        if integrity_error := _artifact_integrity_error(task):
            obligations.append(f"{task_id}:{integrity_error}")
    if not state["tasks"]:
        obligations.append("no_host_tasks_registered")
    why_not_complete = sorted(set(obligations))
    return {
        "schema": PLAN_PROJECTION_SCHEMA,
        "kind": "codex-plan-snapshot",
        "run_id": state["run_id"],
        "host": state["host"],
        "state_revision": state["revision"],
        "status": state["status"],
        "task_counts": task_counts,
        "ready": ready,
        "unresolved_obligations": why_not_complete,
        "why_not_complete": why_not_complete or ["coordinator_completion_required"],
    }


def _write_plan_snapshot(workspace: Path, state: dict[str, Any]) -> dict[str, Any]:
    snapshot = _plan_snapshot(workspace, state)
    encoded = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    snapshot["snapshot_sha256"] = hashlib.sha256(encoded).hexdigest()
    _atomic_write(_plan_snapshot_path(workspace, state["run_id"]), snapshot)
    return snapshot


def _read_plan_snapshot(workspace: Path, state: dict[str, Any]) -> dict[str, Any] | None:
    path = _plan_snapshot_path(workspace, state["run_id"])
    try:
        snapshot = _read_json(path, "Codex plan snapshot")
    except AdapterError:
        return None
    if (
        snapshot.get("schema") != PLAN_PROJECTION_SCHEMA
        or snapshot.get("kind") != "codex-plan-snapshot"
        or snapshot.get("run_id") != state["run_id"]
        or snapshot.get("state_revision") != state["revision"]
    ):
        return None
    digest = snapshot.get("snapshot_sha256")
    unsigned = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    encoded = json.dumps(unsigned, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if not isinstance(digest, str) or digest != hashlib.sha256(encoded).hexdigest():
        return None
    return snapshot


def _plan_items(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    terminal = not snapshot["unresolved_obligations"]
    items = [
        {
            "id": f"run:{snapshot['run_id']}",
            "content": f"Durable host observation: {snapshot['status']} at revision {snapshot['state_revision']}",
            "status": "completed" if terminal else "in_progress",
        }
    ]
    for task_id in snapshot["ready"]:
        items.append(
            {
                "id": f"task:{task_id}",
                "content": f"Run ready task {task_id} from durable state",
                "status": "pending",
            }
        )
    for obligation in snapshot["unresolved_obligations"]:
        items.append(
            {
                "id": f"obligation:{obligation}",
                "content": f"Resolve {obligation}",
                "status": "pending",
            }
        )
    return items


def _plan_projection_status(workspace: Path, state: dict[str, Any]) -> dict[str, Any]:
    snapshot = _read_plan_snapshot(workspace, state)
    if snapshot is None:
        return {"state": "unavailable"}
    try:
        mirror = _read_json(_plan_mirror_path(workspace, state["run_id"]), "Codex plan mirror")
    except AdapterError:
        return {"state": "unavailable", "snapshot": snapshot}
    if (
        mirror.get("schema") != PLAN_PROJECTION_SCHEMA
        or mirror.get("kind") != "codex-plan-mirror"
        or mirror.get("run_id") != state["run_id"]
        or mirror.get("state_revision") != state["revision"]
        or mirror.get("snapshot_sha256") != snapshot["snapshot_sha256"]
        or mirror.get("items") != _plan_items(snapshot)
    ):
        return {"state": "stale", "snapshot": snapshot}
    return {"state": "current", "snapshot": snapshot}


def sync_plan_mirror(workspace: Path, run_id: str, host: str) -> dict[str, Any]:
    state = _load_state(workspace, run_id, host)
    snapshot = _read_plan_snapshot(workspace, state) or _write_plan_snapshot(workspace, state)
    mirror = {
        "schema": PLAN_PROJECTION_SCHEMA,
        "kind": "codex-plan-mirror",
        "run_id": run_id,
        "state_revision": state["revision"],
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "items": _plan_items(snapshot),
    }
    path = _plan_mirror_path(workspace, run_id)
    idempotent = False
    try:
        idempotent = _read_json(path, "Codex plan mirror") == mirror
    except AdapterError:
        pass
    if not idempotent:
        _atomic_write(path, mirror)
    return {
        "plan_projection": "current",
        "idempotent": idempotent,
        "snapshot": {
            "path": str(_plan_snapshot_path(workspace, run_id)),
            "sha256": snapshot["snapshot_sha256"],
            "state_revision": state["revision"],
        },
        "items": mirror["items"],
    }


def _delivery_snapshot_path(workspace: Path, run_id: str) -> Path:
    return _run_dir(workspace, run_id) / "delivery-snapshot.json"


def _validation_outcomes(tasks: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    outcomes = {"passed": 0, "failed": 0, "inconclusive": 0, "missing": 0}
    unresolved: list[str] = []
    for task_id, task in sorted(tasks.items()):
        if task.get("status") not in ("submitted", "completed"):
            outcomes["missing"] += 1
            unresolved.append(f"{task_id}:task_not_submitted")
            continue
        try:
            pack = _read_json(Path(task["artifact"]), "Finding Pack")
        except (AdapterError, TypeError):
            outcomes["missing"] += 1
            unresolved.append(f"{task_id}:validation_missing")
            continue
        validation = pack.get("validation_result")
        validation_status = validation.get("status") if isinstance(validation, dict) else "missing"
        if validation_status not in outcomes:
            validation_status = "missing"
        outcomes[validation_status] += 1
        if validation_status != "passed":
            unresolved.append(f"{task_id}:validation_{validation_status}")
    return outcomes, unresolved


def _delivery_snapshot(workspace: Path, state: dict[str, Any]) -> dict[str, Any]:
    task_counts = {value: 0 for value in TASK_STATUSES}
    unreviewed: list[str] = []
    independently_reviewed = 0
    for task_id, task in sorted(state["tasks"].items()):
        task_counts[task["status"]] += 1
        review_fields = (
            task.get("reviewed_by"),
            task.get("reviewer_host"),
            task.get("reviewer_session_id"),
            task.get("reviewer_lease_id"),
            task.get("review_custody_sha256"),
        )
        if task.get("verified") is True and all(isinstance(value, str) and value for value in review_fields):
            independently_reviewed += 1
        else:
            unreviewed.append(f"{task_id}:independent_review_required")
    validation_outcomes, validation_obligations = _validation_outcomes(state["tasks"])
    integrity_errors = [
        f"{task_id}:{error}"
        for task_id, task in sorted(state["tasks"].items())
        if (error := _artifact_integrity_error(task)) is not None
    ]
    unresolved = sorted({*unreviewed, *validation_obligations, *integrity_errors})
    return {
        "schema": DELIVERY_SNAPSHOT_SCHEMA,
        "kind": "delivery-receipt-snapshot",
        "run_id": state["run_id"],
        "host": state["host"],
        "state_revision": state["revision"],
        "task_counts": task_counts,
        "validation_outcomes": validation_outcomes,
        "reviewer_status": {
            "independently_reviewed": independently_reviewed,
            "unreviewed": len(unreviewed),
        },
        "host_availability": {
            "lifecycle_hooks": state.get("lifecycle_hooks"),
            "host": state["host"],
        },
        "unresolved_obligations": unresolved,
    }


def _write_delivery_snapshot(workspace: Path, state: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    snapshot = _delivery_snapshot(workspace, state)
    encoded = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    snapshot["snapshot_sha256"] = hashlib.sha256(encoded).hexdigest()
    path = _delivery_snapshot_path(workspace, state["run_id"])
    _atomic_write(path, snapshot)
    return path, snapshot


def _snapshot_lines(values: dict[str, Any]) -> list[str]:
    return [f"- {key}: {values[key]}" for key in sorted(values)]


def _render_delivery_report(kind: str, snapshot_path: Path, snapshot: dict[str, Any]) -> str:
    digest = snapshot["snapshot_sha256"]
    title = "Technical Research Package" if kind == "technical_research_package" else "Human Research Report"
    lines = [
        f"# {title}",
        "",
        f"<!-- research-tree-delivery-snapshot: {digest} -->",
        "",
        "## Receipt Snapshot",
        "",
        f"- snapshot_ref: {snapshot_path.name}",
        f"- snapshot_sha256: {digest}",
        f"- run_id: {snapshot['run_id']}",
        f"- state_revision: {snapshot['state_revision']}",
        "",
        "## Task Metrics",
        "",
        *_snapshot_lines(snapshot["task_counts"]),
        "",
        "## Validation Outcomes",
        "",
        *_snapshot_lines(snapshot["validation_outcomes"]),
        "",
        "## Review Status",
        "",
        *_snapshot_lines(snapshot["reviewer_status"]),
        "",
        "## Unresolved Obligations",
        "",
    ]
    if snapshot["unresolved_obligations"]:
        lines.extend(f"- {value}" for value in snapshot["unresolved_obligations"])
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def render_delivery_reports(
    workspace: Path,
    run_id: str,
    host: str,
    technical_report: Path,
    human_report: Path,
) -> dict[str, Any]:
    state = _load_state(workspace, run_id, host)
    snapshot_path, snapshot = _write_delivery_snapshot(workspace, state)
    technical = _inside(workspace, technical_report, "technical_research_package path")
    human = _inside(workspace, human_report, "human_research_report path")
    _atomic_write_text(technical, _render_delivery_report("technical_research_package", snapshot_path, snapshot))
    _atomic_write_text(human, _render_delivery_report("human_research_report", snapshot_path, snapshot))
    return {
        "snapshot": {
            "path": str(snapshot_path),
            "sha256": snapshot["snapshot_sha256"],
            "state_revision": snapshot["state_revision"],
        },
        "technical_research_package": _observe_report(workspace, technical, "technical_research_package"),
        "human_research_report": _observe_report(workspace, human, "human_research_report"),
    }


def _projection_mismatch(kind: str, expected: str, actual: str, snapshot: dict[str, Any]) -> str:
    if actual == expected:
        return ""
    for group_name in ("task_counts", "validation_outcomes", "reviewer_status"):
        for field, expected_value in snapshot[group_name].items():
            expected_line = f"- {field}: {expected_value}"
            actual_line = next((line for line in actual.splitlines() if line.startswith(f"- {field}:")), None)
            if actual_line != expected_line:
                return f"delivery report metric mismatch: {group_name}.{field}"
    marker = f"<!-- research-tree-delivery-snapshot: {snapshot['snapshot_sha256']} -->"
    if marker not in actual:
        return "delivery report snapshot digest mismatch"
    return f"{kind} contains prose not generated from the canonical delivery snapshot"


def _observe_report_projection(
    workspace: Path,
    path: Path,
    kind: str,
    snapshot_path: Path,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    manifest = _observe_report(workspace, path, kind)
    if not manifest.get("exists"):
        raise AdapterError(f"{kind} projection is missing")
    if manifest.get("encoding") == "invalid_utf8":
        raise AdapterError(f"{kind} projection must be UTF-8")
    actual = path.read_text(encoding="utf-8")
    expected = _render_delivery_report(kind, snapshot_path, snapshot)
    if mismatch := _projection_mismatch(kind, expected, actual, snapshot):
        raise AdapterError(mismatch)
    manifest["snapshot_ref"] = str(snapshot_path)
    manifest["snapshot_sha256"] = snapshot["snapshot_sha256"]
    manifest["state_revision"] = snapshot["state_revision"]
    return manifest


def _observe_report(workspace: Path, path: Path, kind: str) -> dict[str, Any]:
    resolved = _inside(workspace, path, f"{kind} path")
    if not resolved.is_file():
        return {"status": "observed", "kind": kind, "path": str(resolved), "exists": False}
    raw = resolved.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {
            "status": "observed",
            "kind": kind,
            "path": str(resolved),
            "exists": True,
            "bytes": len(raw),
            "encoding": "invalid_utf8",
        }
    headings = len(re.findall(r"(?m)^#{1,6}\s+\S", text))
    return {
        "status": "observed",
        "kind": kind,
        "path": str(resolved),
        "exists": True,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "heading_count": headings,
    }


def complete_run(
    workspace: Path,
    run_id: str,
    host: str,
    technical_report: Path,
    human_report: Path,
) -> dict[str, Any]:
    summary = status(workspace, run_id, host)
    if not summary["observed_complete"]:
        raise AdapterError("host observations are incomplete; coordinator must assess closure")
    state = _load_state(workspace, run_id, host)
    snapshot_path, snapshot = _write_delivery_snapshot(workspace, state)
    technical = _inside(workspace, technical_report, "technical_research_package path")
    human = _inside(workspace, human_report, "human_research_report path")
    state["deliverables"] = {
        "technical_research_package": _observe_report_projection(
            workspace,
            technical,
            "technical_research_package",
            snapshot_path,
            snapshot,
        ),
        "human_research_report": _observe_report_projection(
            workspace,
            human,
            "human_research_report",
            snapshot_path,
            snapshot,
        ),
    }
    state["status"] = "delivery_pending"
    state["completion_authority"] = "coordinator_only"
    _save_state(workspace, state)
    return status(workspace, run_id, host)


def emit_host_event(
    workspace: Path,
    run_id: str,
    host: str,
    task_id: str,
    *,
    event_id: str,
    kind: str,
    sequence: int,
    actor: str,
    payload: dict[str, Any],
    expected_revision: int,
    causation_id: str | None = None,
) -> dict[str, Any]:
    state = _load_state(workspace, run_id, host)
    task = state["tasks"].get(task_id)
    if not isinstance(task, dict) or not task.get("attempt_id"):
        raise AdapterError("host event requires an active task attempt")
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
        raise AdapterError("canonical expected revision must be a nonnegative integer")
    return build_host_event(
        event_id=event_id,
        kind=kind,
        run_id=run_id,
        attempt_id=str(task["attempt_id"]),
        expected_revision=expected_revision,
        sequence=sequence,
        actor=actor,
        payload=payload,
        decision_slot_id=str(task["decision_slot"]),
        causation_id=causation_id,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=HOSTS, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--project-id", required=True)
    init_parser.add_argument("--run-id", required=True)
    init_parser.add_argument(
        "--handoff",
        type=Path,
        required=True,
        help="persisted alignment-handoff JSON produced by alignment_controller.py compile",
    )

    add_parser = subparsers.add_parser("add-task")
    add_parser.add_argument("--run-id", required=True)
    add_parser.add_argument("--task-id", required=True)
    add_parser.add_argument("--decision-slot", required=True)
    add_parser.add_argument("--phase", choices=PHASES, required=True)
    add_parser.add_argument("--artifact", type=Path, required=True)
    add_parser.add_argument("--depends-on", action="append", default=[])

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--run-id", required=True)
    start_parser.add_argument("--task-id", required=True)
    start_parser.add_argument("--worker-id")

    bind_parser = subparsers.add_parser("bind-agent")
    bind_parser.add_argument("--run-id", required=True)
    bind_parser.add_argument("--task-id", required=True)
    bind_parser.add_argument("--attempt-id", required=True)
    bind_parser.add_argument("--agent-id", required=True)
    bind_parser.add_argument("--session-id", required=True)
    bind_parser.add_argument("--causation-id", required=True)

    finish_parser = subparsers.add_parser("finish")
    finish_parser.add_argument("--run-id", required=True)
    finish_parser.add_argument("--task-id", required=True)
    finish_parser.add_argument("--result", choices=("submitted", "failed"), required=True)
    finish_parser.add_argument("--reason")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--run-id", required=True)
    verify_parser.add_argument("--task-id", required=True)
    verify_parser.add_argument("--reviewer-id", required=True)
    verify_parser.add_argument("--reviewer-host", required=True)
    verify_parser.add_argument("--reviewer-session-id", required=True)
    verify_parser.add_argument("--reviewer-lease-id", required=True)
    verify_parser.add_argument("--review-custody", type=Path, required=True)
    verify_parser.add_argument("--review-note", required=True)
    verify_parser.add_argument("--checked-anchor", action="append", default=[])

    recover_parser = subparsers.add_parser("recover")
    recover_parser.add_argument("--run-id", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--run-id", required=True)

    sync_plan_parser = subparsers.add_parser("sync-plan")
    sync_plan_parser.add_argument("--run-id", required=True)

    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("--run-id", required=True)
    complete_parser.add_argument("--technical-report", type=Path, required=True)
    complete_parser.add_argument("--human-report", type=Path, required=True)

    render_delivery_parser = subparsers.add_parser("render-delivery")
    render_delivery_parser.add_argument("--run-id", required=True)
    render_delivery_parser.add_argument("--technical-report", type=Path, required=True)
    render_delivery_parser.add_argument("--human-report", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate-finding")
    validate_parser.add_argument("path", type=Path)

    probe_parser = subparsers.add_parser("probe-host")
    probe_parser.add_argument("--observations", type=Path, required=True)

    project_parser = subparsers.add_parser("project-workflow")
    project_parser.add_argument("--request", type=Path, required=True)

    reconcile_parser = subparsers.add_parser("reconcile-host")
    reconcile_parser.add_argument("--request", type=Path, required=True)

    replan_parser = subparsers.add_parser("replan-workflow")
    replan_parser.add_argument("--request", type=Path, required=True)

    resume_parser = subparsers.add_parser("resume-workflow")
    resume_parser.add_argument("--request", type=Path, required=True)

    emit_parser = subparsers.add_parser("emit-event")
    emit_parser.add_argument("--run-id", required=True)
    emit_parser.add_argument("--task-id", required=True)
    emit_parser.add_argument("--event-id", required=True)
    emit_parser.add_argument("--kind", required=True)
    emit_parser.add_argument("--expected-revision", type=int, required=True)
    emit_parser.add_argument("--sequence", type=int, required=True)
    emit_parser.add_argument("--actor", required=True)
    emit_parser.add_argument("--causation-id")
    emit_parser.add_argument("--payload", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    workspace = args.workspace.resolve()
    try:
        contract_host = "claude-code" if args.host == "claude" else args.host
        if args.command == "probe-host":
            result = probe_host(contract_host, _read_json(args.observations.resolve(), "capability observations"))
        elif args.command == "project-workflow":
            result = project_workflow(_read_json(args.request.resolve(), "workflow projection request"), contract_host)
        elif args.command == "reconcile-host":
            result = reconcile_workflow(
                _read_json(args.request.resolve(), "workflow reconciliation request"), contract_host
            )
        elif args.command == "replan-workflow":
            result = replan_workflow(_read_json(args.request.resolve(), "workflow replan request"), contract_host)
        elif args.command == "resume-workflow":
            result = resume_workflow(_read_json(args.request.resolve(), "workflow resume request"), contract_host)
        elif args.command == "emit-event":
            payload_path = args.payload if args.payload.is_absolute() else workspace / args.payload
            result = emit_host_event(
                workspace,
                args.run_id,
                args.host,
                args.task_id,
                event_id=args.event_id,
                kind=args.kind,
                sequence=args.sequence,
                actor=args.actor,
                payload=_read_json(payload_path, "host event payload"),
                expected_revision=args.expected_revision,
                causation_id=args.causation_id,
            )
        elif args.command == "init":
            handoff = args.handoff if args.handoff.is_absolute() else workspace / args.handoff
            result = init_run(workspace, args.project_id, args.run_id, args.host, handoff)
        elif args.command == "add-task":
            artifact = args.artifact
            if not artifact.is_absolute():
                artifact = workspace / artifact
            result = add_task(
                workspace,
                args.run_id,
                args.host,
                args.task_id,
                args.decision_slot,
                args.phase,
                artifact,
                args.depends_on,
            )
        elif args.command == "start":
            result = start_task(workspace, args.run_id, args.host, args.task_id, args.worker_id)
        elif args.command == "bind-agent":
            result = bind_agent(
                workspace,
                args.run_id,
                args.host,
                args.task_id,
                attempt_id=args.attempt_id,
                agent_id=args.agent_id,
                session_id=args.session_id,
                causation_id=args.causation_id,
            )
        elif args.command == "finish":
            result = finish_task(
                workspace,
                args.run_id,
                args.host,
                args.task_id,
                args.result,
                args.reason,
            )
        elif args.command == "verify":
            custody = args.review_custody if args.review_custody.is_absolute() else workspace / args.review_custody
            result = verify_task(
                workspace,
                args.run_id,
                args.host,
                args.task_id,
                args.reviewer_id,
                args.reviewer_host,
                args.reviewer_session_id,
                args.reviewer_lease_id,
                custody,
                args.review_note,
                args.checked_anchor,
            )
        elif args.command == "recover":
            result = recover(workspace, args.run_id, args.host)
        elif args.command == "status":
            result = status(workspace, args.run_id, args.host)
        elif args.command == "sync-plan":
            result = sync_plan_mirror(workspace, args.run_id, args.host)
        elif args.command == "complete":
            technical = (
                args.technical_report if args.technical_report.is_absolute() else workspace / args.technical_report
            )
            human = args.human_report if args.human_report.is_absolute() else workspace / args.human_report
            result = complete_run(workspace, args.run_id, args.host, technical, human)
        elif args.command == "render-delivery":
            technical = (
                args.technical_report if args.technical_report.is_absolute() else workspace / args.technical_report
            )
            human = args.human_report if args.human_report.is_absolute() else workspace / args.human_report
            result = render_delivery_reports(workspace, args.run_id, args.host, technical, human)
        else:
            result = validate_finding(args.path.resolve())
    except (AdapterError, OSError, WorkflowContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
