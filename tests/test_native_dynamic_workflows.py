from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from research_tree import (
    HostCapabilityError,
    HostEvent,
    NativeWorkflowError,
    capability_manifest,
    probe_host,
    record_probe_failure,
    project_native_workflow,
    reconcile_native_workflow,
    replan_native_workflow,
    resume_native_workflow,
    workflow_host_event,
)


AVAILABLE = {
    "native_dynamic_workflow": "available",
    "dynamic_delegation": "available",
    "parallel_workers": "available",
    "lifecycle_hooks": "available",
    "background_execution": "available",
    "durable_resume": "available",
    "scheduled_drain": "available",
    "structured_event_transport": "available",
}
ROOT = Path(__file__).resolve().parents[1]
NATIVE_ADAPTER = ROOT / "scripts" / "native_execution_adapter.py"
HERMES_ADAPTER = ROOT / "scripts" / "hermes_execution_adapter.py"


def _actions() -> tuple[dict[str, object], ...]:
    return (
        {"action_id": "action-a", "phase_id": "landscape", "dependencies": []},
        {"action_id": "action-b", "phase_id": "deep-dive", "dependencies": []},
    )


def _run_adapter(workspace: Path, host: str, command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    if host == "hermes":
        invocation = [sys.executable, str(HERMES_ADAPTER), "--workspace", str(workspace), command, *arguments]
    else:
        invocation = [
            sys.executable,
            str(NATIVE_ADAPTER),
            "--host",
            "claude" if host == "claude-code" else host,
            "--workspace",
            str(workspace),
            command,
            *arguments,
        ]
    return subprocess.run(invocation, cwd=workspace, text=True, capture_output=True, check=False)


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.mark.parametrize("state", ["unavailable", "partial", "denied", "failed", "unknown"])
def test_capability_probe_is_honest_and_selects_fallback(state: str) -> None:
    observations = {**AVAILABLE, "native_dynamic_workflow": state}
    probe = probe_host("codex", observations)

    assert probe["mode"] == "fallback"
    assert probe["fallback_id"] == "coordinator-dispatch-v1"
    assert probe["observations"]["native_dynamic_workflow"] == state
    assert len(probe["semantic_digest"]) == 64


def test_invocation_failure_changes_digest_without_claiming_native_support() -> None:
    available = probe_host("claude-code", AVAILABLE)
    failed = record_probe_failure(available, "native_dynamic_workflow", "permission_denied")

    assert available["mode"] == "native"
    assert failed["mode"] == "fallback"
    assert failed["observations"]["native_dynamic_workflow"] == "failed"
    assert failed["failure_codes"] == {"native_dynamic_workflow": "permission_denied"}
    assert failed["semantic_digest"] != available["semantic_digest"]


def test_capability_manifest_rejects_unknown_surface() -> None:
    manifest = capability_manifest("hermes")
    assert manifest["host"] == "hermes"
    assert manifest["fallback_id"] == "coordinator-dispatch-v1"
    with pytest.raises(HostCapabilityError, match="unsupported capability"):
        probe_host("hermes", {**AVAILABLE, "telepathy": "available"})


def test_hermes_optional_surfaces_select_independent_fallbacks() -> None:
    probe = probe_host(
        "hermes",
        {
            **AVAILABLE,
            "lifecycle_hooks": "unavailable",
            "scheduled_drain": "denied",
            "parallel_workers": "partial",
        },
    )

    assert probe["mode"] == "native"
    assert probe["selected_fallbacks"] == {
        "lifecycle_hooks": "host-event-observation-v1",
        "parallel_workers": "bounded-sequential-dispatch-v1",
        "scheduled_drain": "checkpoint-resume-v1",
    }


@pytest.mark.parametrize(
    ("host", "native_surface"),
    [
        ("claude-code", "claude-dynamic-phases"),
        ("codex", "codex-concurrent-ready"),
        ("hermes", "hermes-delegation-batch"),
    ],
)
def test_native_projection_preserves_canonical_obligations(host: str, native_surface: str) -> None:
    probe = probe_host(host, AVAILABLE)
    workflow = project_native_workflow(
        workflow_id=f"workflow-{host}",
        script_id="script-one",
        run_id="run-one",
        run_revision=7,
        strategy_revision="strategy-one",
        permission_profile="research-read-write",
        checkpoint_contract="analysis-checkpoint-v1",
        checkpoint_refs=("checkpoint-one",),
        actions=_actions(),
        capability_probe=probe,
        max_phases=4,
        max_children=4,
    )

    assert workflow["native_surface"] == native_surface
    assert workflow["action_refs"] == ["action-a", "action-b"]
    assert workflow["checkpoint_refs"] == ["checkpoint-one"]
    assert workflow["authoritative"] is False
    assert workflow["completion_authority"] == "coordinator_only"
    assert workflow["complete"] is False


def test_fallback_projection_retains_actions_and_completion_guards() -> None:
    probe = probe_host("codex", {**AVAILABLE, "native_dynamic_workflow": "unavailable"})
    workflow = project_native_workflow(
        workflow_id="workflow-fallback",
        script_id="script-fallback",
        run_id="run-one",
        run_revision=3,
        strategy_revision="strategy-one",
        permission_profile="bounded",
        checkpoint_contract="analysis-checkpoint-v1",
        checkpoint_refs=(),
        actions=_actions(),
        capability_probe=probe,
        max_phases=4,
        max_children=4,
    )

    assert workflow["mode"] == "fallback"
    assert workflow["native_surface"] == "coordinator-dispatch"
    assert workflow["action_refs"] == ["action-a", "action-b"]
    assert workflow["complete"] is False


def test_claude_replan_preserves_workflow_and_script_identity() -> None:
    workflow = project_native_workflow(
        workflow_id="workflow-claude",
        script_id="script-claude",
        run_id="run-one",
        run_revision=7,
        strategy_revision="strategy-one",
        permission_profile="bounded",
        checkpoint_contract="analysis-checkpoint-v1",
        checkpoint_refs=("checkpoint-one",),
        actions=_actions(),
        capability_probe=probe_host("claude-code", AVAILABLE),
        max_phases=4,
        max_children=4,
    )
    replanned = replan_native_workflow(
        workflow,
        strategy_revision="strategy-two",
        run_revision=8,
        successor_actions=({"action_id": "action-c", "phase_id": "validation", "dependencies": []},),
        reason_event_ref="event-contradiction",
    )

    assert replanned["workflow_id"] == workflow["workflow_id"]
    assert replanned["script_id"] == workflow["script_id"]
    assert replanned["projection_revision"] == workflow["projection_revision"] + 1
    assert replanned["strategy_revision"] == "strategy-two"
    assert replanned["stale_phase_refs"] == ["landscape", "deep-dive"]
    assert replanned["replan_event_refs"] == ["event-contradiction"]


def test_resume_and_reconcile_require_checkpoint_backed_identity() -> None:
    workflow = project_native_workflow(
        workflow_id="workflow-hermes",
        script_id="script-hermes",
        run_id="run-one",
        run_revision=7,
        strategy_revision="strategy-one",
        permission_profile="bounded",
        checkpoint_contract="analysis-checkpoint-v1",
        checkpoint_refs=("checkpoint-one",),
        actions=_actions(),
        capability_probe=probe_host("hermes", AVAILABLE),
        max_phases=4,
        max_children=4,
    )
    resumed = resume_native_workflow(workflow, checkpoint_ref="checkpoint-two", run_revision=8)
    reconciliation = reconcile_native_workflow(
        resumed,
        host_children={resumed["children"][0]["attempt_id"]: "completed"},
        checkpoint_child_refs=(),
        current_strategy_revision="strategy-one",
    )

    assert resumed["workflow_id"] == workflow["workflow_id"]
    assert resumed["checkpoint_refs"] == ["checkpoint-one", "checkpoint-two"]
    assert reconciliation["classifications"][resumed["children"][0]["attempt_id"]] == "unknown"
    assert reconciliation["next_action"] == "resume_from_checkpoint"
    assert reconciliation["complete"] is False


def test_stale_strategy_and_provider_failure_are_non_success() -> None:
    workflow = project_native_workflow(
        workflow_id="workflow-codex",
        script_id="script-codex",
        run_id="run-one",
        run_revision=7,
        strategy_revision="strategy-one",
        permission_profile="bounded",
        checkpoint_contract="analysis-checkpoint-v1",
        checkpoint_refs=("checkpoint-one",),
        actions=_actions(),
        capability_probe=probe_host("codex", AVAILABLE),
        max_phases=4,
        max_children=4,
    )
    reconciliation = reconcile_native_workflow(
        workflow,
        host_children={child["attempt_id"]: "active" for child in workflow["children"]},
        checkpoint_child_refs=tuple(child["attempt_id"] for child in workflow["children"]),
        current_strategy_revision="strategy-two",
    )
    assert set(reconciliation["classifications"].values()) == {"stale"}
    assert reconciliation["next_action"] == "replan"
    assert workflow["complete"] is False
    with pytest.raises(NativeWorkflowError, match="maximum phases"):
        project_native_workflow(
            workflow_id="workflow-too-large",
            script_id="script-too-large",
            run_id="run-one",
            run_revision=7,
            strategy_revision="strategy-one",
            permission_profile="bounded",
            checkpoint_contract="analysis-checkpoint-v1",
            checkpoint_refs=(),
            actions=_actions(),
            capability_probe=probe_host("codex", AVAILABLE),
            max_phases=1,
            max_children=4,
        )


def test_workflow_events_are_digest_bound_and_non_authoritative() -> None:
    workflow = project_native_workflow(
        workflow_id="workflow-event",
        script_id="script-event",
        run_id="run-event",
        run_revision=4,
        strategy_revision="strategy-one",
        permission_profile="bounded",
        checkpoint_contract="analysis-checkpoint-v1",
        checkpoint_refs=("checkpoint-one",),
        actions=_actions(),
        capability_probe=probe_host("codex", AVAILABLE),
        max_phases=4,
        max_children=4,
    )
    event = workflow_host_event(
        workflow,
        event_id="event-workflow-started",
        kind="workflow_started",
        attempt_id=workflow["children"][0]["attempt_id"],
        sequence=1,
        created_at="2026-08-12T00:00:00+00:00",
    )

    parsed = HostEvent.from_value(event.to_dict())
    assert parsed.kind == "workflow_started"
    assert parsed.payload["workflow_id"] == "workflow-event"
    assert parsed.payload["completion_authority"] == "coordinator_only"
    assert parsed.payload["authoritative"] is False

    resumed = workflow_host_event(
        workflow,
        event_id="event-workflow-resumed",
        kind="workflow_resumed",
        attempt_id=workflow["children"][0]["attempt_id"],
        sequence=2,
        created_at="2026-08-12T00:01:00+00:00",
    )
    phase = workflow_host_event(
        workflow,
        event_id="event-workflow-phase",
        kind="workflow_phase_completed",
        attempt_id=workflow["children"][0]["attempt_id"],
        sequence=3,
        created_at="2026-08-12T00:02:00+00:00",
        phase_id="landscape",
        child_attempt_refs=(workflow["children"][0]["attempt_id"],),
        produced_artifact_refs=("capture-one", "checkpoint-one"),
        successor_disposition="validate",
    )
    failed = workflow_host_event(
        workflow,
        event_id="event-workflow-failed",
        kind="provider_failure",
        attempt_id=workflow["children"][0]["attempt_id"],
        sequence=4,
        created_at="2026-08-12T00:03:00+00:00",
        category="retryable",
        provider="provider-one",
        model="model-one",
        opaque_code="permission-limit",
        safe_log_ref="log-one",
    )
    reconciled = workflow_host_event(
        workflow,
        event_id="event-workflow-reconciled",
        kind="reconciliation_detected",
        attempt_id=workflow["children"][0]["attempt_id"],
        sequence=5,
        created_at="2026-08-12T00:04:00+00:00",
        classifications={workflow["children"][0]["attempt_id"]: "unknown"},
        next_action="resume_from_checkpoint",
    )

    assert resumed.payload["checkpoint_refs"] == ["checkpoint-one"]
    assert phase.payload["successor_disposition"] == "validate"
    assert phase.payload["produced_artifact_refs"] == ["capture-one", "checkpoint-one"]
    assert failed.payload["opaque_code"] == "permission-limit"
    assert failed.payload["complete"] is False
    assert reconciled.payload["next_action"] == "resume_from_checkpoint"


def test_native_workflow_schema_examples_validate_with_contract_validator() -> None:
    schema_root = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2" / "schemas"
    schema = json.loads((schema_root / "native-workflow-run-v1.json").read_text(encoding="utf-8"))
    examples = json.loads((schema_root / "examples" / "index-v1.json").read_text(encoding="utf-8"))
    row = next(item for item in examples if False) if isinstance(examples, list) else None
    if row is None:
        rows = examples.get("entries", [])
        row = next(item for item in rows if item.get("schema") == "native-workflow-run-v1.json")
    valid = row["valid"]

    assert set(schema["required"]) <= set(valid)
    assert valid["completion_authority"] == "coordinator_only"
    assert valid["authoritative"] is False
    assert valid["complete"] is False


@pytest.mark.parametrize("host", ["claude-code", "codex", "hermes"])
def test_packaged_adapters_probe_project_and_reconcile(host: str, tmp_path: Path) -> None:
    observations = _write_json(tmp_path / "observations.json", AVAILABLE)
    probed = _run_adapter(tmp_path, host, "probe-host", "--observations", str(observations))
    assert probed.returncode == 0, probed.stdout + probed.stderr
    probe = json.loads(probed.stdout)
    assert probe["mode"] == "native"
    assert probe["host"] == host

    request = _write_json(
        tmp_path / "projection.json",
        {
            "workflow_id": f"workflow-{host}",
            "script_id": "script-one",
            "run_id": "run-one",
            "run_revision": 5,
            "strategy_revision": "strategy-one",
            "permission_profile": "bounded",
            "checkpoint_contract": "analysis-checkpoint-v1",
            "checkpoint_refs": ["checkpoint-one"],
            "actions": list(_actions()),
            "capability_probe": probe,
            "max_phases": 4,
            "max_children": 4,
        },
    )
    projected = _run_adapter(tmp_path, host, "project-workflow", "--request", str(request))
    assert projected.returncode == 0, projected.stdout + projected.stderr
    workflow = json.loads(projected.stdout)
    assert workflow["workflow_id"] == f"workflow-{host}"
    assert workflow["action_refs"] == ["action-a", "action-b"]
    assert workflow["completion_authority"] == "coordinator_only"
    assert workflow["complete"] is False

    reconciliation_request = _write_json(
        tmp_path / "reconciliation.json",
        {
            "workflow": workflow,
            "host_children": {workflow["children"][0]["attempt_id"]: "completed"},
            "checkpoint_child_refs": [],
            "current_strategy_revision": "strategy-one",
        },
    )
    reconciled = _run_adapter(tmp_path, host, "reconcile-host", "--request", str(reconciliation_request))
    assert reconciled.returncode == 0, reconciled.stdout + reconciled.stderr
    result = json.loads(reconciled.stdout)
    assert set(result["classifications"].values()) >= {"unknown"}
    assert result["complete"] is False
    assert result["completion_authority"] == "coordinator_only"

    replan_request = _write_json(
        tmp_path / "replan.json",
        {
            "workflow": workflow,
            "strategy_revision": "strategy-two",
            "run_revision": 6,
            "successor_actions": [{"action_id": "action-c", "phase_id": "validation", "dependencies": []}],
            "reason_event_ref": "event-contradiction",
        },
    )
    replanned = _run_adapter(tmp_path, host, "replan-workflow", "--request", str(replan_request))
    assert replanned.returncode == 0, replanned.stdout + replanned.stderr
    successor = json.loads(replanned.stdout)
    assert successor["workflow_id"] == workflow["workflow_id"]
    assert successor["script_id"] == workflow["script_id"]
    assert successor["strategy_revision"] == "strategy-two"
    assert successor["stale_phase_refs"] == workflow["phase_refs"]

    resume_request = _write_json(
        tmp_path / "resume.json",
        {"workflow": successor, "checkpoint_ref": "checkpoint-two", "run_revision": 7},
    )
    resumed = _run_adapter(tmp_path, host, "resume-workflow", "--request", str(resume_request))
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    continuation = json.loads(resumed.stdout)
    assert continuation["workflow_id"] == workflow["workflow_id"]
    assert continuation["script_id"] == workflow["script_id"]
    assert continuation["checkpoint_refs"] == ["checkpoint-one", "checkpoint-two"]
    assert continuation["complete"] is False
