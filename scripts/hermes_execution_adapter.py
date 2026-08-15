#!/usr/bin/env python3
"""Translate Hermes execution observations without owning research state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from hermes_event_adapter import (
    HermesEventError,
    build_hermes_event,
    project_hermes_action,
    recovery_events,
)

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


class HermesExecutionError(ValueError):
    """Raised when a compatibility command has invalid bounded input."""


def _inside(workspace: Path, candidate: Path, label: str) -> Path:
    root = workspace.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise HermesExecutionError(f"{label} must remain in the workspace") from error
    return resolved


def _read_json(workspace: Path, path: Path, label: str) -> dict[str, Any]:
    resolved = _inside(workspace, path if path.is_absolute() else workspace / path, label)
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HermesExecutionError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise HermesExecutionError(f"{label} must be an object")
    return value


def _relative_paths(workspace: Path, paths: list[Path]) -> list[str]:
    return [
        _inside(workspace, path if path.is_absolute() else workspace / path, "Finding Pack path")
        .relative_to(workspace)
        .as_posix()
        for path in paths
    ]


def initialize_projection(workspace: Path, project_id: str, run_id: str, handoff_path: Path) -> dict[str, Any]:
    try:
        project_workspace = initialize_project_run(
            workspace, project_id=project_id, run_id=run_id, host="hermes"
        )
        installation = install_project_hooks(workspace, project_workspace)
        hook_probe = probe_lifecycle_hook(project_workspace, launcher=Path(installation["launcher"]))
    except ProjectWorkspaceError as error:
        raise HermesExecutionError(str(error)) from error
    handoff = _read_json(workspace, handoff_path, "alignment handoff")
    if handoff.get("schema") != 1 or handoff.get("kind") != "alignment-handoff":
        raise HermesExecutionError("handoff must be a schema-1 alignment-handoff artifact")
    resolved = _inside(workspace, handoff_path if handoff_path.is_absolute() else workspace / handoff_path, "handoff")
    return {
        "run_id": run_id,
        "project_id": project_workspace.project_id,
        "project_run_root": str(project_workspace.run_root),
        "lifecycle_hooks": hook_probe.status,
        "status": "observed",
        "authoritative": False,
        "completion_authority": "coordinator_only",
        "handoff_path": resolved.relative_to(workspace).as_posix(),
        "handoff_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "alignment_run_id": handoff.get("run_id"),
    }


def batch_observation(
    workspace: Path,
    run_id: str,
    batch_id: str,
    status: str,
    delegation_ids: list[str],
    finding_paths: list[Path],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "batch_id": batch_id,
        "batch_status": status,
        "delegation_ids": list(delegation_ids),
        "finding_paths": _relative_paths(workspace, finding_paths),
        "status": "observed",
        "authoritative": False,
        "completion_authority": "coordinator_only",
    }


def completion_observation(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "delivery_pending",
        "complete": False,
        "observed_complete": True,
        "completion_authority": "coordinator_only",
        "authoritative": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--project-id", required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--handoff", type=Path, required=True)

    batch = commands.add_parser("record-batch")
    batch.add_argument("--run-id", required=True)
    batch.add_argument("--batch-id", required=True)
    batch.add_argument("--status", required=True)
    batch.add_argument("--delegation-id", action="append", default=[])
    batch.add_argument("--finding", type=Path, action="append", default=[])

    recover = commands.add_parser("recover")
    recover.add_argument("--run-id", required=True)
    recover.add_argument("--canonical-attempt", type=Path)
    recover.add_argument("--unknown-event-id")
    recover.add_argument("--retry-event-id")
    recover.add_argument("--retry-category")
    recover.add_argument("--method")
    recover.add_argument("--created-at")

    status = commands.add_parser("status")
    status.add_argument("--run-id", required=True)

    complete = commands.add_parser("complete")
    complete.add_argument("--run-id", required=True)
    complete.add_argument("--technical-report", type=Path, required=True)
    complete.add_argument("--human-report", type=Path, required=True)

    emit = commands.add_parser("emit-event")
    emit.add_argument("--event-id", required=True)
    emit.add_argument("--kind", required=True)
    emit.add_argument("--run-id", required=True)
    emit.add_argument("--attempt-id", required=True)
    emit.add_argument("--expected-revision", type=int, required=True)
    emit.add_argument("--sequence", type=int, required=True)
    emit.add_argument("--causation-id")
    emit.add_argument("--action-id")
    emit.add_argument("--decision-slot-id")
    emit.add_argument("--created-at", required=True)
    emit.add_argument("--payload", type=Path, required=True)

    project = commands.add_parser("project-action")
    project.add_argument("--action", type=Path, required=True)

    probe = commands.add_parser("probe-host")
    probe.add_argument("--observations", type=Path, required=True)

    workflow = commands.add_parser("project-workflow")
    workflow.add_argument("--request", type=Path, required=True)

    reconcile = commands.add_parser("reconcile-host")
    reconcile.add_argument("--request", type=Path, required=True)

    replan = commands.add_parser("replan-workflow")
    replan.add_argument("--request", type=Path, required=True)

    resume = commands.add_parser("resume-workflow")
    resume.add_argument("--request", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    workspace = args.workspace.resolve()
    try:
        if args.command == "probe-host":
            result = probe_host("hermes", _read_json(workspace, args.observations, "capability observations"))
        elif args.command == "project-workflow":
            result = project_workflow(_read_json(workspace, args.request, "workflow projection request"), "hermes")
        elif args.command == "reconcile-host":
            result = reconcile_workflow(
                _read_json(workspace, args.request, "workflow reconciliation request"), "hermes"
            )
        elif args.command == "replan-workflow":
            result = replan_workflow(_read_json(workspace, args.request, "workflow replan request"), "hermes")
        elif args.command == "resume-workflow":
            result = resume_workflow(_read_json(workspace, args.request, "workflow resume request"), "hermes")
        elif args.command == "init":
            result = initialize_projection(workspace, args.project_id, args.run_id, args.handoff)
        elif args.command == "record-batch":
            result = batch_observation(
                workspace, args.run_id, args.batch_id, args.status, args.delegation_id, args.finding
            )
        elif args.command == "recover":
            if args.canonical_attempt is None:
                raise HermesExecutionError("canonical attempt snapshot is required")
            snapshot = _read_json(workspace, args.canonical_attempt, "canonical attempt")
            if snapshot.get("run_id") != args.run_id:
                raise HermesExecutionError("canonical attempt run_id mismatch")
            events = recovery_events(
                run_id=args.run_id,
                action_id=snapshot.get("action_id"),
                attempt_id=snapshot.get("attempt_id"),
                expected_revision=snapshot.get("expected_revision"),
                next_sequence=snapshot.get("next_sequence"),
                unknown_event_id=args.unknown_event_id,
                retry_event_id=args.retry_event_id,
                retry_category=args.retry_category,
                method=args.method,
                authorized_methods=set(snapshot.get("authorized_methods", [])),
                created_at=args.created_at,
            )
            result = {"events": events, "authoritative": False}
        elif args.command == "complete":
            result = completion_observation(args.run_id)
        elif args.command == "emit-event":
            result = build_hermes_event(
                event_id=args.event_id,
                kind=args.kind,
                run_id=args.run_id,
                attempt_id=args.attempt_id,
                expected_revision=args.expected_revision,
                sequence=args.sequence,
                causation_id=args.causation_id,
                action_id=args.action_id,
                decision_slot_id=args.decision_slot_id,
                created_at=args.created_at,
                payload=_read_json(workspace, args.payload, "event payload"),
            )
        elif args.command == "project-action":
            result = project_hermes_action(_read_json(workspace, args.action, "canonical action"))
        else:
            raise HermesExecutionError("status requires the canonical coordinator ledger")
    except (HermesEventError, HermesExecutionError, WorkflowContractError, TypeError, ValueError) as error:
        print(str(error))
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
