"""Stable, host-neutral lifecycle commands for governed research runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .coordinator import (
    CompletionBlockedError,
    CoordinatorConflictError,
    CoordinatorError,
    IllegalTransitionError,
    ResearchRunCoordinator,
    StaleStateError,
)
from .domain import ArtifactRef, RuntimeStoreError
from .project_workspace import (
    ProjectWorkspaceError,
    initialize_project_run,
    install_project_hooks,
    probe_lifecycle_hook,
    resume_project_run,
)
from .run_ledger import LedgerConflictError, LedgerError, RunLedger
from .skill_setup import SkillSetupError, install_skill, skill_status

LIFECYCLE_SCHEMA_VERSION = 1
HOSTS = ("codex", "claude", "hermes")
LIFECYCLE_REQUEST_KIND = "lifecycle-request"
LIFECYCLE_RESUME_KIND = "lifecycle-resume"


class CliInputError(ValueError):
    """Raised when a stable CLI input cannot be parsed safely."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-tree",
        description="Stable, host-neutral lifecycle commands; the canonical coordinator retains completion authority.",
        epilog="Commands: install, doctor, run, resume, status, verify.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    install = commands.add_parser("install", help="install one or more host skill packages")
    _add_host_selection(install)
    _add_install_location(install)
    install.add_argument("--mode", choices=("link", "copy"), default="link")
    install.add_argument("--dry-run", action="store_true")

    doctor = commands.add_parser("doctor", help="check install state and lifecycle readiness")
    _add_host_selection(doctor)
    _add_install_location(doctor)
    doctor.add_argument("--workspace", type=Path, default=Path.cwd())
    _add_run_identity(doctor, required=False)

    run = commands.add_parser("run", help="create a durable, non-authoritative governed run")
    _add_workspace(run)
    _add_single_host(run)
    _add_run_identity(run, required=True)
    run.add_argument("--outcome", required=True, help="plain-language intended research outcome")
    run.add_argument("--scope", required=True, help="plain-language in-scope boundary")
    run.add_argument("--authority", required=True, help="plain-language authorization boundary")
    run.add_argument("--success-oracle", required=True, help="plain-language completion evidence rule")

    resume = commands.add_parser("resume", help="resume a durable governed run without widening authority")
    _add_workspace(resume)
    _add_single_host(resume)
    _add_run_identity(resume, required=True)

    status = commands.add_parser("status", help="report canonical revision and readiness failures")
    _add_workspace(status)
    _add_single_host(status)
    _add_run_identity(status, required=True)

    verify = commands.add_parser("verify", help="report whether the run has independent completion evidence")
    _add_workspace(verify)
    _add_single_host(verify)
    _add_run_identity(verify, required=True)

    return parser


def _internal_parser() -> argparse.ArgumentParser:
    internal = argparse.ArgumentParser(prog="research-tree internal")
    internal.add_argument("--acknowledge-internal-contract", action="store_true", required=True)
    internal_commands = internal.add_subparsers(dest="internal_command", required=True)
    coordinator = internal_commands.add_parser("coordinator", help=argparse.SUPPRESS)
    coordinator.add_argument("--workspace", required=True, type=Path)
    verbs = coordinator.add_subparsers(dest="verb", required=True)

    ingest = verbs.add_parser("ingest", help=argparse.SUPPRESS)
    ingest.add_argument("--event", required=True, type=Path)

    recover = verbs.add_parser("recover", help=argparse.SUPPRESS)
    recover.add_argument("--run-id", required=True)

    why_not_complete = verbs.add_parser("why-not-complete", help=argparse.SUPPRESS)
    why_not_complete.add_argument("--run-id", required=True)

    complete = verbs.add_parser("complete", help=argparse.SUPPRESS)
    complete.add_argument("--run-id", required=True)
    complete.add_argument("--actor", required=True)
    complete.add_argument("--expected-revision", required=True, type=int)
    return internal


def _add_host_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", choices=(*HOSTS, "all"), action="append", required=True)


def _add_single_host(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", choices=HOSTS, required=True)


def _add_install_location(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", required=True, type=Path, help="checkout containing generated host packages")
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--codex-home", type=Path)


def _add_workspace(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True, type=Path, help="normal writable project directory")


def _add_run_identity(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument("--project-id", required=required)
    parser.add_argument("--run-id", required=required)


def _read_json_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CliInputError("event_json_invalid") from error
    if not isinstance(value, Mapping):
        raise CliInputError("event_json_object_required")
    return value


def _selected_hosts(raw_hosts: Sequence[str]) -> tuple[str, ...]:
    return HOSTS if "all" in raw_hosts else tuple(dict.fromkeys(raw_hosts))


def _stable_payload(
    command: str,
    *,
    status: str,
    run: Mapping[str, Any] | None = None,
    readiness: Mapping[str, Any] | None = None,
    result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    run_payload = {"authority_revision": None, **dict(run or {})}
    return {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "contract": "research-tree-lifecycle",
        "command": command,
        "status": status,
        "run": run_payload,
        "readiness": dict(readiness or {"ready": False, "failure_reasons": []}),
        "completion_authority": "human_and_canonical_coordinator",
        "result": dict(result or {}),
    }


def _installation_readiness(installations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failures = [
        "skill_installation_not_current:" + str(item["host"])
        for item in installations
        if item.get("status") != "current"
    ]
    return {"ready": not failures, "failure_reasons": failures}


def _run_identity(arguments: argparse.Namespace, revision: int) -> dict[str, Any]:
    return {
        "project_id": arguments.project_id,
        "run_id": arguments.run_id,
        "host": arguments.host,
        "authority_revision": revision,
    }


def _project_run_root(workspace: Path, project_id: str, run_id: str) -> Path:
    return workspace / ".research-tree" / "projects" / project_id / "runs" / run_id


def _lifecycle_artifacts(ledger: RunLedger, run_id: str) -> list[Any]:
    return [
        artifact
        for artifact in ledger.load_run(run_id).artifacts
        if artifact.kind in {LIFECYCLE_REQUEST_KIND, LIFECYCLE_RESUME_KIND}
    ]


def _runtime_readiness(
    workspace: Path, arguments: argparse.Namespace, ledger: RunLedger
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_root = _project_run_root(workspace, arguments.project_id, arguments.run_id)
    manifest_path = run_root / "manifest.json"
    artifacts = _lifecycle_artifacts(ledger, arguments.run_id)
    failures = [
        "alignment_confirmation_required",
        "authority_binding_required",
        "success_oracle_evidence_required",
        "independent_reviewer_receipt_required",
    ]
    if not manifest_path.is_file():
        failures.insert(0, "project_workspace_missing")
    request = next((artifact for artifact in artifacts if artifact.kind == LIFECYCLE_REQUEST_KIND), None)
    if request is None:
        failures.insert(0, "lifecycle_request_missing")
        request_payload: dict[str, Any] = {}
    else:
        request_payload = dict(request.payload)
    event_directory = run_root / "events"
    observed_events = len(tuple(event_directory.glob("*.json"))) if event_directory.is_dir() else 0
    result = {
        "request": request_payload,
        "lifecycle_artifact_count": len(artifacts),
        "observed_hook_event_count": observed_events,
    }
    return {"ready": False, "failure_reasons": failures}, result


def _install(arguments: argparse.Namespace) -> dict[str, Any]:
    result = install_skill(
        _selected_hosts(arguments.host),
        source=arguments.source,
        scope=arguments.scope,
        mode=arguments.mode,
        home=arguments.home,
        project_root=arguments.project_root,
        codex_home=arguments.codex_home,
        dry_run=arguments.dry_run,
    )
    status_result = skill_status(
        _selected_hosts(arguments.host),
        source=arguments.source,
        scope=arguments.scope,
        home=arguments.home,
        project_root=arguments.project_root,
        codex_home=arguments.codex_home,
    )
    statuses = {str(item["host"]): item for item in status_result["installations"]}
    installations = [{**item, **statuses[str(item["host"])]} for item in result["installations"]]
    result = {**result, "installations": installations}
    readiness = _installation_readiness(installations)
    return _stable_payload(
        "install", status="installed" if readiness["ready"] else "planned", readiness=readiness, result=result
    )


def _doctor(arguments: argparse.Namespace) -> dict[str, Any]:
    result = skill_status(
        _selected_hosts(arguments.host),
        source=arguments.source,
        scope=arguments.scope,
        home=arguments.home,
        project_root=arguments.project_root,
        codex_home=arguments.codex_home,
    )
    readiness = _installation_readiness(result["installations"])
    run: dict[str, Any] = {}
    if arguments.project_id is not None or arguments.run_id is not None:
        if not arguments.project_id or not arguments.run_id:
            raise CliInputError("project_id_and_run_id_required_together")
        workspace = arguments.workspace.resolve()
        ledger = RunLedger(workspace)
        revision = ledger.get_revision(arguments.run_id)
        run = {
            "project_id": arguments.project_id,
            "run_id": arguments.run_id,
            "authority_revision": revision,
        }
        lifecycle_readiness, lifecycle_result = _runtime_readiness(workspace, arguments, ledger)
        readiness = {
            "ready": readiness["ready"] and lifecycle_readiness["ready"],
            "failure_reasons": [*readiness["failure_reasons"], *lifecycle_readiness["failure_reasons"]],
        }
        result = {**result, "lifecycle": lifecycle_result}
    provider_readiness = {
        # issue #326: static installation health and live provider readiness are
        # separate sections.  Provider state is probe-declared ("unknown" when not
        # probed); no credentials or raw gateway logs are ever included.
        "state": "unknown",
        "note": "live provider readiness requires an explicit probe; not evaluated here",
    }
    result = {**result, "provider_readiness": provider_readiness}
    return _stable_payload(
        "doctor",
        status="healthy" if readiness["ready"] else "attention_required",
        run=run,
        readiness=readiness,
        result=result,
    )


def _run_lifecycle(arguments: argparse.Namespace) -> dict[str, Any]:
    workspace = arguments.workspace.expanduser().resolve()
    ledger = RunLedger(workspace)
    ledger.create_run(arguments.run_id)
    request = {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "outcome": arguments.outcome,
        "scope": arguments.scope,
        "authority": arguments.authority,
        "success_oracle": arguments.success_oracle,
        "host": arguments.host,
        "project_id": arguments.project_id,
    }
    request_artifact = ledger.append_artifact(
        arguments.run_id,
        "lifecycle-request",
        LIFECYCLE_REQUEST_KIND,
        request,
        expected_revision=ledger.get_revision(arguments.run_id),
    )
    project_run = initialize_project_run(
        workspace,
        project_id=arguments.project_id,
        run_id=arguments.run_id,
        host=arguments.host,
    )
    installation = install_project_hooks(workspace, project_run)
    hook_probe = probe_lifecycle_hook(project_run, launcher=Path(installation["launcher"]))
    revision = ledger.get_revision(arguments.run_id)
    readiness, runtime = _runtime_readiness(workspace, arguments, ledger)
    return _stable_payload(
        "run",
        status="prepared",
        run=_run_identity(arguments, revision),
        readiness=readiness,
        result={
            "request_ref": {
                "run_id": request_artifact.round_id,
                "artifact_id": request_artifact.id,
                "revision": request_artifact.revision,
            },
            "hook_probe": {
                "status": hook_probe.status,
                "record_path": str(hook_probe.record_path) if hook_probe.record_path else None,
            },
            "lifecycle": runtime,
        },
    )


def _resume(arguments: argparse.Namespace) -> dict[str, Any]:
    workspace = arguments.workspace.expanduser().resolve()
    ledger = RunLedger(workspace)
    artifacts = _lifecycle_artifacts(ledger, arguments.run_id)
    request = next((artifact for artifact in artifacts if artifact.kind == LIFECYCLE_REQUEST_KIND), None)
    if request is None:
        raise CliInputError("lifecycle_request_missing")
    project_run = resume_project_run(
        workspace,
        project_id=arguments.project_id,
        run_id=arguments.run_id,
        host=arguments.host,
    )
    installation = install_project_hooks(workspace, project_run)
    hook_probe = probe_lifecycle_hook(project_run, launcher=Path(installation["launcher"]))
    resumed = ledger.append_artifact(
        arguments.run_id,
        "lifecycle-resume",
        LIFECYCLE_RESUME_KIND,
        {"schema_version": LIFECYCLE_SCHEMA_VERSION, "host": arguments.host, "request_ref": request.id},
        parent_refs=(ArtifactRef(arguments.run_id, request.id, request.revision),),
        expected_revision=ledger.get_revision(arguments.run_id),
    )
    revision = ledger.get_revision(arguments.run_id)
    readiness, runtime = _runtime_readiness(workspace, arguments, ledger)
    return _stable_payload(
        "resume",
        status="resumed",
        run=_run_identity(arguments, revision),
        readiness=readiness,
        result={
            "resume_ref": {"run_id": resumed.round_id, "artifact_id": resumed.id, "revision": resumed.revision},
            "hook_probe": {
                "status": hook_probe.status,
                "record_path": str(hook_probe.record_path) if hook_probe.record_path else None,
            },
            "lifecycle": runtime,
        },
    )


def _status(arguments: argparse.Namespace) -> dict[str, Any]:
    workspace = arguments.workspace.expanduser().resolve()
    ledger = RunLedger(workspace)
    revision = ledger.get_revision(arguments.run_id)
    readiness, result = _runtime_readiness(workspace, arguments, ledger)
    return _stable_payload(
        "status",
        status="blocked" if not readiness["ready"] else "ready",
        run=_run_identity(arguments, revision),
        readiness=readiness,
        result=result,
    )


def _verify(arguments: argparse.Namespace) -> dict[str, Any]:
    payload = _status(arguments)
    payload["command"] = "verify"
    payload["status"] = "verification_pending"
    payload["result"] = {
        **payload["result"],
        "verification": "independent_completion_receipt_absent",
    }
    return payload


def _internal_run(arguments: argparse.Namespace) -> tuple[str | None, Any]:
    if arguments.verb == "ingest":
        event = _read_json_object(arguments.event)
        run_id = event.get("run_id") if isinstance(event.get("run_id"), str) else None
        arguments.run_id = run_id
        result = ResearchRunCoordinator(RunLedger(arguments.workspace)).ingest_host_event(event)
        return run_id, result.to_dict()

    coordinator = ResearchRunCoordinator(RunLedger(arguments.workspace))
    if arguments.verb == "recover":
        return arguments.run_id, coordinator.recover(arguments.run_id)
    if arguments.verb == "why-not-complete":
        return arguments.run_id, coordinator.why_not_complete(arguments.run_id)
    if arguments.verb == "complete":
        result = coordinator.complete(
            arguments.run_id,
            actor=arguments.actor,
            expected_revision=arguments.expected_revision,
        )
        return arguments.run_id, result.to_dict()
    raise CliInputError("unsupported_internal_verb")


def _success(run_id: str | None, result: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": "ok",
        "category": "success",
        "retryability": False,
        "run_id": run_id,
        "safe_message": "ok",
        "unmet_obligations": [],
        "evidence_refs": [],
        "next_action": None,
        "result": result,
    }
    if isinstance(result, Mapping):
        obligations = result.get("unmet_obligations")
        if isinstance(obligations, (list, tuple)):
            payload["unmet_obligations"] = list(obligations)
        actions = result.get("next_actions")
        if isinstance(actions, (list, tuple)) and actions:
            payload["next_action"] = actions[0]
    return payload


def _failure(error: Exception, run_id: str | None) -> tuple[int, dict[str, Any]]:
    code = str(error) or type(error).__name__
    category = "invalid_input"
    retryability = False
    exit_code = 2
    unmet_obligations: list[str] = []
    next_action: str | None = None

    if isinstance(error, CompletionBlockedError):
        code = "completion_blocked"
        category = "blocked"
        exit_code = 4
        unmet_obligations = list(error.unmet_obligations)
        next_action = "resolve:" + unmet_obligations[0] if unmet_obligations else None
    elif isinstance(error, StaleStateError):
        category = "conflict"
        retryability = True
        exit_code = 3
        next_action = error.next_action
    elif isinstance(error, (CoordinatorConflictError, LedgerConflictError)) and code == "stale_revision":
        category = "conflict"
        retryability = True
        exit_code = 3
    elif isinstance(error, IllegalTransitionError):
        category = "terminal"
        exit_code = 10
    elif isinstance(error, (RuntimeStoreError, LedgerError, OSError)) and not isinstance(error, CoordinatorError):
        category = "store_unavailable"
        retryability = True
        exit_code = 9

    return exit_code, {
        "code": code,
        "category": category,
        "retryability": retryability,
        "run_id": run_id,
        "safe_message": code,
        "unmet_obligations": unmet_obligations,
        "evidence_refs": [],
        "next_action": next_action,
    }


def _emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    if raw_arguments[:1] == ["internal"]:
        arguments = _internal_parser().parse_args(raw_arguments[1:])
        arguments.command = "internal"
    else:
        arguments = build_parser().parse_args(raw_arguments)
    try:
        if arguments.command == "install":
            payload = _install(arguments)
            _emit(payload)
            return 0 if payload["readiness"]["ready"] else 4
        if arguments.command == "doctor":
            payload = _doctor(arguments)
            _emit(payload)
            return 0 if payload["readiness"]["ready"] else 4
        if arguments.command == "run":
            _emit(_run_lifecycle(arguments))
            return 0
        if arguments.command == "resume":
            _emit(_resume(arguments))
            return 0
        if arguments.command == "status":
            payload = _status(arguments)
            _emit(payload)
            return 0 if payload["readiness"]["ready"] else 4
        if arguments.command == "verify":
            _emit(_verify(arguments))
            return 4
        resolved_run_id, result = _internal_run(arguments)
    except (
        CliInputError,
        CoordinatorError,
        RuntimeStoreError,
        LedgerError,
        ProjectWorkspaceError,
        SkillSetupError,
        OSError,
    ) as error:
        exit_code, payload = _failure(error, getattr(arguments, "run_id", None))
        _emit(payload)
        return exit_code
    _emit(_success(resolved_run_id, result))
    return 0
