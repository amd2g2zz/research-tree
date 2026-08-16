from __future__ import annotations

from pathlib import Path
from runpy import run_path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "claude_orchestration_contract.py"


def _contract() -> dict[str, object]:
    return run_path(str(CONTRACT))


def _request(**overrides: object) -> dict[str, object]:
    request: dict[str, object] = {
        "project_id": "project-one",
        "run_id": "run-one",
        "requested_mode": "auto",
        "capabilities": {"agent": "available", "workflow": "available", "hooks": "available"},
        "claude_code_version": "2.1.221",
        "sdk_version": "0.1.0",
        "model": "claude-test",
        "package_revision": "package-243",
        "environment_digest": "a" * 64,
    }
    request.update(overrides)
    return request


def _receipt(mode: str) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": 1,
        "receipt_kind": "claude_code_runtime_receipt_v1",
        "mode": mode,
        "project_id": "project-one",
        "run_id": "run-one",
        "session_id": "session-one",
        "claude_code_version": "2.1.221",
        "sdk_version": "0.1.0",
        "model": "claude-test",
        "package_revision": "package-243",
        "environment_digest": "a" * 64,
        "hook_events": [{"event_id": "hook-one", "kind": "SessionStart"}],
        "workflow": {
            "workflow_id": "workflow-one",
            "script_digest": "b" * 64,
            "runtime_id": "workflow-runtime-one",
            "phases": [
                {"phase_id": "landscape", "runtime_id": "phase-one", "status": "completed"},
                {"phase_id": "validation", "runtime_id": "phase-two", "status": "completed"},
            ],
        },
        "agents": [
            {
                "agent_id": "agent-one",
                "runtime_id": "agent-runtime-one",
                "action_id": "action-one",
                "attempt_id": "attempt-one",
                "status": "completed",
                "parent_phase_id": "landscape",
                "delegation_depth": 1,
            },
            {
                "agent_id": "agent-two",
                "runtime_id": "agent-runtime-two",
                "action_id": "action-two",
                "attempt_id": "attempt-two",
                "status": "completed",
                "parent_phase_id": "validation",
                "delegation_depth": 1,
            },
        ],
    }
    if mode == "agent":
        receipt.pop("workflow")
        for agent in receipt["agents"]:  # type: ignore[index]
            agent.pop("parent_phase_id")  # type: ignore[union-attr]
    if mode == "workflow":
        receipt["agents"] = []
    return receipt


@pytest.mark.parametrize(
    ("capabilities", "requested_mode", "expected_mode"),
    [
        ({"agent": "available", "workflow": "available", "hooks": "available"}, "agent", "agent"),
        ({"agent": "available", "workflow": "available", "hooks": "available"}, "workflow", "workflow"),
        ({"agent": "available", "workflow": "available", "hooks": "available"}, "hybrid", "hybrid"),
        ({"agent": "available", "workflow": "unavailable", "hooks": "available"}, "auto", "agent"),
        ({"agent": "unavailable", "workflow": "available", "hooks": "available"}, "auto", "workflow"),
    ],
)
def test_select_mode_distinguishes_claude_native_surfaces(
    capabilities: dict[str, str], requested_mode: str, expected_mode: str
) -> None:
    selected = _contract()["select_mode"](_request(capabilities=capabilities, requested_mode=requested_mode))  # type: ignore[operator]

    assert selected["mode"] == expected_mode
    assert selected["selection_evidence"]["capabilities"] == capabilities
    assert len(selected["semantic_digest"]) == 64


def test_select_mode_reports_infeasible_without_fabricating_a_fallback() -> None:
    selected = _contract()["select_mode"](  # type: ignore[operator]
        _request(capabilities={"agent": "unavailable", "workflow": "denied", "hooks": "unknown"})
    )

    assert selected["mode"] == "infeasible"
    assert selected["authoritative"] is False


@pytest.mark.parametrize("mode", ["agent", "workflow", "hybrid"])
def test_bind_receipt_maps_real_native_identities_without_closure_authority(mode: str) -> None:
    selected = _contract()["select_mode"](_request(requested_mode=mode))  # type: ignore[operator]
    bridge = _contract()["bind_receipt"](selected, _receipt(mode))  # type: ignore[operator]

    assert bridge["mode"] == mode
    assert bridge["authoritative"] is False
    assert bridge["completion_authority"] == "coordinator_only"
    if mode == "agent":
        assert len(bridge["child_attempt_bindings"]) == 2
    else:
        assert len(bridge["phase_bindings"]) >= 2


def test_hybrid_receipt_rejects_nested_agents_and_quarantines_replanned_phases() -> None:
    contract = _contract()
    selected = contract["select_mode"](_request(requested_mode="hybrid"))  # type: ignore[operator]
    receipt = _receipt("hybrid")
    receipt["workflow"]["replan"] = {"reason_event_id": "contradiction-one", "superseded_phase_ids": ["landscape"]}  # type: ignore[index]
    bridge = contract["bind_receipt"](selected, receipt)  # type: ignore[operator]

    assert bridge["quarantined_phase_ids"] == ["landscape"]
    receipt["agents"][0]["delegation_depth"] = 2  # type: ignore[index]
    with pytest.raises(contract["ClaudeOrchestrationError"], match="delegation depth"):  # type: ignore[arg-type]
        contract["bind_receipt"](selected, receipt)  # type: ignore[operator]
