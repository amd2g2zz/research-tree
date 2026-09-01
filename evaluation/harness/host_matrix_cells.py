"""The six gate-7 failure-injection scenario cells.

Each cell is a complete setup -> inject -> observe -> receipt unit against a
real runtime run.  Shared contract and helpers live in ``host_matrix``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from host_matrix import (
    _LAUNCHER_EVENT_NAMES,
    CellResult,
    _append,
    _attempt_outcome,
    _canonical_events,
    _capture_cli,
    _event,
    _false_completion,
    _joined,
    _now,
    _observe,
    _observe_immutable,
    _persisted_events,
    _prepare_run,
)

from research_tree.content_store import ContentAddressedStore, ContentIntegrityError, ContentStoreError
from research_tree.coordinator import CoordinatorConflictError
from research_tree.domain import ArtifactRef
from research_tree.project_workspace import initialize_project_run, install_project_hooks
from research_tree.run_ledger import LedgerIntegrityError, RunLedger


def _scenario_stale_child(host: str, workspace: Path) -> CellResult:
    """Stale child attempts: unknown lease, expired lease, stale revision - all rejected."""

    cell = workspace / "stale_child" / host
    ledger, coordinator, lease, run_id = _prepare_run(cell, host, "stale")
    attempt_id = str(lease.payload["attempt_id"])

    ghost = _event(
        ledger,
        event_id=f"ghost-child-{host}",
        kind="observation",
        run_id=run_id,
        attempt_id=f"attempt-ghost-{host}",
        sequence=1,
        payload={"origin": "worker"},
    )
    unknown_lease, unknown_mutated = _observe_immutable(
        lambda: coordinator.ingest_host_event(ghost),
        ledger,
        run_id,
        token="unknown_attempt",
        marker="unknown_attempt",
        errors=(CoordinatorConflictError,),
    )

    expired_lease = _append(
        ledger,
        run_id,
        attempt_id,
        lease.kind,
        {**dict(lease.payload), "expires_at": "2020-01-01T00:00:00+00:00"},
        (ArtifactRef(run_id, attempt_id, lease.revision),),
    )
    stale_child = _event(
        ledger,
        event_id=f"stale-child-{host}",
        kind="observation",
        run_id=run_id,
        attempt_id=attempt_id,
        sequence=1,
        payload={"origin": "worker"},
    )
    lease_expired, expired_mutated = _observe_immutable(
        lambda: coordinator.ingest_host_event(stale_child),
        ledger,
        run_id,
        token="lease_expired",
        marker="lease_expired",
        errors=(CoordinatorConflictError,),
    )

    stale_revision_event = _event(
        ledger,
        event_id=f"stale-revision-{host}",
        kind="observation",
        run_id=run_id,
        attempt_id=attempt_id,
        sequence=1,
        payload={"origin": "worker"},
        expected_revision=0,
    )
    stale_revision, revision_mutated = _observe_immutable(
        lambda: coordinator.ingest_host_event(stale_revision_event),
        ledger,
        run_id,
        token="stale_revision",
        marker="stale_revision",
        errors=(CoordinatorConflictError,),
    )

    outcomes = [unknown_lease, lease_expired, stale_revision]
    expected = "+".join(item.token for item in outcomes)
    mutated = unknown_mutated or expired_mutated or revision_mutated
    detail = "; ".join(f"{item.token}={item.matched}" for item in outcomes)
    if not all(item.matched for item in outcomes):
        detail += "; messages: " + " | ".join(item.message for item in outcomes if not item.matched)
    return CellResult(
        scenario="stale_child",
        host=host,
        status="passed" if all(item.matched for item in outcomes) and not mutated else "failed",
        injection_transport="host-event-ingestion+lease-revision-supersede",
        cause="runtime-internal",
        host_process_invoked=False,
        expected_reason=expected,
        observed_reason=_joined(outcomes),
        false_completion=_false_completion(ledger, run_id),
        state_mutated=mutated,
        detail=detail,
        events=_canonical_events(ledger, run_id),
        identities=(attempt_id, f"attempt-ghost-{host}"),
        evidence={"expired_lease_revision": expired_lease.revision},
    )


def _scenario_artifact_tamper(host: str, workspace: Path) -> CellResult:
    """Artifact tamper: real CAS byte mutation and a forged checkpoint digest."""

    cell = workspace / "artifact_tamper" / host
    ledger, coordinator, lease, run_id = _prepare_run(cell, host, "tamper")
    attempt_id = str(lease.payload["attempt_id"])
    store = ContentAddressedStore(cell)
    content = store.ingest(f"tamper probe {host}".encode("utf-8"), "text/plain")
    capture = ledger.append_artifact_with_content(
        run_id,
        f"capture-{host}",
        "source-capture",
        {"attempt_id": attempt_id, "status": "committed"},
        content,
        store,
        expected_revision=ledger.get_revision(run_id),
    )

    read_before = store.read(content.digest) == f"tamper probe {host}".encode("utf-8")
    cas_object = cell / ".research-tree" / "cas" / "sha256" / content.digest[:2] / content.digest
    original = bytearray(cas_object.read_bytes())
    original[len(original) // 2] ^= 0x01
    cas_object.write_bytes(bytes(original))
    cas_read = _observe(
        lambda: store.read(content.digest),
        token="cas_digest_mismatch",
        marker="CAS digest mismatch",
        errors=(ContentIntegrityError, ContentStoreError),
    )

    checkpoint = _append(
        ledger,
        run_id,
        f"checkpoint-{host}",
        "analysis-checkpoint",
        {"attempt_id": attempt_id, "status": "committed"},
    )
    forged_payload = {
        "checkpoint_ref": ArtifactRef(run_id, checkpoint.id, checkpoint.revision).to_dict(),
        "checkpoint_digest": "f" * 64,
    }
    forged = _event(
        ledger,
        event_id=f"forged-checkpoint-{host}",
        kind="checkpoint_persisted",
        run_id=run_id,
        attempt_id=attempt_id,
        sequence=1,
        payload=forged_payload,
    )
    forged_digest, forged_mutated = _observe_immutable(
        lambda: coordinator.ingest_host_event(forged),
        ledger,
        run_id,
        token="checkpoint_digest_mismatch",
        marker="checkpoint_digest_mismatch",
        errors=(CoordinatorConflictError,),
    )

    outcomes = [cas_read, forged_digest]
    expected = "+".join(item.token for item in outcomes)
    mutated = forged_mutated
    detail = (
        f"CAS object {content.digest[:12]} tampered mid-byte; read before tamper={read_before}; "
        f"post-tamper read={cas_read.matched}; forged checkpoint rejected={forged_digest.matched}"
    )
    return CellResult(
        scenario="artifact_tamper",
        host=host,
        status="passed" if read_before and all(item.matched for item in outcomes) and not mutated else "failed",
        injection_transport="cas-byte-mutation+host-event-ingestion",
        cause="runtime-internal",
        host_process_invoked=False,
        expected_reason=expected,
        observed_reason=_joined(outcomes),
        false_completion=_false_completion(ledger, run_id),
        state_mutated=mutated,
        detail=detail,
        events=_canonical_events(ledger, run_id),
        identities=(attempt_id,),
        evidence={
            "capture_ref": ArtifactRef(run_id, capture.id, capture.revision).to_dict(),
            "tampered_byte_changed": True,
            "read_before_tamper": read_before,
        },
    )


def _launcher_binding_observation(host: str, workspace: Path, run_id: str) -> dict[str, Any]:
    """Run the real run-bound launcher with the host's event name, no identity.

    An interrupted child that never reports its identity must be recorded as
    ``unknown_outcome``, never as a bound completion.
    """

    project_run = initialize_project_run(workspace, project_id=f"proj-{host}", run_id=run_id, host=host)
    installation = install_project_hooks(workspace, project_run)
    launcher = Path(installation["launcher"])
    event_name = _LAUNCHER_EVENT_NAMES[host]
    payload = {"hook_event_name": event_name}
    completed = subprocess.run(
        [sys.executable, str(launcher)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    records = sorted((project_run.run_root / "events").glob("*.json"))
    record: dict[str, Any] = {}
    if records:
        try:
            record = json.loads(records[-1].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            record = {}
    return {
        "launcher_exit_code": completed.returncode,
        "launcher_event_name": event_name,
        "launcher_recorded": bool(records),
        "launcher_binding_status": record.get("binding_status"),
        "codex_hook_config": Path(installation["codex"]["config"]).is_file(),
        "claude_hook_config": Path(installation["claude"]["config"]).is_file(),
        "hermes_hook_config": Path(installation["hermes"]["config"]).is_file(),
    }


def _scenario_interruption(host: str, workspace: Path) -> CellResult:
    """Interrupted child: runtime records unknown, rejects completion, accepts truth."""

    cell = workspace / "interruption" / host
    ledger, coordinator, lease, run_id = _prepare_run(cell / "runtime", host, "interruption")
    attempt_id = str(lease.payload["attempt_id"])
    launcher_evidence = _launcher_binding_observation(host, cell, run_id)

    outcome = _attempt_outcome(host, attempt_id)
    forged_completion = _event(
        ledger,
        event_id=f"interrupted-completion-{host}",
        kind="worker_finished",
        run_id=run_id,
        attempt_id=attempt_id,
        sequence=1,
        payload={"outcome": "success", "attempt_outcome": outcome["dict"]},
    )
    rejection, rejection_mutated = _observe_immutable(
        lambda: coordinator.ingest_host_event(forged_completion),
        ledger,
        run_id,
        token="attempt_outcome_semantic_failure",
        marker="attempt_outcome_semantic_failure",
        errors=(CoordinatorConflictError,),
    )
    truthful = _event(
        ledger,
        event_id=f"interrupted-unknown-{host}",
        kind="unknown_outcome",
        run_id=run_id,
        attempt_id=attempt_id,
        sequence=1,
        payload={"reason": "interrupted_child"},
    )
    accepted = coordinator.ingest_host_event(truthful)
    mutated = rejection_mutated

    launcher_ok = launcher_evidence["launcher_recorded"] and (
        launcher_evidence["launcher_binding_status"] == ("unknown_outcome" if host != "hermes" else None)
    )
    detail = (
        f"launcher recorded binding_status={launcher_evidence['launcher_binding_status']!r} for "
        f"{launcher_evidence['launcher_event_name']}; forged worker_finished rejected "
        f"({rejection.message[:80]}); truthful unknown_outcome accepted as {accepted.id}"
    )
    if host == "hermes":
        detail += "; launcher_binding not recognized for hermes event name (recorded limitation)"
    return CellResult(
        scenario="interruption",
        host=host,
        status="passed" if rejection.matched and launcher_ok and not mutated else "failed",
        injection_transport="launcher-subprocess+host-event-ingestion",
        cause="synthesized-trigger",
        host_process_invoked=False,
        expected_reason="attempt_outcome_semantic_failure",
        observed_reason=rejection.token if rejection.matched else rejection.message,
        false_completion=_false_completion(ledger, run_id),
        state_mutated=mutated,
        detail=detail,
        events=_canonical_events(ledger, run_id),
        identities=(attempt_id, "attempt-missing-launcher-identity"),
        evidence={**launcher_evidence, "classification": outcome["classification"]},
    )


def _scenario_provider_error(host: str, workspace: Path) -> CellResult:
    """Provider outage: declared via the real provider_failure envelope, never completes."""

    cell = workspace / "provider_error" / host
    ledger, coordinator, lease, run_id = _prepare_run(cell, host, "provider")
    attempt_id = str(lease.payload["attempt_id"])

    failure_payload = {
        "category": "provider_unavailable",
        "provider": f"gateway-{host}",
        "model": f"model-{host}",
        "opaque_code": uuid.uuid4().hex,
        "safe_log_ref": f"logs/{host}/provider-failure.json",
    }
    declared = _event(
        ledger,
        event_id=f"provider-failure-{host}",
        kind="provider_failure",
        run_id=run_id,
        attempt_id=attempt_id,
        sequence=1,
        payload=failure_payload,
    )
    coordinator.ingest_host_event(declared)
    declared_ok = any(kind == "provider_failure" for kind, _attempt in _persisted_events(ledger, run_id))

    outcome = _attempt_outcome(host, attempt_id, provider_disposition="insufficient_balance")
    forged_completion = _event(
        ledger,
        event_id=f"provider-completion-{host}",
        kind="worker_finished",
        run_id=run_id,
        attempt_id=attempt_id,
        sequence=2,
        causation_id=f"provider-failure-{host}",
        payload={"outcome": "success", "attempt_outcome": outcome["dict"]},
    )
    rejection, mutated = _observe_immutable(
        lambda: coordinator.ingest_host_event(forged_completion),
        ledger,
        run_id,
        token="attempt_outcome_semantic_failure",
        marker="attempt_outcome_semantic_failure",
        errors=(CoordinatorConflictError,),
    )
    retry = _event(
        ledger,
        event_id=f"provider-retry-{host}",
        kind="retry",
        run_id=run_id,
        attempt_id=attempt_id,
        sequence=2,
        causation_id=f"provider-failure-{host}",
        payload={"retry_of": attempt_id, "category": "transient"},
    )
    coordinator.ingest_host_event(retry)

    detail = (
        f"provider_failure envelope accepted ({declared_ok}); classification={outcome['classification']}; "
        f"completion claim rejected ({rejection.message[:80]}); retry accepted with new causation"
    )
    return CellResult(
        scenario="provider_error",
        host=host,
        status="passed" if declared_ok and rejection.matched and not mutated else "failed",
        injection_transport="host-event-ingestion",
        cause="synthesized-trigger",
        host_process_invoked=False,
        expected_reason="attempt_outcome_semantic_failure",
        observed_reason=rejection.token if rejection.matched else rejection.message,
        false_completion=_false_completion(ledger, run_id),
        state_mutated=mutated,
        detail=detail,
        events=_canonical_events(ledger, run_id),
        identities=(attempt_id,),
        evidence={"classification": outcome["classification"], "provider_failure_declared": declared_ok},
    )


def _scenario_resume(host: str, workspace: Path) -> CellResult:
    """Resume: real CLI run + resume; resuming an unprepared run fails closed."""

    cell = workspace / "resume" / host
    host_args = ["--workspace", str(cell), "--host", host]
    project_id, run_id = f"proj-{host}", f"run-{host}-resume"
    missing_run = f"run-{host}-resume-missing"
    ledger_probe = RunLedger(cell)
    ledger_probe.initialize()
    ledger_probe.create_run(missing_run)

    blocked_code, blocked_envelope = _capture_cli(
        [*["resume"], *host_args, "--project-id", project_id, "--run-id", missing_run]
    )
    blocked_ok = blocked_code == 2 and blocked_envelope.get("code") == "lifecycle_request_missing"
    blocked_artifacts = [
        item for item in RunLedger(cell).load_run(missing_run).artifacts if item.kind == "lifecycle-resume"
    ]
    mutated = bool(blocked_artifacts)

    run_code, run_envelope = _capture_cli(
        [
            "run",
            *host_args,
            "--project-id",
            project_id,
            "--run-id",
            run_id,
            "--outcome",
            "validated customer decision",
            "--scope",
            "customer validation evidence",
            "--authority",
            "operator-authorized local workspace",
            "--success-oracle",
            "canonical coordinator completion evidence",
        ]
    )
    run_ok = run_code == 0 and run_envelope.get("status") == "prepared"
    request_before = next(
        (item for item in RunLedger(cell).load_run(run_id).artifacts if item.kind == "lifecycle-request"), None
    )
    request_payload_before = dict(request_before.payload) if request_before is not None else {}

    resume_code, resume_envelope = _capture_cli(["resume", *host_args, "--project-id", project_id, "--run-id", run_id])
    resume_ok = resume_code == 0 and resume_envelope.get("status") == "resumed"
    ledger = RunLedger(cell)
    artifacts = ledger.load_run(run_id).artifacts
    resumed = next((item for item in artifacts if item.kind == "lifecycle-resume"), None)
    request_ref = f"{request_before.round_id}/{request_before.id}@{request_before.revision}" if request_before else ""
    resume_parent = (
        f"{resumed.parent_refs[0].round_id}/{resumed.parent_refs[0].artifact_id}@{resumed.parent_refs[0].revision}"
        if resumed and resumed.parent_refs
        else ""
    )
    request_payload_unchanged = (
        dict(next((item for item in artifacts if item.kind == "lifecycle-request")).payload) == request_payload_before
        if request_before is not None
        else False
    )
    manifest_path = cell / ".research-tree" / "projects" / project_id / "runs" / run_id / "manifest.json"
    manifest_hosts = list(json.loads(manifest_path.read_text(encoding="utf-8")).get("hosts", ()))

    detail = (
        f"blocked resume exit={blocked_code} code={blocked_envelope.get('code')}; run exit={run_code} "
        f"status={run_envelope.get('status')}; resume exit={resume_code} status={resume_envelope.get('status')}; "
        f"resume parent binding matched={resume_parent == request_ref}"
    )
    passed = (
        blocked_ok
        and run_ok
        and resume_ok
        and resume_parent == request_ref
        and request_payload_unchanged
        and manifest_hosts == [host]
        and not mutated
    )
    return CellResult(
        scenario="resume",
        host=host,
        status="passed" if passed else "failed",
        injection_transport="cli-subprocess-entrypoint",
        cause="runtime-cli",
        host_process_invoked=False,
        expected_reason="lifecycle_request_missing",
        observed_reason=str(blocked_envelope.get("code")) if blocked_ok else json.dumps(blocked_envelope)[:200],
        false_completion=_false_completion(ledger, run_id),
        state_mutated=mutated,
        detail=detail,
        events=_canonical_events(ledger, run_id),
        identities=(run_id, missing_run),
        evidence={
            "resume_ref": str(resumed.id) if resumed else "",
            "request_ref": request_ref,
            "resume_ref_parent": resume_parent,
            "request_payload_unchanged": request_payload_unchanged,
            "manifest_hosts": manifest_hosts,
            "run_status": run_envelope.get("status"),
            "resume_status": resume_envelope.get("status"),
        },
    )


def _scenario_cross_workspace_isolation(host: str, workspace: Path) -> CellResult:
    """Cross-workspace isolation: foreign refs, path escape, foreign ledger - all rejected."""

    cell = workspace / "cross_workspace_isolation" / host
    ledger_a, coordinator_a, lease_a, run_a = _prepare_run(cell / "ws-a", host, "iso-a")
    ledger_b, _coordinator_b, _lease_b, run_b = _prepare_run(cell / "ws-b", host, "iso-b")
    attempt_a = str(lease_a.payload["attempt_id"])

    store_b = ContentAddressedStore(cell / "ws-b")
    content_b = store_b.ingest(f"cross-workspace capture {host}".encode("utf-8"), "text/plain")
    capture_b = ledger_b.append_artifact_with_content(
        run_b,
        f"capture-{host}",
        "source-capture",
        {"attempt_id": f"attempt-{host}-iso-b", "status": "committed"},
        content_b,
        store_b,
        expected_revision=ledger_b.get_revision(run_b),
    )
    # Locally valid evidence skeleton in run A so the structural completeness
    # checks pass and the per-reference resolution sees the foreign capture.
    capture_a = _append(
        ledger_a, run_a, f"capture-a-{host}", "source-capture", {"attempt_id": attempt_a, "status": "committed"}
    )
    receipt_a = _append(
        ledger_a,
        run_a,
        f"receipt-a-{host}",
        "acquisition-receipt",
        {"attempt_id": attempt_a, "capture_id": capture_a.id, "status": "succeeded"},
        (ArtifactRef(run_a, capture_a.id, capture_a.revision),),
    )
    checkpoint_a = _append(
        ledger_a, run_a, f"checkpoint-a-{host}", "analysis-checkpoint", {"attempt_id": attempt_a, "status": "committed"}
    )
    finding_a = _append(ledger_a, run_a, f"finding-a-{host}", "finding-pack", {"attempt_id": attempt_a})
    produced_a = _append(ledger_a, run_a, f"produced-a-{host}", "analysis-output", {"attempt_id": attempt_a})
    smuggled_payload = {
        "outcome": "completion-claim",
        "capture_refs": [ArtifactRef(run_b, capture_b.id, capture_b.revision).to_dict()],
        "receipt_refs": [ArtifactRef(run_a, receipt_a.id, receipt_a.revision).to_dict()],
        "checkpoint_ref": ArtifactRef(run_a, checkpoint_a.id, checkpoint_a.revision).to_dict(),
        "finding_refs": [ArtifactRef(run_a, finding_a.id, finding_a.revision).to_dict()],
        "produced_artifact_refs": [ArtifactRef(run_a, produced_a.id, produced_a.revision).to_dict()],
    }
    smuggled = _event(
        ledger_a,
        event_id=f"smuggled-{host}",
        kind="worker_finished",
        run_id=run_a,
        attempt_id=attempt_a,
        sequence=1,
        payload=smuggled_payload,
    )
    foreign_ref, foreign_mutated = _observe_immutable(
        lambda: coordinator_a.ingest_host_event(smuggled),
        ledger_a,
        run_a,
        token="capture_reference_invalid",
        marker="capture_reference_invalid",
        errors=(CoordinatorConflictError,),
    )

    escape_payload = {"evidence_refs": ["capture-1"], "report_path": "../../escape.json"}
    # Inject the traversal payload as a raw mapping so the coordinator's
    # ingestion boundary performs normalization and raises the canonical
    # rejection; pre-building the envelope here would short-circuit the runtime.
    escape = {
        "event_id": f"escape-{host}",
        "kind": "submission",
        "run_id": run_a,
        "attempt_id": attempt_a,
        "expected_revision": ledger_a.get_revision(run_a),
        "sequence": 1,
        "actor": "worker",
        "created_at": _now(),
        "payload": escape_payload,
    }
    path_escape, escape_mutated = _observe_immutable(
        lambda: coordinator_a.ingest_host_event(escape),
        ledger_a,
        run_a,
        token="host_path_escape_rejected",
        marker="cannot escape the workspace",
        errors=(CoordinatorConflictError,),
    )

    foreign_run, foreign_run_mutated = _observe_immutable(
        lambda: ledger_b.load_run(run_a),
        ledger_a,
        run_a,
        token="cross_workspace_run_absent",
        marker=f"run does not exist: {run_a}",
        errors=(LedgerIntegrityError,),
    )

    outcomes = [foreign_ref, path_escape, foreign_run]
    expected = "+".join(item.token for item in outcomes)
    mutated = foreign_mutated or escape_mutated or foreign_run_mutated
    detail = "; ".join(f"{item.token}={item.matched}" for item in outcomes)
    if not all(item.matched for item in outcomes):
        detail += "; messages: " + " | ".join(item.message for item in outcomes if not item.matched)
    return CellResult(
        scenario="cross_workspace_isolation",
        host=host,
        status="passed" if all(item.matched for item in outcomes) and not mutated else "failed",
        injection_transport="cross-run-reference+payload-path+ledger-probe",
        cause="runtime-internal",
        host_process_invoked=False,
        expected_reason=expected,
        observed_reason=_joined(outcomes),
        false_completion=_false_completion(ledger_a, run_a),
        state_mutated=mutated,
        detail=detail,
        events=_canonical_events(ledger_a, run_a),
        identities=(attempt_a,),
        evidence={
            "foreign_capture_ref": ArtifactRef(run_b, capture_b.id, capture_b.revision).to_dict(),
            "workspace_a": str(cell / "ws-a"),
            "workspace_b": str(cell / "ws-b"),
        },
    )


SCENARIO_HANDLERS: Mapping[str, Callable[[str, Path], CellResult]] = {
    "interruption": _scenario_interruption,
    "provider_error": _scenario_provider_error,
    "stale_child": _scenario_stale_child,
    "artifact_tamper": _scenario_artifact_tamper,
    "resume": _scenario_resume,
    "cross_workspace_isolation": _scenario_cross_workspace_isolation,
}
