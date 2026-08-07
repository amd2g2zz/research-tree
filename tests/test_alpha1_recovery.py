from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES = ("provider-failure", "crash-recovery")


def test_provider_failure_preserves_retryable_obligation_without_claiming_defect(
    tmp_path: Path,
) -> None:
    from evaluation.harness.alpha1_adversarial_recovery import replay_recovery_case

    receipt = replay_recovery_case(
        repository_root=ROOT,
        work_root=tmp_path,
        case_id="provider-failure",
    )

    assert receipt["case_id"] == "provider-failure"
    assert receipt["status"] == "pending"
    assert receipt["semantic_predicate"] == (
        "legacy_native_adapter_lost_provider_failed_obligation"
    )
    assert receipt["predicates"] == {
        "lost_obligation": {
            "holds": False,
            "predicate": "failed_task_absent_or_not_retryable_after_provider_failure",
        },
        "recovered_obligation": {
            "holds": True,
            "predicate": "failed_task_remains_ready_and_can_start_a_new_attempt",
        },
    }
    assert receipt["observed"]["failed_status"] == "failed"
    assert receipt["observed"]["failure_reason"] == "provider unavailable"
    assert receipt["observed"]["ready_after_failure"] == [
        "provider-failure-task"
    ]
    assert receipt["observed"]["retry_status"] == "running"
    assert receipt["observed"]["retry_attempt"] == 2
    assert receipt["observed"]["attempt_id_changed"] is True
    assert [command["name"] for command in receipt["commands"]] == [
        "init",
        "add-task",
        "start",
        "finish",
        "status",
        "start",
    ]
    assert all(command["returncode"] == 0 for command in receipt["commands"])
    assert str(tmp_path) not in json.dumps(receipt)
    assert not (tmp_path / "alpha1-checkout").exists()
    assert not (tmp_path / "provider-failure-workspace").exists()


def test_crash_recovery_reopens_in_flight_obligation_idempotently(
    tmp_path: Path,
) -> None:
    from evaluation.harness.alpha1_adversarial_recovery import replay_recovery_case

    receipt = replay_recovery_case(
        repository_root=ROOT,
        work_root=tmp_path,
        case_id="crash-recovery",
    )

    assert receipt["case_id"] == "crash-recovery"
    assert receipt["status"] == "pending"
    assert receipt["semantic_predicate"] == (
        "legacy_native_adapter_lost_in_flight_obligation_after_process_boundary"
    )
    assert receipt["predicates"] == {
        "lost_obligation": {
            "holds": False,
            "predicate": "in_flight_task_absent_or_not_retryable_after_recovery",
        },
        "recovered_obligation": {
            "holds": True,
            "predicate": "recover_reopens_in_flight_task_as_unknown_ready_for_retry",
        },
    }
    assert receipt["observed"]["first_recovery"] == ["crash-recovery-task"]
    assert receipt["observed"]["second_recovery"] == []
    assert receipt["observed"]["recovery_revision_stable"] is True
    assert receipt["observed"]["status_after_recovery"] == "running"
    assert receipt["observed"]["unknown_tasks_after_recovery"] == 1
    assert receipt["observed"]["ready_after_recovery"] == [
        "crash-recovery-task"
    ]
    assert receipt["observed"]["retry_status"] == "running"
    assert receipt["observed"]["retry_attempt"] == 2
    assert receipt["observed"]["attempt_id_changed"] is True
    assert [command["name"] for command in receipt["commands"]] == [
        "init",
        "add-task",
        "start",
        "recover",
        "recover",
        "status",
        "start",
    ]
    assert all(command["returncode"] == 0 for command in receipt["commands"])
    assert str(tmp_path) not in json.dumps(receipt)
    assert not (tmp_path / "alpha1-checkout").exists()
    assert not (tmp_path / "crash-recovery-workspace").exists()


@pytest.mark.parametrize("case_id", CASES)
def test_recovery_cli_writes_machine_receipt_and_cleans_by_default(
    tmp_path: Path,
    case_id: str,
) -> None:
    work_root = tmp_path / "work"
    receipt_path = tmp_path / f"{case_id}.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evaluation.harness.alpha1_adversarial_recovery",
            "--case",
            case_id,
            "--repository-root",
            str(ROOT),
            "--work-root",
            str(work_root),
            "--receipt",
            str(receipt_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout)
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt
    assert receipt["status"] == "pending"
    assert receipt["commands"][0]["raw_stdout_sha256"]
    assert receipt["commands"][0]["raw_stderr_sha256"]
    assert receipt["commands"][0]["redacted_stdout_sha256"]
    assert receipt["commands"][0]["redacted_stderr_sha256"]
    assert not (work_root / "alpha1-checkout").exists()
    assert not (work_root / f"{case_id}-workspace").exists()


@pytest.mark.parametrize("case_id", CASES)
def test_recorded_recovery_receipt_is_case_bound_and_truthful(case_id: str) -> None:
    result_path = (
        ROOT
        / "evaluation/results/alpha1-adversarial-v1/recovery"
        / f"{case_id}.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    baseline = json.loads(
        (ROOT / "evaluation/baselines/alpha1-0.0.1-a1.json").read_text(
            encoding="utf-8"
        )
    )
    fixture_path = (
        ROOT
        / "evaluation/fixtures/alpha1-adversarial-v1/recovery"
        / f"{case_id}.json"
    )
    fixture_bytes = fixture_path.read_bytes()

    assert result["case_id"] == case_id
    assert result["status"] == "pending"
    assert result["host_package"] == baseline["host_packages"]["claude-code"]
    assert result["inputs"]["case"] == {
        "bytes": len(fixture_bytes),
        "sha256": hashlib.sha256(fixture_bytes).hexdigest(),
    }
    assert result["predicates"]["lost_obligation"]["holds"] is False
    assert result["predicates"]["recovered_obligation"]["holds"] is True
    assert all(command["returncode"] == 0 for command in result["commands"])
    rendered = json.dumps(result)
    assert "/private/" not in rendered
    assert "/tmp/" not in rendered
    assert "vulnerability_reproduced" not in rendered
    assert "fix_confirmed" not in rendered


def test_recovery_cli_leaves_caller_owned_work_root_empty_by_default(tmp_path: Path) -> None:
    work_root = tmp_path / "work"
    receipt_path = tmp_path / "receipt.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evaluation.harness.alpha1_adversarial_recovery",
            "--case",
            "provider-failure",
            "--repository-root",
            str(ROOT),
            "--work-root",
            str(work_root),
            "--receipt",
            str(receipt_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert work_root.is_dir()
    assert tuple(work_root.iterdir()) == ()
