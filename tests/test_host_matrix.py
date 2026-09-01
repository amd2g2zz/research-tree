"""Gate 7 (#292): live-host failure-injection matrix (red-first contract tests).

Every test drives the harness through real runtime runs: a real RunLedger, the
real coordinator, real files, the real run-bound launcher subprocess, and the
real host-neutral CLI.  No runtime component is replaced by a stand-in.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation" / "harness"))

from host_matrix import (  # noqa: E402
    ATTEMPT_HOSTS,
    HOSTS,
    SCENARIOS,
    build_receipt,
    run_matrix,
    run_scenario,
)

RUNNER = ROOT / "evaluation" / "harness" / "run_host_matrix.py"


def test_matrix_parameters_are_canonical() -> None:
    assert SCENARIOS == (
        "interruption",
        "provider_error",
        "stale_child",
        "artifact_tamper",
        "resume",
        "cross_workspace_isolation",
    )
    assert HOSTS == ("codex", "claude", "hermes")
    # Host identities the runtime actually admits (host_attempts.HOST_ATTEMPT_HOSTS).
    assert ATTEMPT_HOSTS == {"codex": "codex", "claude": "claude-code", "hermes": "hermes"}


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_cell_is_live_runtime_fail_closed(scenario: str, host: str, tmp_path: Path) -> None:
    result = run_scenario(scenario, host, tmp_path)

    assert result.scenario == scenario
    assert result.host == host
    assert result.status == "passed", result.detail
    # The failure path ends the run's completion claim: no false completion.
    assert result.false_completion is False
    # The observed disposition matches the runtime's canonical fail-closed reason.
    assert result.observed_reason == result.expected_reason
    # Honest provenance: no third-party host product binary was in the loop.
    assert result.host_process_invoked is False
    assert result.injection_transport
    assert result.cause


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize(
    "scenario", ["interruption", "provider_error", "stale_child", "artifact_tamper", "cross_workspace_isolation"]
)
def test_rejection_cells_never_mutate_canonical_state(scenario: str, host: str, tmp_path: Path) -> None:
    result = run_scenario(scenario, host, tmp_path)
    assert result.state_mutated is False, result.detail


def test_interruption_launcher_binding_differs_by_host(tmp_path: Path) -> None:
    for host, expected_binding in (("codex", "unknown_outcome"), ("claude", "unknown_outcome"), ("hermes", None)):
        result = run_scenario("interruption", host, tmp_path / host)
        assert result.evidence.get("launcher_binding_status") == expected_binding
        if expected_binding is None:
            assert "launcher_binding" in result.detail


def test_resume_cell_binds_resume_to_original_request_without_widening_authority(tmp_path: Path) -> None:
    for host in HOSTS:
        result = run_scenario("resume", host, tmp_path / host)
        evidence = result.evidence
        assert evidence["resume_ref_parent"] == evidence["request_ref"]
        assert evidence["request_payload_unchanged"] is True
        assert evidence["manifest_hosts"] == [host]
        assert result.observed_reason == "lifecycle_request_missing"


def test_stale_child_cell_records_all_three_rejections(tmp_path: Path) -> None:
    result = run_scenario("stale_child", "claude", tmp_path)
    assert result.expected_reason == "unknown_attempt+lease_expired+stale_revision"
    assert result.observed_reason == result.expected_reason


def test_cross_workspace_cell_rejects_every_cross_boundary_vector(tmp_path: Path) -> None:
    result = run_scenario("cross_workspace_isolation", "hermes", tmp_path)
    assert result.expected_reason == ("capture_reference_invalid+host_path_escape_rejected+cross_workspace_run_absent")


def test_artifact_tamper_cell_detects_cas_and_digest_tampering(tmp_path: Path) -> None:
    result = run_scenario("artifact_tamper", "codex", tmp_path)
    assert result.expected_reason == "cas_digest_mismatch+checkpoint_digest_mismatch"
    assert result.evidence["tampered_byte_changed"] is True
    assert result.evidence["read_before_tamper"] is True


def test_receipt_mirrors_harness_result_contract(tmp_path: Path) -> None:
    cells = [run_scenario(scenario, "codex", tmp_path) for scenario in ("interruption", "resume")]
    receipt = build_receipt(cells)
    assert receipt["schema_version"] == 1
    assert receipt["case_id"] == "host-matrix-v1"
    assert receipt["status"] == "passed"
    assert receipt["blocker"] is None
    assert receipt["replay"] == {"status": "passed", "divergences": []}
    assert [cell["name"] for cell in receipt["cells"]] == ["interruption:codex", "resume:codex"]
    for cell in receipt["cells"]:
        assert set(("name", "status", "detail", "identities", "events")) <= set(cell)
        matrix = cell["matrix"]
        assert matrix["scenario"] and matrix["host"]
        assert matrix["injection_transport"]
        assert matrix["host_process_invoked"] is False
        assert matrix["false_completion"] is False


def test_run_matrix_runs_cells_and_writes_receipt(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipts" / "host-matrix.json"
    receipt = run_matrix(
        tmp_path / "cells", hosts=("codex",), scenarios=("interruption", "resume"), result_path=receipt_path
    )
    assert receipt["status"] == "passed"
    assert len(receipt["cells"]) == 2
    written = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert written == receipt
    assert receipt_path.parent.is_dir()


def test_runner_executes_filtered_matrix_and_emits_receipt(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workspace",
            str(tmp_path / "cells"),
            "--result",
            str(result_path),
            "--hosts",
            "claude",
            "--scenarios",
            "interruption",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(result_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "passed"
    assert [cell["name"] for cell in receipt["cells"]] == ["interruption:claude"]
