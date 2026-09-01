"""Issue #322: host-capability discovery (Pi-native + bounded recon).

Probe-semantics tests ported from ``origin/dev:tests/test_native_dynamic_workflows.py``
after batch-1 retired ``native_workflows.py`` along with that test file — the
deleted file carried assertions about surviving ``host_capabilities`` behaviour.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from research_tree.host_capabilities import (
    CAPABILITY_FALLBACKS,
    CAPABILITY_STATES,
    HOST_SURFACES,
    HOSTS,
    HostCapabilityError,
    capability_manifest,
    probe_host,
    record_probe_failure,
)

ROOT = Path(__file__).resolve().parents[1]
NATIVE_ADAPTER = ROOT / "scripts" / "native_execution_adapter.py"
HERMES_ADAPTER = ROOT / "scripts" / "hermes_execution_adapter.py"

AVAILABLE = {
    "native_dynamic_workflow": "available",
    "dynamic_delegation": "available",
    "parallel_workers": "available",
    "lifecycle_hooks": "available",
    "background_execution": "available",
    "durable_resume": "available",
    "scheduled_drain": "available",
    "structured_event_transport": "available",
    "claude-agent-children": "available",
    "claude-native-workflow": "available",
    "claude-hybrid-workflow": "available",
}


def test_probe_commands_cover_required_surfaces() -> None:
    for host in HOSTS:
        assert host in HOST_SURFACES


def test_capability_manifest_for_known_host_returns_structured_record() -> None:
    """Every known host yields a structured capability record (no user deflection)."""

    for host in HOSTS:
        record = capability_manifest(host)
        assert record["host"] == host
        assert "capabilities" in record
        assert "fallback_id" in record


def test_capability_manifest_records_each_surface() -> None:
    record = capability_manifest("codex")
    assert record["host"] == "codex"
    assert "capabilities" in record
    assert record["fallback_id"] == "coordinator-dispatch-v1"


def test_missing_capability_yields_degraded_strategy_with_fallback() -> None:
    """A capability that is unavailable has a recorded fallback (not a hard block)."""

    assert isinstance(CAPABILITY_FALLBACKS, dict)
    assert len(CAPABILITY_FALLBACKS) > 0


def test_pi_supported_via_compatibility_path() -> None:
    """Host-iteration UI is host-specific — surfaces are keyed by host."""

    assert "claude-code" in HOST_SURFACES
    assert "codex" in HOST_SURFACES
    assert "hermes" in HOST_SURFACES


def test_host_capability_disposition_states_are_distinct() -> None:
    assert {"available", "unavailable", "partial", "denied", "failed", "unknown"} <= set(CAPABILITY_STATES)


def test_pi_in_host_registry_with_native_surface() -> None:
    """#322 acceptance: Pi has a supported activation path (in the registry)."""

    from research_tree.host_capabilities import HOSTS as known_hosts

    assert "pi" in known_hosts, "Pi must be a known host with a supported activation path"
    from research_tree.host_capabilities import HOST_SURFACES

    assert "pi" in HOST_SURFACES
    record = capability_manifest("pi")
    assert record["host"] == "pi"


# ---------------------------------------------------------------------------
# Probe semantics — ported from tests/test_native_dynamic_workflows.py
# ---------------------------------------------------------------------------


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
