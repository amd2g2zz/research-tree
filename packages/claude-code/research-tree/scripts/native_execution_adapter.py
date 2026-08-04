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


SCHEMA = 1
HOSTS = ("codex", "claude")
PHASES = ("landscape", "deep_dive", "adversarial", "validation")
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
    return _inside(
        workspace,
        workspace / ".research-tree-native" / _identifier(run_id, "run id"),
        "run directory",
    )


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


def _load_handoff(workspace: Path, path: Path) -> tuple[dict[str, Any], Path]:
    resolved = _inside(workspace, path, "handoff path")
    handoff = _read_json(resolved, "alignment handoff")
    if handoff.get("schema") != 1 or handoff.get("kind") != "alignment-handoff":
        raise AdapterError("handoff must be a schema-1 alignment-handoff artifact")
    if not isinstance(handoff.get("decision_slots"), dict) or not handoff["decision_slots"]:
        raise AdapterError("handoff decision_slots must be a nonempty object")
    if not isinstance(handoff.get("execution_context"), dict):
        raise AdapterError("handoff execution_context must be an object")
    return handoff, resolved


def init_run(
    workspace: Path, run_id: str, host: str, handoff_path: Path
) -> dict[str, Any]:
    workspace = workspace.resolve()
    path = _state_path(workspace, run_id)
    if path.exists():
        raise AdapterError(f"run already exists: {run_id}")
    handoff, resolved_handoff = _load_handoff(workspace, handoff_path)
    state: dict[str, Any] = {
        "schema": SCHEMA,
        "host": host,
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
        "verified": False,
        "artifact_sha256": None,
        "failure_reason": None,
        "started_at": None,
        "submitted_at": None,
        "reviewed_at": None,
        "reviewed_by": None,
        "review_note": None,
        "checked_anchors": [],
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
        state["tasks"][dependency]["status"] == "completed"
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
    task["worker_id"] = (
        _identifier(worker_id, "worker id") if worker_id is not None else None
    )
    task["verified"] = False
    task["failure_reason"] = None
    task["started_at"] = _now()
    task["submitted_at"] = None
    task["reviewed_at"] = None
    task["reviewed_by"] = None
    task["review_note"] = None
    task["checked_anchors"] = []
    _save_state(workspace, state)
    return task


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
    observations = _require_list(
        pack.get("observations"), "observations", nonempty=True
    )
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
        _require_string(
            observation.get("applicability"), f"observation {index} applicability"
        )
        if observation.get("confidence") not in ("low", "medium", "high"):
            raise AdapterError(
                f"Finding Pack observation {index} confidence is invalid"
            )
        _require_string(
            observation.get("limitation"), f"observation {index} limitation"
        )
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
            _require_string(
                continuation.get(key), f"continuation {index} {key}"
            )
        cost = continuation.get("estimated_cost")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost <= 0:
            raise AdapterError(
                f"Finding Pack continuation {index} estimated_cost must be positive"
            )
    validation_result = pack.get("validation_result")
    if validation_result is not None:
        if not isinstance(validation_result, dict):
            raise AdapterError("Finding Pack validation_result must be an object")
        if validation_result.get("status") not in ("passed", "failed", "inconclusive"):
            raise AdapterError("Finding Pack validation_result status is invalid")
        _require_string(validation_result.get("oracle"), "validation_result oracle")
        _require_string(
            validation_result.get("evidence_ref"), "validation_result evidence_ref"
        )
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
    task["status"] = "submitted"
    task["verified"] = False
    task["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    task["worker_id"] = None
    task["submitted_at"] = _now()
    _save_state(workspace, state)
    return task


def verify_task(
    workspace: Path,
    run_id: str,
    host: str,
    task_id: str,
    reviewer_id: str,
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
    expected_anchors = {
        observation["anchor"]["ref"] for observation in pack["observations"]
    }
    supplied_anchors = {
        _require_string(anchor, "checked anchor") for anchor in checked_anchors
    }
    missing = sorted(expected_anchors - supplied_anchors)
    if missing:
        raise AdapterError("evidence review is missing anchors: " + ", ".join(missing))
    task["status"] = "completed"
    task["verified"] = True
    task["reviewed_by"] = _identifier(reviewer_id, "reviewer id")
    task["review_note"] = _require_string(review_note, "review note")
    task["checked_anchors"] = sorted(supplied_anchors)
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
            invalid_dependencies = [
                dependency for dependency in task["dependencies"] if dependency in reasons
            ]
            if invalid_dependencies:
                reasons[task_id] = (
                    "dependency reopened: " + ", ".join(sorted(invalid_dependencies))
                )
                changed = True

    for task_id in reasons:
        task = state["tasks"][task_id]
        task["status"] = "unknown"
        task["worker_id"] = None
        task["verified"] = False
        task["artifact_sha256"] = None
        task["failure_reason"] = reasons[task_id]
        task["submitted_at"] = None
        task["reviewed_at"] = None
        task["reviewed_by"] = None
        task["review_note"] = None
        task["checked_anchors"] = []
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
        if task["status"] in ("pending", "failed", "unknown") and _dependencies_complete(
            state, task
        ):
            ready.append(task_id)
        integrity_error = _artifact_integrity_error(task)
        if integrity_error is not None:
            integrity_errors.append(f"{task_id}: {integrity_error}")
    complete = bool(state["tasks"]) and counts["completed"] == len(state["tasks"])
    complete = complete and not integrity_errors
    return {
        "run_id": run_id,
        "host": host,
        "status": state["status"],
        "revision": state["revision"],
        "counts": counts,
        "ready": sorted(ready),
        "complete": complete,
        "integrity_errors": integrity_errors,
        "recovery_required": [
            error.split(":", 1)[0] for error in integrity_errors
        ],
    }


def _verify_report(
    workspace: Path,
    path: Path,
    kind: str,
    minimum_bytes: int,
    minimum_headings: int,
) -> dict[str, Any]:
    resolved = _inside(workspace, path, f"{kind} path")
    raw = resolved.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AdapterError(f"{kind} must be UTF-8 without BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdapterError(f"{kind} must be UTF-8") from exc
    headings = len(re.findall(r"(?m)^#{1,6}\s+\S", text))
    if len(raw) < minimum_bytes or headings < minimum_headings:
        raise AdapterError(
            f"{kind} is too shallow; requires at least {minimum_bytes} bytes and "
            f"{minimum_headings} headings"
        )
    return {
        "status": "verified",
        "kind": kind,
        "path": str(resolved),
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
    if not summary["complete"]:
        raise AdapterError("run cannot complete while tasks or integrity checks remain")
    state = _load_state(workspace, run_id, host)
    state["deliverables"] = {
        "technical_research_package": _verify_report(
            workspace, technical_report, "technical_research_package", 1024, 3
        ),
        "human_research_report": _verify_report(
            workspace, human_report, "human_research_report", 512, 2
        ),
    }
    state["status"] = "complete"
    _save_state(workspace, state)
    return status(workspace, run_id, host)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=HOSTS, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--run-id", required=True)
    init_parser.add_argument(
        "--handoff", type=Path, required=True,
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

    finish_parser = subparsers.add_parser("finish")
    finish_parser.add_argument("--run-id", required=True)
    finish_parser.add_argument("--task-id", required=True)
    finish_parser.add_argument("--result", choices=("submitted", "failed"), required=True)
    finish_parser.add_argument("--reason")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--run-id", required=True)
    verify_parser.add_argument("--task-id", required=True)
    verify_parser.add_argument("--reviewer-id", required=True)
    verify_parser.add_argument("--review-note", required=True)
    verify_parser.add_argument("--checked-anchor", action="append", default=[])

    recover_parser = subparsers.add_parser("recover")
    recover_parser.add_argument("--run-id", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--run-id", required=True)

    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("--run-id", required=True)
    complete_parser.add_argument("--technical-report", type=Path, required=True)
    complete_parser.add_argument("--human-report", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate-finding")
    validate_parser.add_argument("path", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    workspace = args.workspace.resolve()
    try:
        if args.command == "init":
            handoff = args.handoff if args.handoff.is_absolute() else workspace / args.handoff
            result = init_run(workspace, args.run_id, args.host, handoff)
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
            result = start_task(
                workspace, args.run_id, args.host, args.task_id, args.worker_id
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
            result = verify_task(
                workspace,
                args.run_id,
                args.host,
                args.task_id,
                args.reviewer_id,
                args.review_note,
                args.checked_anchor,
            )
        elif args.command == "recover":
            result = recover(workspace, args.run_id, args.host)
        elif args.command == "status":
            result = status(workspace, args.run_id, args.host)
        elif args.command == "complete":
            technical = args.technical_report if args.technical_report.is_absolute() else workspace / args.technical_report
            human = args.human_report if args.human_report.is_absolute() else workspace / args.human_report
            result = complete_run(workspace, args.run_id, args.host, technical, human)
        else:
            result = validate_finding(args.path.resolve())
    except (AdapterError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
