#!/usr/bin/env python3
"""Translate Hermes execution observations without owning research state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
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
    from research_tree.context_ledger import ContextBudget, ContextLedgerError, ContextReadLedger
except ImportError:
    from context_ledger_contract import ContextBudget, ContextLedgerError, ContextReadLedger

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


def _run_dir(workspace: Path, run_id: str) -> Path:
    candidates = tuple((workspace / ".research-tree" / "projects").glob(f"*/runs/{run_id}"))
    if len(candidates) != 1:
        raise HermesExecutionError("run must resolve to exactly one project workspace")
    return _inside(workspace, candidates[0], "run directory")


def _context_budget(args: argparse.Namespace) -> ContextBudget | None:
    values = {
        "max_fresh_input_tokens": getattr(args, "max_fresh_input_tokens", None),
        "max_cached_input_tokens": getattr(args, "max_cached_input_tokens", None),
        "max_replayed_input_tokens": getattr(args, "max_replayed_input_tokens", None),
        "max_tool_output_tokens": getattr(args, "max_tool_output_tokens", None),
        "max_process_output_tokens": getattr(args, "max_process_output_tokens", None),
        "max_duplicate_read_ratio": getattr(args, "max_duplicate_read_ratio", None),
    }
    budget = ContextBudget(**values)
    return None if budget.is_unbounded else budget


def _context_ledger(workspace: Path, args: argparse.Namespace) -> ContextReadLedger:
    return ContextReadLedger(workspace, _run_dir(workspace, args.run_id), args.run_id, budget=_context_budget(args))


def _add_context_budget_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-fresh-input-tokens", type=int)
    parser.add_argument("--max-cached-input-tokens", type=int)
    parser.add_argument("--max-replayed-input-tokens", type=int)
    parser.add_argument("--max-tool-output-tokens", type=int)
    parser.add_argument("--max-process-output-tokens", type=int)
    parser.add_argument("--max-duplicate-read-ratio", type=float)


def _read_json(workspace: Path, path: Path, label: str) -> dict[str, Any]:
    resolved = _inside(workspace, path if path.is_absolute() else workspace / path, label)
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HermesExecutionError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise HermesExecutionError(f"{label} must be an object")
    return value


def _load_handoff(workspace: Path, path: Path) -> tuple[dict[str, Any], Path]:
    handoff = _read_json(workspace, path, "alignment handoff")
    if handoff.get("schema") != 1 or handoff.get("kind") != "alignment-handoff":
        raise HermesExecutionError("handoff must be a schema-1 alignment-handoff artifact")
    alignment_digest = handoff.get("alignment_digest")
    compiled_digest = handoff.get("compiled_graph_digest")
    if not all(
        isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
        for digest in (alignment_digest, compiled_digest)
    ):
        raise HermesExecutionError("handoff must include alignment confirmation digests")
    if alignment_digest != compiled_digest:
        raise HermesExecutionError("handoff has a stale alignment confirmation")
    resolved = _inside(workspace, path if path.is_absolute() else workspace / path, "handoff")
    return handoff, resolved


def _observed_delegation_ids(workspace: Path, run_id: str) -> set[str]:
    """Return delegation identities the project hook stream actually observed."""

    events_root = workspace / ".research-tree" / "projects"
    observed: set[str] = set()
    for hook_file in sorted(events_root.glob(f"*/runs/{run_id}/events/*.json")):
        try:
            record = json.loads(hook_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("source") != "research-tree-hermes-hook":
            continue
        if record.get("tool_name") not in (None, "delegate_task"):
            continue
        delegation_id = record.get("delegation_id")
        if isinstance(delegation_id, str) and delegation_id:
            observed.add(delegation_id)
    return observed


def _validated_finding(workspace: Path, path: Path) -> tuple[str, str]:
    """Return (relative path, sha256) for one intact object Finding Pack."""

    resolved = _inside(workspace, path if path.is_absolute() else workspace / path, "Finding Pack path")
    try:
        raw = resolved.read_bytes()
    except OSError as error:
        raise HermesExecutionError(f"finding pack is unreadable: {error}") from error
    if not raw:
        raise HermesExecutionError("finding pack is empty")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HermesExecutionError(f"finding pack is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise HermesExecutionError("finding pack must be an object")
    return resolved.relative_to(workspace).as_posix(), hashlib.sha256(raw).hexdigest()


def initialize_projection(workspace: Path, project_id: str, run_id: str, handoff_path: Path) -> dict[str, Any]:
    handoff, resolved = _load_handoff(workspace, handoff_path)
    try:
        project_workspace = initialize_project_run(workspace, project_id=project_id, run_id=run_id, host="hermes")
        installation = install_project_hooks(workspace, project_workspace)
        hook_probe = probe_lifecycle_hook(project_workspace, launcher=Path(installation["launcher"]))
    except ProjectWorkspaceError as error:
        raise HermesExecutionError(str(error)) from error
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
    finding_digests: list[str] | None = None,
    attempt_id: str | None = None,
) -> dict[str, Any]:
    if not delegation_ids:
        raise HermesExecutionError("record-batch requires at least one observed delegation identity")
    observed = _observed_delegation_ids(workspace, run_id)
    for delegation_id in delegation_ids:
        if delegation_id not in observed:
            raise HermesExecutionError(
                f"delegation identity {delegation_id!r} was not observed by the project hook stream"
            )
    findings = [_validated_finding(workspace, path) for path in finding_paths]
    if finding_digests is not None:
        if len(finding_digests) != len(findings):
            raise HermesExecutionError("declared finding digests must match the finding count")
        for declared, (_, actual) in zip(finding_digests, findings, strict=False):
            if declared != actual:
                raise HermesExecutionError(f"finding pack digest mismatch: declared {declared}")
    if attempt_id is not None:
        for relative, _ in findings:
            body = json.loads((workspace / relative).read_text(encoding="utf-8"))
            declared_attempt = body.get("attempt_id")
            if declared_attempt is not None and declared_attempt != attempt_id:
                raise HermesExecutionError(
                    f"finding pack {relative!r} attempt ancestry {declared_attempt!r} "
                    f"does not match batch attempt {attempt_id!r}"
                )
    return {
        "run_id": run_id,
        "batch_id": batch_id,
        "batch_status": status,
        "delegation_ids": list(delegation_ids),
        "finding_paths": [relative for relative, _ in findings],
        "finding_digests": [digest for _, digest in findings],
        "status": "observed",
        "authoritative": False,
        "completion_authority": "coordinator_only",
    }


def completion_observation(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "delivery_pending",
        "complete": False,
        "observed_complete": False,
        "completion_authority": "coordinator_only",
        "authoritative": False,
    }


def _observed_children(workspace: Path, run_id: str) -> list[dict[str, Any]]:
    """Return observed hook records that carry a bindable child identity."""

    events_root = workspace / ".research-tree" / "projects"
    observed: list[dict[str, Any]] = []
    for hook_file in sorted(events_root.glob(f"*/runs/{run_id}/events/*.json")):
        try:
            record = json.loads(hook_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("source") != "research-tree-hermes-hook":
            continue
        child_id = record.get("agent_id") or record.get("child_subagent_id") or record.get("child_id")
        if not isinstance(child_id, str) or not child_id:
            continue
        observed.append({**record, "child_id": child_id})
    return observed


def run_delegation(workspace: Path, run_id: str, wave_path: Path) -> dict[str, Any]:
    """Bind observed delegation children to canonical attempts and build events."""

    wave = _read_json(workspace, wave_path, "delegation wave")
    if wave.get("schema") != 1 or wave.get("kind") != "delegation-wave":
        raise HermesExecutionError("wave must be a schema-1 delegation-wave artifact")
    attempts = wave.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise HermesExecutionError("wave must declare at least one attempt")

    observed = _observed_children(workspace, run_id)
    retry_of_by_attempt = {
        str(item.get("attempt_id")): item.get("retry_of") for item in attempts if item.get("retry_of")
    }
    pending: list[dict[str, Any]] = [
        item for item in attempts if str(item.get("attempt_id")) not in retry_of_by_attempt
    ]
    if len(observed) != len(pending):
        raise HermesExecutionError(
            f"observed hook stream has {len(observed)} children for {len(pending)} attempts; "
            "identities must come from the real host surface and surplus observations "
            "must not rebind across waves"
        )

    bindings: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    used_children: set[str] = set()
    for attempt, observation in zip(pending, observed, strict=False):
        child_id = observation["child_id"]
        if child_id in used_children:
            raise HermesExecutionError(f"child identity {child_id!r} cannot bind to a second attempt")
        used_children.add(child_id)
        attempt_id = str(attempt["attempt_id"])
        bindings.append(
            {
                "attempt_id": attempt_id,
                "action_id": attempt.get("action_id"),
                "child_id": child_id,
                "delegation_id": observation.get("delegation_id"),
                "task_id": observation.get("task_id"),
            }
        )
        status = observation.get("status")
        events.append(
            build_hermes_event(
                event_id=f"{attempt['event_id_prefix']}-start",
                kind="attempt_started",
                run_id=run_id,
                attempt_id=attempt_id,
                expected_revision=attempt["expected_revision"],
                sequence=attempt["next_sequence"],
                action_id=attempt.get("action_id"),
                created_at=attempt["created_at"],
                payload={},
            )
        )
        if status == "completed":
            events.append(
                build_hermes_event(
                    event_id=f"{attempt['event_id_prefix']}-finish",
                    kind="worker_finished",
                    run_id=run_id,
                    attempt_id=attempt_id,
                    expected_revision=attempt["expected_revision"],
                    sequence=attempt["next_sequence"] + 1,
                    action_id=attempt.get("action_id"),
                    created_at=attempt["created_at"],
                    payload={"outcome": "completed"},
                )
            )
        else:
            # Only an explicitly observed "completed" status may finish a
            # worker; every other status (interrupted, cancelled, failed,
            # error, timeout, or absent) is an unresolved outcome.
            events.append(
                build_hermes_event(
                    event_id=f"{attempt['event_id_prefix']}-unknown",
                    kind="unknown_outcome",
                    run_id=run_id,
                    attempt_id=attempt_id,
                    expected_revision=attempt["expected_revision"],
                    sequence=attempt["next_sequence"] + 1,
                    action_id=attempt.get("action_id"),
                    created_at=attempt["created_at"],
                    payload={"reason": "interrupted_child" if status == "interrupted" else "unresolved_status"},
                )
            )

    for item in attempts:
        attempt_id = str(item.get("attempt_id"))
        retry_of = retry_of_by_attempt.get(attempt_id)
        if retry_of is None:
            continue
        events.append(
            build_hermes_event(
                event_id=f"{item['event_id_prefix']}-retry",
                kind="retry",
                run_id=run_id,
                attempt_id=attempt_id,
                expected_revision=item["expected_revision"],
                sequence=item["next_sequence"],
                action_id=item.get("action_id"),
                created_at=item["created_at"],
                payload={"retry_of": retry_of, "category": "transient", "action_id": item.get("action_id")},
            )
        )

    return {
        "run_id": run_id,
        "bindings": bindings,
        "events": events,
        "status": "observed",
        "authoritative": False,
        "completion_authority": "coordinator_only",
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
    batch.add_argument("--finding-digest", action="append", default=[])
    batch.add_argument("--attempt-id")

    recover = commands.add_parser("recover")
    recover.add_argument("--run-id", required=True)
    recover.add_argument("--canonical-attempt", type=Path)
    recover.add_argument("--unknown-event-id")
    recover.add_argument("--retry-event-id")
    recover.add_argument("--retry-category")
    recover.add_argument("--method")
    recover.add_argument("--created-at")

    delegation = commands.add_parser("run-delegation")
    delegation.add_argument("--run-id", required=True)
    delegation.add_argument("--wave", type=Path, required=True)

    status = commands.add_parser("status")
    status.add_argument("--run-id", required=True)

    context_record = commands.add_parser("context-record")
    context_record.add_argument("--run-id", required=True)
    context_record.add_argument("--source", type=Path, required=True)
    context_record.add_argument("--consumer", required=True)
    context_record.add_argument("--phase", required=True)
    context_record.add_argument("--byte-start", type=int, default=0)
    context_record.add_argument("--byte-end", type=int)
    context_record.add_argument("--input-tokens", type=int, default=0)
    context_record.add_argument("--tool-output-tokens", type=int, default=0)
    context_record.add_argument("--process-output-tokens", type=int, default=0)
    _add_context_budget_arguments(context_record)

    context_seal = commands.add_parser("context-seal")
    context_seal.add_argument("--run-id", required=True)
    context_seal.add_argument("--source", type=Path, required=True)

    context_receipt = commands.add_parser("context-receipt")
    context_receipt.add_argument("--run-id", required=True)

    context_resume = commands.add_parser("context-resume")
    context_resume.add_argument("--run-id", required=True)
    _add_context_budget_arguments(context_resume)

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
    exit_code = 0
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
        elif args.command == "context-record":
            result = _context_ledger(workspace, args).record_read(
                args.source,
                consumer=args.consumer,
                phase=args.phase,
                byte_start=args.byte_start,
                byte_end=args.byte_end,
                input_tokens=args.input_tokens,
                tool_output_tokens=args.tool_output_tokens,
                process_output_tokens=args.process_output_tokens,
            )
            if result["status"] == "budget_exceeded":
                exit_code = 4
        elif args.command == "context-seal":
            result = _context_ledger(workspace, args).seal_source(args.source)
        elif args.command == "context-receipt":
            result = _context_ledger(workspace, args).receipt()
        elif args.command == "context-resume":
            result = _context_ledger(workspace, args).resume(_context_budget(args))
        elif args.command == "record-batch":
            result = batch_observation(
                workspace,
                args.run_id,
                args.batch_id,
                args.status,
                args.delegation_id,
                args.finding,
                finding_digests=args.finding_digest or None,
                attempt_id=args.attempt_id,
            )
        elif args.command == "run-delegation":
            result = run_delegation(workspace, args.run_id, args.wave)
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
    except (
        ContextLedgerError,
        HermesEventError,
        HermesExecutionError,
        WorkflowContractError,
        TypeError,
        ValueError,
    ) as error:
        print(str(error))
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
