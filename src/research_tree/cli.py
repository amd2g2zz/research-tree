"""Stable, host-neutral lifecycle commands for governed research runs."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .alignment_graph import AlignmentGraphError, AlignmentGraphStore, database_path
from .alignment_handoff import goal_decomposition, initialize_research_from_alignment

# isort: split
from .alignment_handoff import ALIGNMENT_HANDOFF_KIND
from .completion_inputs import CompletionInputRegistrar
from .coordinator import (
    RESEARCH_RUN_STATE_KIND,
    CompletionBlockedError,
    CoordinatorConflictError,
    CoordinatorError,
    IllegalTransitionError,
    ResearchRunCoordinator,
    StaleStateError,
)
from .decision_frame import DECISION_FRAME_KIND, DecisionFrame, IntentHypothesis
from .decision_map import BLUEPRINT_TARGET_KIND, BlueprintTargetError, CanonicalBlueprintTargetCompiler
from .delivery import compile_operating_model, render_operating_model
from .domain import ArtifactRef, ArtifactRevision, RuntimeStoreError
from .intake import CanonicalInputIntakeService
from .intent import WORKING_BRIEF_KIND, CanonicalIntentModelCompiler, CanonicalWorkingBriefCompiler
from .origins import close_tag, open_tag
from .project_workspace import (
    ProjectWorkspaceError,
    initialize_project_run,
    install_project_hooks,
    probe_lifecycle_hook,
    resume_project_run,
)
from .run_ledger import LedgerConflictError, LedgerError, RunLedger
from .skill_setup import SkillSetupError, install_skill, plan_heterogeneous_install, skill_status
from .strategy_projection import (
    STRATEGY_PROJECTION_KIND,
    StrategyProjection,
    StrategyProjectionError,
    authority_fingerprint,
    validate_falsifiability,
)
from .tree_state import RESEARCH_TREE_STATE_KIND

LIFECYCLE_SCHEMA_VERSION = 1
HOSTS = ("codex", "claude", "hermes")
LIFECYCLE_REQUEST_KIND = "lifecycle-request"
LIFECYCLE_RESUME_KIND = "lifecycle-resume"
log = logging.getLogger(__name__)


class CliInputError(ValueError):
    """Raised when a stable CLI input cannot be parsed safely."""

    def __init__(self, message: str, *, diagnostic: str | None = None) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-tree",
        description="Stable, host-neutral lifecycle commands; the canonical coordinator retains completion authority.",
        epilog="Commands: install, doctor, run, initialize, resume, status, strategy, operating-model, verify.",
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

    initialize = commands.add_parser(
        "initialize",
        help=(
            "bind the compiled alignment handoff to a blueprint target and initialize the run; "
            "on a late-stage failure re-run with the same idempotency key to resume"
        ),
    )
    _add_workspace(initialize)
    _add_run_identity(initialize, required=True)
    initialize.add_argument("--brief", type=Path, help="operator document compiling the intent model and Working Brief")
    initialize.add_argument("--blueprint", type=Path, help="operator document compiling the Blueprint Target")
    initialize.add_argument("--frame", type=Path, help="operator document persisting the decision frame")
    initialize.add_argument("--idempotency-key")

    operating_model = commands.add_parser(
        "operating-model",
        help="render the Human Brief operating model: roles, SLA, concurrency, blockers, fallback",
    )
    _add_workspace(operating_model)
    _add_run_identity(operating_model, required=True)
    operating_model.add_argument("--json", action="store_true", help="emit the canonical payload instead of markdown")

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

    strategy = commands.add_parser(
        "strategy",
        help="project the goal onto slots and drive draft, display, and confirmation",
    )
    _add_workspace(strategy)
    strategy.add_argument("--project-id", required=True)
    strategy.add_argument("--run-id", required=True)
    strategy_verbs = strategy.add_subparsers(dest="strategy_verb", required=True)
    propose = strategy_verbs.add_parser("propose", help="persist a reviewed strategy projection draft")
    propose.add_argument("--projection", required=True, type=Path)
    propose.add_argument(
        "--alignment-verification",
        type=Path,
        help="independent subagent alignment verification document (registered before display)",
    )
    strategy_verbs.add_parser("display", help="display the projection after falsifiability review")
    confirm = strategy_verbs.add_parser(
        "confirm",
        help="confirm the displayed projection with the digest-bearing human authorization",
    )
    confirm.add_argument("--confirmation", required=True)

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
    """Issue #325: read canonical state; do NOT hard-code a fake failure list.

    Surfaces the real failure reasons reported by the coordinator
    (``why_not_complete``) plus static project-workspace checks.  Returns
    a real ``ready`` boolean; the per-field reason list is constructed
    from canonical evidence, not a constant.
    """

    run_root = _project_run_root(workspace, arguments.project_id, arguments.run_id)
    manifest_path = run_root / "manifest.json"
    artifacts = _lifecycle_artifacts(ledger, arguments.run_id)
    request = next((artifact for artifact in artifacts if artifact.kind == LIFECYCLE_REQUEST_KIND), None)
    request_payload: dict[str, Any] = dict(request.payload) if request is not None else {}
    event_directory = run_root / "events"
    observed_events = len(tuple(event_directory.glob("*.json"))) if event_directory.is_dir() else 0
    failures: list[str] = []
    if not manifest_path.is_file():
        failures.append("project_workspace_missing")
    if request is None:
        failures.append("lifecycle_request_missing")
    # Issue #325 acceptance: alignment/authority/success-oracle/reviewer-receipts
    # are the four canonical obligations for a fresh run.  A real coordinator
    # exposes the same names; surface them when the corresponding artifacts
    # are not present in the run.
    authority_required = request is None or "authority_binding" not in dict(request_payload)
    if authority_required:
        failures.append("authority_binding_required")
    if request is not None and "alignment_confirmation" not in dict(request_payload):
        failures.append("alignment_confirmation_required")
    if request is not None and not dict(request_payload).get("success_oracle"):
        failures.append("success_oracle_evidence_required")
    if request is not None and not dict(request_payload).get("reviewer_receipt"):
        failures.append("independent_reviewer_receipt_required")
    # Plus dynamic canonical reasons (replaces the static list when present)
    try:
        coordinator = ResearchRunCoordinator(ledger)
        why = coordinator.why_not_complete(arguments.run_id)
    except (CoordinatorError, RuntimeStoreError, LedgerError, OSError) as error:
        # Issue #382: a broad ``except Exception`` here would reproduce the
        # retired ``verification_pending`` shortcut that issue #325 was supposed
        # to retire.  Narrow to the canonical error classes and surface a
        # deterministic ``readiness_canonical_unreachable`` reason so the
        # failure is observable; anything else still propagates.
        log.warning(
            "runtime_readiness_canonical_unreachable: %s",
            error,
            extra={"run_id": arguments.run_id, "error": str(error)},
        )
        why = None
        failures.append("readiness_canonical_unreachable")
    if isinstance(why, Mapping):
        for obligation in why.get("unmet_obligations", ()) or ():
            if obligation not in failures:
                failures.append(obligation)
    ready = not failures
    result = {
        "request": request_payload,
        "lifecycle_artifact_count": len(artifacts),
        "observed_hook_event_count": observed_events,
        "canonical_unmet_obligations": [
            o
            for o in failures
            if o
            not in {
                "project_workspace_missing",
                "lifecycle_request_missing",
                "authority_binding_required",
                "alignment_confirmation_required",
                "success_oracle_evidence_required",
                "independent_reviewer_receipt_required",
            }
        ],
    }
    return {"ready": ready, "failure_reasons": failures}, result


def _user_facing_installation(item: Mapping[str, Any]) -> dict[str, Any]:
    """Issue #292 gate 4: keep the operator surface user-readable.

    The ``skill_setup`` API retains digest verification and hook bookkeeping
    internally; the lifecycle CLI echoes only the operator-facing fields so
    ordinary users never see internal schema detail (payload digests, hook
    config paths, activation placeholders, or the packaged-file manifest).
    """

    fields = ("host", "scope", "mode", "target", "action", "status", "reason", "discovery")
    return {field: item[field] for field in fields if item.get(field) is not None}


def _install(arguments: argparse.Namespace) -> dict[str, Any]:
    """Issue #386: dispatch through plan_heterogeneous_install per entry action.

    Replaces the retired ``install_skill`` + ``skill_status`` path so the
    ``plan_heterogeneous_install`` planner has at least one upstream
    caller (issue #328 acceptance).  Per-entry dispatch:
        install  → install_skill([host], ...) then mark status="current"
        current  → no-op confirmation (status="current")
        skipped  → preserve required_config snippet, no install_skill call
        conflict → SkillSetupError failure envelope
    """

    hosts = _selected_hosts(arguments.host)
    plan = plan_heterogeneous_install(
        hosts=hosts,
        source=arguments.source,
        scope=arguments.scope,
        home=arguments.home,
        project_root=arguments.project_root,
        codex_home=arguments.codex_home,
        dry_run=arguments.dry_run,
    )

    installations: list[dict[str, Any]] = []
    skipped_required_config: list[dict[str, Any]] = []
    for entry in plan["entries"]:
        action = entry["action"]
        host = entry["host"]
        if action == "install":
            sub = install_skill(
                (host,),
                source=arguments.source,
                scope=arguments.scope,
                mode=arguments.mode,
                home=arguments.home,
                project_root=arguments.project_root,
                codex_home=arguments.codex_home,
                dry_run=arguments.dry_run,
            )
            for installed in sub.get("installations", []):
                installations.append(
                    {
                        **_user_facing_installation(installed),
                        "status": "current" if not arguments.dry_run else "planned",
                        "current": not arguments.dry_run,
                    }
                )
        elif action == "current":
            installations.append(
                {
                    **_user_facing_installation(entry),
                    "status": "current",
                    "current": True,
                }
            )
        elif action == "skipped":
            skipped_required_config.append(
                {
                    "host": host,
                    "required_config": entry.get("required_config"),
                    "reason": entry.get("reason"),
                }
            )
        elif action == "conflict":
            raise SkillSetupError(f"install_conflict: {host}={entry.get('reason', 'conflict')}")
        else:  # pragma: no cover - defensive
            raise SkillSetupError(f"install_unknown_action: {host}={action}")

    # Issue #386: skipped hosts are not ready (no native target) — surface them in readiness.
    readiness = _heterogeneous_readiness(installations, skipped_required_config)
    plan_payload = {
        "scope": plan.get("scope"),
        "mode": plan.get("mode"),
        "dry_run": plan.get("dry_run"),
        "aggregate_ready": plan.get("aggregate_ready"),
        "snippet_required": plan.get("snippet_required"),
        "snippet": plan.get("snippet"),
        "installations": installations,
        "skipped_required_config": skipped_required_config,
    }
    status = "installed" if plan.get("aggregate_ready") else "partial"
    return _stable_payload("install", status=status, readiness=readiness, result=plan_payload)


def _heterogeneous_readiness(
    installations: Sequence[Mapping[str, Any]],
    skipped: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Issue #386: readiness combines installation status + skipped hosts.

    Skipped hosts have no native target and cannot become current without an
    external config snippet; treat them as a readiness failure so callers can
    see that the install was partial, not silent.
    """

    failures = [
        "skill_installation_not_current:" + str(item["host"])
        for item in installations
        if item.get("status") != "current"
    ]
    failures.extend("skill_installation_skipped:" + str(item["host"]) for item in skipped)
    return {"ready": not failures, "failure_reasons": failures}


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
    # Issue #325: 4-section doctor split — installation / host_capability / run_readiness / completion_verification
    result = {
        **result,
        "installations": [_user_facing_installation(item) for item in result["installations"]],
        "installation": {
            "hosts": {
                host: {"state": "unknown", "reason": "doctor probes on demand"}
                for host in _selected_hosts(arguments.host)
            },
            "state": "ready" if readiness["ready"] else "attention_required",
        },
        "host_capability": provider_readiness,
        "run_readiness": {"ready": readiness["ready"], "reasons": readiness["failure_reasons"]},
        "completion_verification": {"state": "unknown", "note": "verify with --run-id for canonical status"},
    }
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
            "hook_probe": {"status": hook_probe.status},
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
            "hook_probe": {"status": hook_probe.status},
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
    """Issue #325: validate canonical completion receipt; field-level reasons on failure."""

    payload = _status(arguments)
    payload["command"] = "verify"
    ledger = RunLedger(arguments.workspace.expanduser().resolve())
    revision = ledger.get_revision(arguments.run_id)
    receipt_status = _validate_canonical_receipt(ledger, arguments.run_id, revision)
    payload["status"] = receipt_status["status"]
    payload["result"] = {**payload["result"], "verification": receipt_status["details"]}
    return payload


def _validate_canonical_receipt(ledger: RunLedger, run_id: str, revision: int) -> dict[str, Any]:
    """Read coordinator.why_not_complete and classify the verification state.

    Returns a ``status`` ("verified" | "verification_pending" with reasons
    | "verification_failed" with field-level reasons) and a ``details`` dict
    suitable for the verify payload.
    """

    try:
        coordinator = ResearchRunCoordinator(ledger)
        why = coordinator.why_not_complete(run_id)
    except (StaleStateError, CoordinatorConflictError, LedgerConflictError) as error:
        # Issue #382: stale / conflict state is an actionable failure, not
        # a pending verdict.  Classify as ``verification_failed`` so callers
        # re-enter alignment rather than waiting on a verdict that will
        # never resolve on its own.
        return {
            "status": "verification_failed",
            "details": {
                "verdict": "canonical_conflict",
                "reasons": [f"coordinator_conflict: {error}"],
                "package_id": None,
                "host_id": None,
                "revision": revision,
            },
        }
    except (CoordinatorError, RuntimeStoreError, LedgerError, OSError) as error:
        # Transient / store-unavailable: surface as a failed verdict with
        # the underlying error message so the failure exit-code path can
        # retry.  Unexpected exceptions propagate (see ``main``).
        return {
            "status": "verification_failed",
            "details": {
                "verdict": "canonical_unreachable",
                "reasons": [f"coordinator_error: {error}"],
            },
        }
    if not isinstance(why, Mapping):
        return {
            "status": "verification_pending",
            "details": {
                "verdict": "canonical_unavailable",
                "reasons": ["coordinator returned no canonical state"],
            },
        }
    unmet = tuple(why.get("unmet_obligations", ()) or ())
    package_id = why.get("package_id")
    host_id = why.get("host_id")
    if unmet:
        return {
            "status": "verification_pending",
            "details": {
                "verdict": "unmet_obligations",
                "reasons": list(unmet),
                "package_id": package_id,
                "host_id": host_id,
                "revision": revision,
            },
        }
    # All canonical obligations met → verified
    return {
        "status": "verified",
        "details": {
            "verdict": "all_canonical_obligations_met",
            "reasons": [],
            "package_id": package_id,
            "host_id": host_id,
            "revision": revision,
        },
    }


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

    payload = {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "contract": "research-tree-lifecycle",
        "command": "error",
        "code": code,
        "category": category,
        "retryability": retryability,
        "exit_code": exit_code,
        "run_id": run_id,
        "safe_message": code,
        "unmet_obligations": unmet_obligations,
        "evidence_refs": [],
        "next_action": next_action,
    }
    diagnostic = getattr(error, "diagnostic", None)
    if diagnostic:
        payload["diagnostic"] = str(diagnostic)
    return exit_code, payload


def _emit(payload: Mapping[str, Any]) -> None:
    command = str(payload.get("command", "unknown"))
    body = json.dumps(payload, sort_keys=True)
    attributes = {"source": "research-tree-cli", "command": command}
    if isinstance(payload.get("category"), str) and payload["category"] != "success":
        attributes["category"] = str(payload["category"])
        attributes["retryability"] = str(bool(payload.get("retryability"))).lower()
        attributes["exit-code"] = str(payload.get("exit_code", 2))
        print(open_tag("rt:error", attributes) + body + close_tag("rt:error"))
        return
    run = payload.get("run") if isinstance(payload.get("run"), Mapping) else {}
    revision = run.get("authority_revision")
    if revision is not None:
        attributes["rev"] = str(revision)
    print(open_tag("rt:tool-output", attributes) + body + close_tag("rt:tool-output"))


def _latest_kind(artifacts: Sequence[ArtifactRevision], kind: str) -> ArtifactRevision | None:
    """Resolve the latest revision of one artifact kind, or None."""

    candidates = [item for item in artifacts if item.kind == kind]
    return max(candidates, key=lambda item: item.revision) if candidates else None


def _compile_working_brief(ledger: RunLedger, run_id: str, document: Mapping[str, Any]) -> ArtifactRevision:
    """Compile the intent model and Working Brief from one operator document (#470)."""

    inputs = tuple(document.get("inputs", ()))
    intake = CanonicalInputIntakeService(ledger)
    for entry in inputs:
        intake.ingest_text(
            round_id=run_id,
            input_id=str(entry["id"]),
            kind=str(entry["kind"]),
            content=str(entry["content"]),
            origin_type=str(entry["origin_type"]),
            origin_locator=str(entry["origin_locator"]),
            role=str(entry.get("role", "signal")),
            expected_revision=ledger.get_revision(run_id),
        )
    model = CanonicalIntentModelCompiler(ledger).compile(
        round_id=run_id,
        intent_id=str(document["intent_id"]),
        context_bundle_ids=tuple(document.get("context_bundle_ids", ())),
        input_ids=[str(entry["id"]) for entry in inputs],
        analysis=dict(document["analysis"]),
        expected_revision=ledger.get_revision(run_id),
    )
    return CanonicalWorkingBriefCompiler(ledger).compile(
        round_id=run_id,
        brief_id=str(document["brief_id"]),
        intent_model=model,
        triggers=tuple(document.get("triggers", ())),
        context_bundle_ids=tuple(document.get("context_bundle_ids", ())),
        selected_input_ids=tuple(document["selected_input_ids"]),
        input_roles=dict(document["input_roles"]),
        material_conflicts=tuple(document.get("material_conflicts", ())),
        working_interpretation=str(document["working_interpretation"]),
        technical_outcome=str(document["technical_outcome"]),
        assumptions=tuple(document.get("assumptions", ())),
        expected_revision=ledger.get_revision(run_id),
    )


def _persist_frame(
    coordinator: ResearchRunCoordinator,
    ledger: RunLedger,
    run_id: str,
    frame_path: Path,
    target: ArtifactRevision,
) -> dict[str, Any]:
    """Persist the decision frame document bound to the compiled blueprint target.

    Idempotent on frame_id: an identical retry resolves the stored frame and
    appends nothing, so repeated initialize runs stay byte-identical (HIGH-2).
    """

    document = dict(_read_json_object(frame_path))
    frame_id = str(document.get("frame_id", ""))
    stored_frames = [
        item for item in ledger.load_run(run_id).artifacts if item.kind == DECISION_FRAME_KIND and item.id == frame_id
    ]
    if stored_frames:
        stored = max(stored_frames, key=lambda item: item.revision)
        return ArtifactRef(run_id, stored.id, stored.revision).to_dict()
    document["hypotheses"] = [IntentHypothesis.from_dict(item) for item in document.get("hypotheses", ())]
    document["target_ref"] = ArtifactRef(run_id, target.id, target.revision)
    try:
        frame = DecisionFrame.create(**document)
    except (TypeError, ValueError) as error:
        raise CliInputError(f"decision_frame_invalid: {error}") from error
    stored = coordinator.persist_decision_frame(frame, expected_revision=ledger.get_revision(run_id))
    return ArtifactRef(run_id, stored.id, stored.revision).to_dict()


def _initialize(arguments: argparse.Namespace) -> dict[str, Any]:
    """Bridge a prepared run to an initialized run-state through the canonical chain (#470)."""

    workspace = arguments.workspace.expanduser().resolve()
    ledger = RunLedger(workspace)
    run_id = arguments.run_id
    snapshot = ledger.load_run(run_id)
    handoff = _latest_kind(snapshot.artifacts, ALIGNMENT_HANDOFF_KIND)
    if handoff is None:
        try:
            initialize_research_from_alignment(
                ledger,
                round_id=run_id,
                tree_id=f"tree-{run_id}",
                alignment_database=database_path(workspace, run_id, arguments.project_id),
                expected_revision=ledger.get_revision(run_id),
            )
        except AlignmentGraphError as error:
            raise CoordinatorConflictError("alignment_not_confirmed") from error
        snapshot = ledger.load_run(run_id)
        handoff = _latest_kind(snapshot.artifacts, ALIGNMENT_HANDOFF_KIND)
    # Stored lineage wins (HIGH-2): once the run carries a blueprint target, retries
    # resolve brief/target/frame from stored artifacts and never re-ingest or
    # re-compile, so N identical retries leave the ledger byte-identical.
    artifacts = snapshot.artifacts
    target = _latest_kind(artifacts, BLUEPRINT_TARGET_KIND)
    if target is None:
        brief = _latest_kind(artifacts, WORKING_BRIEF_KIND)
        if brief is None:
            if arguments.brief is None:
                raise CoordinatorConflictError("working_brief_missing")
            brief = _compile_working_brief(ledger, run_id, _read_json_object(arguments.brief))
        if arguments.blueprint is None:
            raise CoordinatorConflictError("blueprint_target_missing")
        document = _read_json_object(arguments.blueprint)
        try:
            target = CanonicalBlueprintTargetCompiler(ledger).compile(
                round_id=run_id,
                target_id=str(document["target_id"]),
                working_brief=brief,
                slots=tuple(document["slots"]),
                change=dict(document["change"]),
                expected_revision=ledger.get_revision(run_id),
                alignment_handoff=handoff,
            )
        except BlueprintTargetError as error:
            # An invariant-sentence input failure is invalid_input, never store_unavailable.
            raise CliInputError("blueprint_target_invalid", diagnostic=str(error)) from error
    else:
        brief = _latest_kind(artifacts, WORKING_BRIEF_KIND)
        if brief is None:
            raise CoordinatorConflictError("working_brief_missing")
        if ArtifactRef(run_id, handoff.id, handoff.revision) not in target.parent_refs:
            raise CoordinatorConflictError("blueprint_target_handoff_lineage")
    coordinator = ResearchRunCoordinator(ledger)
    try:
        state = coordinator.initialize(
            run_id=run_id,
            alignment_handoff=handoff,
            blueprint_target=target,
            expected_revision=ledger.get_revision(run_id),
            idempotency_key=arguments.idempotency_key,
        )
    except CoordinatorConflictError as error:
        raise _stable_conflict(error) from error
    frame_ref = None
    if arguments.frame is not None:
        frame_ref = _persist_frame(coordinator, ledger, run_id, arguments.frame, target)
    return _stable_payload(
        "initialize",
        status="initialized",
        run={
            "project_id": arguments.project_id,
            "run_id": run_id,
            "authority_revision": ledger.get_revision(run_id),
        },
        result={
            "state": state.payload.get("state"),
            "handoff_ref": ArtifactRef(run_id, handoff.id, handoff.revision).to_dict(),
            "target_ref": ArtifactRef(run_id, target.id, target.revision).to_dict(),
            "frame_ref": frame_ref,
        },
    )


def _stable_conflict(error: CoordinatorConflictError) -> CoordinatorConflictError:
    """Map coordinator invariant sentences to stable snake_case codes (M6)."""

    mapped = {
        "run is already initialized": "run_already_initialized",
        "blueprint-target lineage does not include alignment-handoff": "blueprint_target_handoff_lineage",
    }.get(str(error))
    if mapped is None:
        return error
    wrapped = CoordinatorConflictError(mapped)
    wrapped.diagnostic = str(error)
    return wrapped


def _operating_model(arguments: argparse.Namespace) -> str | dict[str, Any]:
    """Render the canonical operating model for operator reading (#470)."""

    workspace = arguments.workspace.expanduser().resolve()
    ledger = RunLedger(workspace)
    snapshot = ledger.load_run(arguments.run_id)
    model = compile_operating_model(arguments.run_id, snapshot.artifacts, ledger)
    states = [item for item in snapshot.artifacts if item.kind == RESEARCH_RUN_STATE_KIND]
    state = max(states, key=lambda item: item.revision).payload.get("state") if states else None
    if arguments.json:
        return _stable_payload(
            "operating-model",
            status=str(state) if state else "prepared",
            run={
                "project_id": arguments.project_id,
                "run_id": arguments.run_id,
                "authority_revision": ledger.get_revision(arguments.run_id),
            },
            readiness={"ready": bool(state), "failure_reasons": [] if state else ["run_not_initialized"]},
            result={"operating_model": model},
        )
    markdown = render_operating_model(model)
    attributes = {"source": "research-tree-cli", "command": "operating-model"}
    if state is not None:
        attributes["state"] = str(state)
    return open_tag("rt:tool-output", attributes) + markdown + close_tag("rt:tool-output")


def _projection_from_document(document: Mapping[str, Any]) -> StrategyProjection:
    """Accept a serialized projection or a base document the product completes (#470)."""

    try:
        if "display_payload" in document:
            return StrategyProjection.from_dict(document)
        values = dict(document)
        for name in ("decision_frame_ref", "alignment_handoff_ref", "target_ref"):
            values[name] = ArtifactRef.from_dict(values[name])
        return StrategyProjection.create(**values)
    except (StrategyProjectionError, TypeError, KeyError, ValueError) as error:
        raise CliInputError("strategy_projection_invalid") from error


def _latest_strategy_projection(ledger: RunLedger, run_id: str) -> ArtifactRevision:
    """Resolve the current strategy-projection revision for the run."""

    candidates = [item for item in ledger.load_run(run_id).artifacts if item.kind == STRATEGY_PROJECTION_KIND]
    if not candidates:
        raise CoordinatorConflictError("strategy_projection_missing")
    return max(candidates, key=lambda item: item.revision)


def _strategy(arguments: argparse.Namespace) -> dict[str, Any]:
    """Dispatch strategy lifecycle verbs onto the authoritative coordinator API."""

    workspace = arguments.workspace.expanduser().resolve()
    ledger = RunLedger(workspace)
    coordinator = ResearchRunCoordinator(ledger)
    if arguments.strategy_verb == "propose":
        return _strategy_propose(coordinator, ledger, arguments)
    if arguments.strategy_verb == "display":
        return _strategy_display(coordinator, ledger, arguments)
    if arguments.strategy_verb == "confirm":
        return _strategy_confirm(coordinator, ledger, arguments)
    raise CliInputError("unsupported_strategy_verb")


def _strategy_propose(
    coordinator: ResearchRunCoordinator,
    ledger: RunLedger,
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    """Persist a reviewed projection draft through coordinator.persist_strategy_projection."""

    proposal = _projection_from_document(_read_json_object(arguments.projection))
    if proposal.run_id != arguments.run_id:
        raise CliInputError("strategy_projection_cross_run")
    # The verification document must name its own id; that gate runs before any
    # write. Registration itself must follow the projection persist because the
    # ledger enforces parent existence, so a registration failure discloses the
    # stored projection ref in the failure payload (review M4).
    alignment_verification = None
    if arguments.alignment_verification is not None:
        alignment_verification = dict(_read_json_object(arguments.alignment_verification))
        if not str(alignment_verification.get("id") or "").strip():
            raise CliInputError("alignment_verification_id_required")
    stored = coordinator.persist_strategy_projection(proposal, expected_revision=ledger.get_revision(arguments.run_id))
    if alignment_verification is not None:
        alignment_verification["projection_ref"] = ArtifactRef(
            arguments.run_id, stored.projection_id, stored.revision
        ).to_dict()
        alignment_verification["authority_fingerprint"] = authority_fingerprint(proposal)
        try:
            CompletionInputRegistrar(ledger).write_alignment_verification(
                round_id=arguments.run_id,
                verification_id=str(alignment_verification.get("id")),
                payload=alignment_verification,
                expected_revision=ledger.get_revision(arguments.run_id),
            )
        except (RuntimeStoreError, CoordinatorError, ValueError) as error:
            raise CliInputError(
                "alignment_verification_not_registered",
                diagnostic=(
                    f"the projection draft is stored at {ArtifactRef(arguments.run_id, stored.projection_id, stored.revision).to_dict()}; "
                    f"registration failed: {error}"
                ),
            ) from error
    return _stable_payload(
        f"strategy.{arguments.strategy_verb}",
        status="proposed",
        run={"project_id": arguments.project_id, "run_id": arguments.run_id, "authority_revision": None},
        result={
            "projection_ref": ArtifactRef(arguments.run_id, stored.projection_id, stored.revision).to_dict(),
            "status": stored.status,
        },
    )


def _strategy_display(
    coordinator: ResearchRunCoordinator,
    ledger: RunLedger,
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    """Review the draft, commit the displayed revision, and advance the run state."""

    run_id = arguments.run_id
    latest = _latest_strategy_projection(ledger, run_id)
    artifact, projection = coordinator.require_strategy_projection(
        ArtifactRef(run_id, latest.id, latest.revision),
        run_id=run_id,
    )
    # Pre-flight the falsifiability review before committing the displayed revision so a
    # rejected display leaves no appended artifact behind. The coordinator's
    # display_strategy re-enforces the same gate at the authority layer for every caller.
    try:
        validate_falsifiability(projection)
    except StrategyProjectionError as error:
        raise CoordinatorConflictError(str(error)) from error
    # Issue #462: pre-flight the independent-verification gate for the same reason —
    # the draft must already carry an independent subagent alignment verification
    # (bound by authority fingerprint) before the display revision is appended.
    coordinator.require_independent_alignment_verification(run_id, projection)
    if projection.status == "draft":
        values = projection.to_dict()
        for derived in ("schema_version", "kind", "display_payload", "display_digest", "content_hash"):
            values.pop(derived)
        values["status"] = "displayed"
        values["revision"] = projection.revision + 1
        values["decision_frame_ref"] = projection.decision_frame_ref
        values["alignment_handoff_ref"] = projection.alignment_handoff_ref
        values["target_ref"] = projection.target_ref
        revised = StrategyProjection.create(**values)
        ledger.append_strategy_projection(
            run_id,
            revised.projection_id,
            revised.to_dict(),
            parent_refs=(
                ArtifactRef(run_id, artifact.id, artifact.revision),
                revised.decision_frame_ref,
                revised.alignment_handoff_ref,
                revised.target_ref,
            ),
            expected_revision=ledger.get_revision(run_id),
        )
        projection = revised
        artifact = _latest_strategy_projection(ledger, run_id)
    coordinator.display_strategy(
        run_id,
        projection,
        expected_revision=ledger.get_revision(run_id),
    )
    return _stable_payload(
        f"strategy.{arguments.strategy_verb}",
        status="displayed",
        run={"project_id": arguments.project_id, "run_id": run_id, "authority_revision": None},
        result={
            "projection_ref": ArtifactRef(run_id, artifact.id, artifact.revision).to_dict(),
            "display_digest": projection.display_digest,
            "goal_decomposition": list(goal_decomposition(ledger.load_run(run_id).artifacts)),
        },
    )


def _strategy_confirm(
    coordinator: ResearchRunCoordinator,
    ledger: RunLedger,
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    """Confirm the displayed projection with the human's digest-bearing authorization."""

    run_id = arguments.run_id
    workspace = arguments.workspace.expanduser().resolve()
    database = database_path(workspace, run_id, arguments.project_id)
    try:
        AlignmentGraphStore(database).compile_handoff()
    except AlignmentGraphError as error:
        raise CoordinatorConflictError("alignment_not_confirmed") from error
    latest = _latest_strategy_projection(ledger, run_id)
    # Issue #292 gate 1: the operator confirms the displayed digest; the CLI
    # embeds the recomputed authority fingerprint so the confirmation carries
    # a field-level binding that the coordinator guard can re-verify. The
    # generic-acknowledgement guard must still see the operator's words, so
    # it is checked before the fingerprint is appended.
    if arguments.confirmation.strip().lower() in {"ok", "okay", "yes", "continue", "go ahead", "proceed"}:
        raise CliInputError("generic_confirmation")
    projection = StrategyProjection.from_dict(latest.payload)
    confirmation = f"{arguments.confirmation} authority-fingerprint {authority_fingerprint(projection)}"
    confirmed_state = coordinator.confirm_handoff(
        run_id,
        projection_ref=ArtifactRef(run_id, latest.id, latest.revision),
        confirmation=confirmation,
        expected_revision=ledger.get_revision(run_id),
        actor="human",
    )
    trees = [item for item in ledger.load_run(run_id).artifacts if item.kind == RESEARCH_TREE_STATE_KIND]
    tree_ref = None
    if not trees:
        created = initialize_research_from_alignment(
            ledger,
            round_id=run_id,
            tree_id=f"tree-{run_id}",
            alignment_database=database,
            expected_revision=ledger.get_revision(run_id),
        )
        tree_ref = ArtifactRef(run_id, created.id, created.revision).to_dict()
    return _stable_payload(
        "strategy.confirm",
        status="confirmed",
        run={"project_id": arguments.project_id, "run_id": run_id, "authority_revision": ledger.get_revision(run_id)},
        result={
            "projection_ref": ArtifactRef(run_id, latest.id, latest.revision).to_dict(),
            "display_digest": confirmed_state.payload.get("strategy_display_digest"),
            "state": confirmed_state.payload.get("state"),
            "tree_ref": tree_ref,
        },
    )


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
        if arguments.command == "initialize":
            _emit(_initialize(arguments))
            return 0
        if arguments.command == "operating-model":
            payload = _operating_model(arguments)
            if isinstance(payload, str):
                print(payload)
            else:
                _emit(payload)
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
        if arguments.command == "strategy":
            payload = _strategy(arguments)
            _emit(payload)
            return 0
        resolved_run_id, result = _internal_run(arguments)
    except (
        CliInputError,
        CoordinatorError,
        AlignmentGraphError,
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
