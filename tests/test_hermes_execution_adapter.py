from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from research_tree.contracts import HostEvent
from research_tree.coordinator import ResearchRunCoordinator
from research_tree.host_events import canonical_event_digest
from research_tree.leases import AttemptLease


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "hermes_execution_adapter.py"
NATIVE_ADAPTER = ROOT / "scripts" / "host_event_adapter.py"


def run_adapter(command: str, payload: dict[str, object], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    input_path = tmp_path / f"{command}.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(ADAPTER), command, "--input", str(input_path)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def event_context(*, expected_revision: int = 0, event_id: str = "hermes-event") -> dict[str, object]:
    return {
        "event_id": event_id,
        "run_id": "run-hermes",
        "round_id": "round-hermes",
        "slot_id": "slot-hermes",
        "action_id": "action-hermes",
        "attempt_id": "attempt-hermes",
        "causation_id": "cause-hermes",
        "correlation_id": "correlation-hermes",
        "sequence": 1,
        "expected_revision": expected_revision,
        "emitted_at": "2026-08-06T00:00:00Z",
    }


def test_task_projection_is_deterministic_and_creates_no_business_state(tmp_path: Path) -> None:
    payload = {
        "run_id": "run-hermes",
        "round_id": "round-hermes",
        "slot_id": "slot-hermes",
        "action_id": "action-hermes",
        "attempt_id": "attempt-hermes",
        "expected_revision": 7,
        "work_item_ref": {
            "run_id": "run-hermes",
            "artifact_id": "work-hermes",
            "revision": 1,
            "content_hash": "9" * 64,
        },
        "work_item": {
            "work_item_id": "work-hermes",
            "objective": "Verify the disputed implementation claim.",
            "method": "repository-inspection",
            "permission_profile": "read-only-network",
            "expected_output": "FindingPackV1",
            "success_oracle": "oracle-run-passes",
            "completion_evidence": ["evidence-artifact", "oracle-run"],
            "attempt_policy": {
                "max_attempts": 3,
                "method_switch_after": 1,
                "backoff_seconds": [1, 2, 4],
                "retryable_failures": ["provider_failed", "timeout"],
                "no_retry_failures": ["permission_denied", "integrity_failure", "authority_blocked"],
            },
        },
        "lease": {
            "owner": "hermes-worker",
            "dispatch_digest": "a" * 64,
            "lease_expires_at": "2026-08-06T00:15:00Z",
        },
    }

    first = run_adapter("project-task", payload, tmp_path)
    second = run_adapter("project-task", payload, tmp_path)

    assert first.returncode == second.returncode == 0, first.stderr + second.stderr
    assert first.stdout == second.stdout
    projection = json.loads(first.stdout)
    assert projection["kind"] == "hermes-task-projection"
    assert projection["idempotency_key"] == "research-tree:run-hermes:attempt-hermes"
    assert projection["canonical_refs"]["expected_revision"] == 7
    assert projection["acceptance_contract"]["work_item_ref"] == payload["work_item_ref"]
    assert projection["goal"]["acceptance_contract_digest"] == projection["acceptance_contract_digest"]
    assert "max_turns" not in projection["goal"]
    assert projection["kanban"]["idempotency_key"] == projection["idempotency_key"]
    assert any(
        "Hermes completion is non-authoritative" in criterion
        for criterion in projection["acceptance_criteria"]
    )
    assert not (tmp_path / ".research-tree-hermes").exists()
    assert not (tmp_path / ".research-tree").exists()


def test_provider_failure_translation_is_sanitized_and_attempt_bound(tmp_path: Path) -> None:
    payload = {
        **event_context(event_id="provider-failed-hermes"),
        "kind": "provider_failed",
        "details": {
            "provider": "openrouter",
            "model": "glm-5.2",
            "retry_category": "transient",
            "opaque_code": "gateway.retry.exhausted",
            "gateway_log_ref": "log:gateway-attempt-17",
        },
    }

    completed = run_adapter("translate-observation", payload, tmp_path)

    assert completed.returncode == 0, completed.stderr
    event = HostEvent.from_dict(json.loads(completed.stdout))
    assert event.host == "hermes"
    assert event.event_type == "provider_failed"
    assert event.attempt_id == "attempt-hermes"
    assert event.payload == payload["details"]
    assert not (tmp_path / ".research-tree-hermes").exists()

    payload["details"] = {**payload["details"], "raw_error": "secret provider response"}
    rejected = run_adapter("translate-observation", payload, tmp_path)
    assert rejected.returncode == 2
    assert "secret provider response" not in rejected.stderr
    assert json.loads(rejected.stderr)["code"] == "invalid_hermes_observation"

    payload["details"] = {
        key: value for key, value in payload["details"].items() if key != "raw_error"
    }
    payload["details"]["gateway_log_ref"] = "C:/Users/example/.hermes/logs/gateway.log"
    unsafe_ref = run_adapter("translate-observation", payload, tmp_path)
    assert unsafe_ref.returncode == 2
    assert "C:/Users/example" not in unsafe_ref.stderr


@pytest.mark.parametrize(
    ("kind", "event_type", "details"),
    [
        (
            "delegation_dispatched",
            "dispatch_requested",
            {
                "work_item_id": "work-hermes",
                "permission_profile": "read-only-network",
                "dispatch_digest": "a" * 64,
                "lease_policy": {"seconds": 300},
            },
        ),
        (
            "kanban_run_started",
            "attempt_started",
            {
                "worker_id": "hermes-worker",
                "lease_expires_at": "2026-08-06T00:15:00Z",
                "tool_capability_digest": "b" * 64,
                "started_at": "2026-08-06T00:00:00Z",
            },
        ),
        (
            "finding_submitted",
            "finding_submitted",
            {
                "finding_pack_digest": "c" * 64,
                "evidence_refs": ["evidence-1"],
                "submission_status": "submitted",
                "output_digest": "d" * 64,
            },
        ),
        (
            "review_completed",
            "review_completed",
            {
                "reviewer_id": "reviewer-1",
                "accepted_refs": ["finding-1"],
                "field_diagnostics": [],
                "review_digest": "e" * 64,
            },
        ),
        (
            "attempt_unknown",
            "attempt_unknown",
            {
                "reconciliation_reason": "restart",
                "last_heartbeat": None,
                "observed_host_state": {"status": "stale"},
            },
        ),
        (
            "retry_selected",
            "retry_requested",
            {
                "predecessor_attempt": "attempt-hermes",
                "method_provider_change": {"decision": "retry_same_provider"},
                "retry_policy": {"retry_ordinal": 1},
            },
        ),
        (
            "worker_finished",
            "worker_finished",
            {"terminal_status": "completed", "artifact_refs": ["finding-1"]},
        ),
        (
            "state_diverged",
            "reconciliation_detected",
            {
                "host_observation": {"status": "completed"},
                "canonical_observation": {"status": "running"},
                "conflict_class": "status",
                "next_action": "reconcile",
            },
        ),
    ],
)
def test_every_hermes_lifecycle_observation_maps_to_host_event(
    kind: str, event_type: str, details: dict[str, object], tmp_path: Path
) -> None:
    completed = run_adapter(
        "translate-observation",
        {**event_context(event_id=f"event-{kind.replace('_', '-')}"), "kind": kind, "details": details},
        tmp_path,
    )

    assert completed.returncode == 0, completed.stderr
    event = HostEvent.from_dict(json.loads(completed.stdout))
    assert event.event_type == event_type
    assert event.host == "hermes"
    assert dict(event.payload) == details


@pytest.mark.parametrize(
    ("kind", "claim_kind"),
    [
        ("goal_succeeded", "host_status"),
        ("kanban_completed", "worker_status"),
        ("hook_completed", "hook_success"),
        ("wave_completed", "completed_wave"),
    ],
)
def test_hermes_success_signals_are_non_authoritative_completion_claims(
    kind: str, claim_kind: str, tmp_path: Path
) -> None:
    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-hermes")
    payload = {
        **event_context(expected_revision=state["revision"], event_id=f"claim-{claim_kind.replace('_', '-') }"),
        "kind": kind,
        "attempt_id": None,
        "details": {"source_ref": f"hermes:{kind}", "local_status": "completed"},
    }

    translated = run_adapter("translate-observation", payload, tmp_path)
    assert translated.returncode == 0, translated.stderr
    event = HostEvent.from_dict(json.loads(translated.stdout))
    assert event.event_type == "completion_claimed"
    assert event.payload["claim_kind"] == claim_kind

    before = coordinator.status("run-hermes")
    with pytest.raises(coordinator.error_type) as error:
        coordinator.ingest_host_event(event)
    assert error.value.code == "completion_claim_rejected"
    after = coordinator.status("run-hermes")
    assert after["revision"] == before["revision"]
    assert after["state_digest"] == before["state_digest"]
    assert after["lifecycle_state"] != "completed"


def test_provider_failure_recovers_after_restart_without_human_intervention(tmp_path: Path) -> None:
    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-hermes")
    coordinator.issue_lease(
        AttemptLease.create(
            attempt_id="attempt-hermes",
            work_item_id="work-hermes",
            run_id="run-hermes",
            owner="hermes-worker",
            dispatch_digest="a" * 64,
            started_at="2026-08-06T00:00:00Z",
            lease_expires_at="2026-08-06T01:00:00Z",
        ),
        expected_revision=state["revision"],
    )
    state = coordinator.status("run-hermes")
    failure_payload = {
        **event_context(expected_revision=state["revision"], event_id="provider-failed-hermes"),
        "kind": "provider_failed",
        "details": {
            "provider": "primary",
            "model": "model-a",
            "retry_category": "transient",
            "opaque_code": "provider.exhausted",
            "gateway_log_ref": "log:attempt-hermes",
        },
    }
    failed = run_adapter("translate-observation", failure_payload, tmp_path)
    coordinator.ingest_host_event(json.loads(failed.stdout))
    assert coordinator.attempts("run-hermes")["attempt-hermes"]["status"] == "retryable"

    # Simulate a process restart. Recovery reads only canonical state plus a fresh
    # Hermes snapshot and chooses an authority-allowed fallback provider.
    restarted = ResearchRunCoordinator(tmp_path)
    state = restarted.status("run-hermes")
    recovery_payload = {
        "context": {
            **event_context(expected_revision=state["revision"], event_id="retry-hermes"),
            "sequence": 2,
        },
        "canonical_attempt": {
            **restarted.attempts("run-hermes")["attempt-hermes"],
            "method": "repository-inspection",
            "provider": "primary",
            "model": "model-a",
        },
        "policy": {
            "max_attempts": 3,
            "method_switch_after": 2,
            "backoff_seconds": [1, 2, 4],
            "retryable_failures": ["provider_failed", "timeout", "unknown"],
            "no_retry_failures": ["permission_denied", "integrity_failure", "authority_blocked"],
        },
        "snapshot": {"status": "provider_failed", "failure_category": "provider_failed"},
        "authority": {
            "allowed_providers": ["primary", "fallback"],
            "allowed_methods": ["repository-inspection", "browser-validation"],
        },
        "fallback_providers": [{"provider": "fallback", "model": "model-b"}],
        "fallback_methods": ["browser-validation"],
    }

    planned = run_adapter("plan-recovery", recovery_payload, tmp_path)
    assert planned.returncode == 0, planned.stderr
    plan = json.loads(planned.stdout)
    assert plan["decision"] == "alternate_provider"
    assert plan["next_attempt"]["attempt_id"] == "work-hermes-retry-1"
    assert plan["next_attempt"]["provider"] == "fallback"
    retry_event = HostEvent.from_dict(plan["events"][0])
    assert retry_event.event_type == "retry_requested"
    restarted.ingest_host_event(retry_event)
    state = restarted.status("run-hermes")
    retried = restarted.retry_attempt(
        "run-hermes",
        "attempt-hermes",
        dispatch_digest=plan["next_attempt"]["dispatch_digest"],
        expected_revision=state["revision"],
        lease_seconds=60,
    )
    assert retried["retry"]["attempt_id"] == plan["next_attempt"]["attempt_id"]
    assert ResearchRunCoordinator(tmp_path).attempts("run-hermes")["work-hermes-retry-1"]["status"] == "leased"
    assert not (tmp_path / ".research-tree-hermes").exists()


def test_recovery_method_switch_and_authority_block_are_explicit(tmp_path: Path) -> None:
    base = {
        "context": {**event_context(event_id="retry-method"), "sequence": 2},
        "canonical_attempt": {
            "attempt_id": "attempt-hermes",
            "work_item_id": "work-hermes",
            "run_id": "run-hermes",
            "status": "retryable",
            "dispatch_digest": "a" * 64,
            "retry_ordinal": 1,
            "method": "repository-inspection",
            "provider": "primary",
            "model": "model-a",
        },
        "policy": {
            "max_attempts": 3,
            "method_switch_after": 1,
            "backoff_seconds": [1, 2, 4],
            "retryable_failures": ["provider_failed", "unknown"],
            "no_retry_failures": ["permission_denied", "integrity_failure", "authority_blocked"],
        },
        "snapshot": {"status": "unknown", "failure_category": "unknown"},
        "authority": {
            "allowed_providers": ["primary"],
            "allowed_methods": ["repository-inspection", "browser-validation"],
        },
        "fallback_providers": [],
        "fallback_methods": ["browser-validation"],
    }
    switched = run_adapter("plan-recovery", base, tmp_path)
    assert switched.returncode == 0, switched.stderr
    switch_plan = json.loads(switched.stdout)
    assert switch_plan["decision"] == "method_switch"
    assert [event["event_type"] for event in switch_plan["events"]] == [
        "attempt_unknown",
        "retry_requested",
    ]
    assert switch_plan["next_attempt"]["method"] == "browser-validation"

    blocked_payload = json.loads(json.dumps(base))
    blocked_payload["authority"]["allowed_methods"] = ["repository-inspection"]
    blocked = run_adapter("plan-recovery", blocked_payload, tmp_path)
    assert blocked.returncode == 0, blocked.stderr
    block_plan = json.loads(blocked.stdout)
    assert block_plan["decision"] == "authority_blocked"
    assert block_plan["next_attempt"] is None
    assert [event["event_type"] for event in block_plan["events"]] == ["attempt_unknown"]


def test_recovery_retries_same_provider_and_stops_for_nonretryable_failure(tmp_path: Path) -> None:
    payload = {
        "context": event_context(event_id="retry-same-provider"),
        "canonical_attempt": {
            "attempt_id": "attempt-hermes",
            "work_item_id": "work-hermes",
            "run_id": "run-hermes",
            "status": "retryable",
            "dispatch_digest": "a" * 64,
            "retry_ordinal": 0,
            "method": "repository-inspection",
            "provider": "primary",
            "model": "model-a",
        },
        "policy": {
            "max_attempts": 3,
            "method_switch_after": 1,
            "backoff_seconds": [1, 2, 4],
            "retryable_failures": ["provider_failed", "timeout", "unknown"],
            "no_retry_failures": ["permission_denied", "integrity_failure", "authority_blocked"],
        },
        "snapshot": {"status": "provider_failed", "failure_category": "provider_failed"},
        "authority": {
            "allowed_providers": ["primary"],
            "allowed_methods": ["repository-inspection"],
        },
        "fallback_providers": [],
        "fallback_methods": [],
    }
    retried = run_adapter("plan-recovery", payload, tmp_path)
    assert retried.returncode == 0, retried.stderr
    plan = json.loads(retried.stdout)
    assert plan["decision"] == "retry_same_provider"
    assert plan["next_attempt"]["provider"] == "primary"
    assert plan["events"][0]["event_type"] == "retry_requested"

    denied = json.loads(json.dumps(payload))
    denied["snapshot"]["failure_category"] = "permission_denied"
    stopped = run_adapter("plan-recovery", denied, tmp_path)
    assert stopped.returncode == 0, stopped.stderr
    disposition = json.loads(stopped.stdout)
    assert disposition["decision"] == "terminal_failure"
    assert disposition["events"] == []
    assert disposition["next_attempt"] is None

    completed_payload = json.loads(json.dumps(payload))
    completed_payload["snapshot"] = {
        "status": "completed",
        "failure_category": "unknown",
    }
    completed = run_adapter("plan-recovery", completed_payload, tmp_path)
    assert completed.returncode == 0, completed.stderr
    review = json.loads(completed.stdout)
    assert review["decision"] == "awaiting_evidence_review"
    assert review["events"] == []
    assert review["next_attempt"] is None


def test_copied_hermes_package_executes_its_distinct_adapter(tmp_path: Path) -> None:
    package = ROOT / "packages" / "hermes" / "research-tree"
    copied = tmp_path / "installed" / "research-tree"
    import shutil

    shutil.copytree(package, copied)
    payload = {
        **event_context(event_id="copied-hermes"),
        "kind": "provider_failed",
        "details": {
            "provider": "primary",
            "model": "model-a",
            "retry_category": "transient",
            "opaque_code": "provider.exhausted",
            "gateway_log_ref": "sha256:" + "f" * 64,
        },
    }
    input_path = tmp_path / "copied-input.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(copied / "scripts" / "hermes_execution_adapter.py"),
            "translate-observation",
            "--input",
            str(input_path),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert HostEvent.from_dict(json.loads(completed.stdout)).host == "hermes"
    assert not (copied / "scripts" / "codex_execution_adapter.py").exists()
    assert not (copied / "scripts" / "claude_execution_adapter.py").exists()


def test_hermes_and_native_equivalent_events_have_same_semantic_digest(tmp_path: Path) -> None:
    input_event = {
        **event_context(event_id="provider-parity"),
        "event_type": "provider_failed",
        "payload": {
            "provider": "gateway",
            "model": "model-a",
            "retry_category": "transient",
            "opaque_code": "provider.exhausted",
            "gateway_log_ref": "log:provider-parity",
        },
    }
    native_path = tmp_path / "native.json"
    native_path.write_text(json.dumps(input_event), encoding="utf-8")
    native = subprocess.run(
        [sys.executable, str(NATIVE_ADAPTER), "--host", "codex", "emit", "--input", str(native_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    hermes_payload = {
        **{key: value for key, value in input_event.items() if key not in {"event_type", "payload"}},
        "kind": "provider_failed",
        "details": input_event["payload"],
    }
    hermes = run_adapter("translate-observation", hermes_payload, tmp_path)

    assert native.returncode == hermes.returncode == 0, native.stderr + hermes.stderr
    assert canonical_event_digest([json.loads(native.stdout)]) == canonical_event_digest([json.loads(hermes.stdout)])


def _run_provider_restart_fixture(workspace: Path, host: str) -> dict[str, object]:
    workspace.mkdir()
    coordinator = ResearchRunCoordinator(workspace)
    state = coordinator.create("run-hermes")
    coordinator.issue_lease(
        AttemptLease.create(
            attempt_id="attempt-hermes",
            work_item_id="work-hermes",
            run_id="run-hermes",
            owner="worker",
            dispatch_digest="a" * 64,
            started_at="2026-08-06T00:00:00Z",
            lease_expires_at="2026-08-06T01:00:00Z",
        ),
        expected_revision=state["revision"],
    )
    failure_payload = {
        **event_context(
            expected_revision=coordinator.status("run-hermes")["revision"],
            event_id="provider-failed-parity",
        ),
        "event_type": "provider_failed",
        "payload": {
            "provider": "primary",
            "model": "model-a",
            "retry_category": "transient",
            "opaque_code": "provider.exhausted",
            "gateway_log_ref": "log:provider-parity",
        },
    }
    if host == "hermes":
        translated = run_adapter(
            "translate-observation",
            {
                **{key: value for key, value in failure_payload.items() if key not in {"event_type", "payload"}},
                "kind": "provider_failed",
                "details": failure_payload["payload"],
            },
            workspace,
        )
    else:
        input_path = workspace / "native-provider.json"
        input_path.write_text(json.dumps(failure_payload), encoding="utf-8")
        translated = subprocess.run(
            [sys.executable, str(NATIVE_ADAPTER), "--host", host, "emit", "--input", str(input_path)],
            text=True,
            capture_output=True,
            check=False,
        )
    assert translated.returncode == 0, translated.stderr
    failure_event = json.loads(translated.stdout)
    coordinator.ingest_host_event(failure_event)

    restarted = ResearchRunCoordinator(workspace)
    recovery = {
        "context": {
            **event_context(
                expected_revision=restarted.status("run-hermes")["revision"],
                event_id="retry-parity",
            ),
            "sequence": 2,
        },
        "canonical_attempt": {
            **restarted.attempts("run-hermes")["attempt-hermes"],
            "method": "repository-inspection",
            "provider": "primary",
            "model": "model-a",
        },
        "policy": {
            "max_attempts": 3,
            "method_switch_after": 1,
            "backoff_seconds": [1, 2, 4],
            "retryable_failures": ["provider_failed", "unknown"],
            "no_retry_failures": ["permission_denied", "integrity_failure", "authority_blocked"],
        },
        "snapshot": {"status": "provider_failed", "failure_category": "provider_failed"},
        "authority": {
            "allowed_providers": ["primary"],
            "allowed_methods": ["repository-inspection"],
        },
        "fallback_providers": [],
        "fallback_methods": [],
    }
    planned = run_adapter("plan-recovery", recovery, workspace)
    assert planned.returncode == 0, planned.stderr
    plan = json.loads(planned.stdout)
    hermes_retry = plan["events"][0]
    if host == "hermes":
        retry_event = hermes_retry
    else:
        native_retry_input = {
            key: value
            for key, value in hermes_retry.items()
            if key not in {"protocol_version", "host", "payload_digest"}
        }
        input_path = workspace / "native-retry.json"
        input_path.write_text(json.dumps(native_retry_input), encoding="utf-8")
        emitted = subprocess.run(
            [sys.executable, str(NATIVE_ADAPTER), "--host", host, "emit", "--input", str(input_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert emitted.returncode == 0, emitted.stderr
        retry_event = json.loads(emitted.stdout)
    restarted.ingest_host_event(retry_event)
    status = restarted.status("run-hermes")
    restarted.retry_attempt(
        "run-hermes",
        "attempt-hermes",
        dispatch_digest=plan["next_attempt"]["dispatch_digest"],
        expected_revision=status["revision"],
        lease_seconds=60,
    )
    final = restarted.status("run-hermes")
    attempts = restarted.attempts("run-hermes")
    normalized_attempts = {
        attempt_id: {
            "status": value["status"],
            "retry_ordinal": value["retry_ordinal"],
            "dispatch_digest": value["dispatch_digest"],
        }
        for attempt_id, value in attempts.items()
    }
    return {
        "state": {
            "revision": final["revision"],
            "lifecycle_state": final["lifecycle_state"],
            "state_digest": final["state_digest"],
        },
        "attempts": normalized_attempts,
        "event_digest": canonical_event_digest([failure_event, retry_event]),
    }


def test_long_horizon_provider_restart_matches_native_host_semantics(tmp_path: Path) -> None:
    hermes = _run_provider_restart_fixture(tmp_path / "hermes", "hermes")
    codex = _run_provider_restart_fixture(tmp_path / "codex", "codex")

    assert hermes == codex


def test_adapter_source_has_no_legacy_business_state_or_report_gate() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    assert ".research-tree-hermes" not in source
    assert "prepare-delivery" not in source
    assert "technical-report" not in source
    assert "human-report" not in source
    assert "state.json" not in source
    assert "canonical_complete" not in source
