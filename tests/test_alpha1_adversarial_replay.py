from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_pinned_alpha1_hermes_accepts_a_filler_report_from_clean_checkout(tmp_path: Path) -> None:
    from evaluation.harness.alpha1_adversarial import replay_filler_report

    receipt = replay_filler_report(repository_root=ROOT, work_root=tmp_path)
    baseline = json.loads((ROOT / "evaluation/baselines/alpha1-0.0.1-a1.json").read_text())

    assert receipt["baseline"]["commit"] == "8ab91ea4eb55c98441b5ee6001b80922a56ecdd1"
    assert receipt["host"] == "hermes"
    assert receipt["status"] == "vulnerability_reproduced"
    assert receipt["semantic_predicate"] == "legacy_hermes_completed_heading_padding_reports"
    assert receipt["commands"][-1]["name"] == "complete"
    assert receipt["commands"][-1]["returncode"] == 0
    assert receipt["commands"][-1]["stdout"]
    assert str(tmp_path) not in receipt["commands"][-1]["command"]
    assert str(tmp_path) not in receipt["commands"][-1]["stdout"]
    assert receipt["observed"]["status"] == "complete"
    assert receipt["inputs"]["technical"]["bytes"] >= 1024
    assert receipt["inputs"]["human"]["bytes"] >= 512
    assert receipt["host_package"] == baseline["host_packages"]["hermes"]
    assert receipt["environment"]["implementation"] == sys.implementation.name
    assert receipt["limitations"] == ["baseline reproduction is not fix confirmation"]
    assert not (tmp_path / "alpha1-checkout").exists()
    assert not (tmp_path / "filler-report-workspace").exists()

    repeated = replay_filler_report(repository_root=ROOT, work_root=tmp_path)
    assert repeated["status"] == "vulnerability_reproduced"
    assert not (tmp_path / "alpha1-checkout").exists()
    assert not (tmp_path / "filler-report-workspace").exists()


def test_replay_failure_cleans_execution_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from evaluation.harness import alpha1_adversarial

    def fail_command(argv: list[str], *, cwd: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        return (
            subprocess.CompletedProcess(argv, 17, stdout="", stderr="synthetic failure"),
            {
                "argv": argv,
                "returncode": 17,
                "stdout": "",
                "stderr": "synthetic failure",
            },
        )

    monkeypatch.setattr(alpha1_adversarial, "_command", fail_command)

    with pytest.raises(alpha1_adversarial.Alpha1ReplayError, match="historical Hermes command failed"):
        alpha1_adversarial.replay_filler_report(repository_root=ROOT, work_root=tmp_path)

    assert not (tmp_path / "alpha1-checkout").exists()
    assert not (tmp_path / "filler-report-workspace").exists()


def _run_replay_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "evaluation.harness.alpha1_adversarial", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_replay_cli_writes_redacted_receipt_and_reuses_work_root(tmp_path: Path) -> None:
    work_root = tmp_path / "work"
    receipt_path = tmp_path / "receipt.json"

    first = _run_replay_cli(
        "--repository-root",
        str(ROOT),
        "--work-root",
        str(work_root),
        "--receipt",
        str(receipt_path),
    )

    assert first.returncode == 0, first.stderr
    result = json.loads(first.stdout)
    assert result["status"] == "vulnerability_reproduced"
    assert "fix_confirmed" not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)
    assert json.loads(receipt_path.read_text()) == result
    assert not (work_root / "alpha1-checkout").exists()
    assert not (work_root / "filler-report-workspace").exists()

    second = _run_replay_cli(
        "--repository-root",
        str(ROOT),
        "--work-root",
        str(work_root),
        "--receipt",
        str(tmp_path / "receipt-second.json"),
    )
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["status"] == "vulnerability_reproduced"


def test_replay_cli_keep_workspace_is_explicit(tmp_path: Path) -> None:
    work_root = tmp_path / "kept-work"
    result = _run_replay_cli(
        "--repository-root",
        str(ROOT),
        "--work-root",
        str(work_root),
        "--receipt",
        str(tmp_path / "kept-receipt.json"),
        "--keep-workspace",
    )

    assert result.returncode == 0, result.stderr
    assert (work_root / "filler-report-workspace").is_dir()
    assert not (work_root / "alpha1-checkout").exists()


def test_replay_cli_reports_nonzero_json_error_for_nonempty_work_root(tmp_path: Path) -> None:
    work_root = tmp_path / "occupied-work"
    work_root.mkdir()
    (work_root / "sentinel").write_text("preserve me")

    result = _run_replay_cli(
        "--repository-root",
        str(ROOT),
        "--work-root",
        str(work_root),
        "--receipt",
        str(tmp_path / "error-receipt.json"),
    )

    assert result.returncode != 0
    assert json.loads(result.stderr) == {"error": "work_root must be empty"}
    assert "Traceback" not in result.stderr
    assert (work_root / "sentinel").read_text() == "preserve me"


def test_recorded_filler_report_receipt_is_redacted_and_not_fix_confirmation() -> None:
    result = json.loads(
        (ROOT / "evaluation/results/alpha1-adversarial-v1/filler-report.json").read_text()
    )

    assert result["status"] == "vulnerability_reproduced"
    assert result["observed"]["status"] == "complete"
    assert result["host_package"]["path"] == "packages/hermes/research-tree"
    assert result["commands"][-1]["name"] == "complete"
    assert result["commands"][-1]["raw_stdout_sha256"] == result["commands"][-1]["stdout_sha256"]
    assert result["commands"][-1]["redacted_stdout_sha256"]
    assert result["commands"][-1]["raw_stderr_sha256"] == result["commands"][-1]["stderr_sha256"]
    assert result["commands"][-1]["redacted_stderr_sha256"]
    assert "<workspace>" in result["commands"][-1]["stdout"]
    assert "/private/" not in json.dumps(result)
    assert "fix_confirmed" not in json.dumps(result)


def test_pinned_alpha1_native_adapter_accepts_forged_validation_without_resolvable_evidence(
    tmp_path: Path,
) -> None:
    from evaluation.harness.alpha1_adversarial_forged_validation import (
        replay_forged_validation,
    )

    receipt = replay_forged_validation(repository_root=ROOT, work_root=tmp_path)

    assert receipt["baseline"]["commit"] == "8ab91ea4eb55c98441b5ee6001b80922a56ecdd1"
    assert receipt["host"] == "claude"
    assert receipt["status"] == "vulnerability_reproduced"
    assert receipt["semantic_predicate"] == (
        "legacy_native_adapter_accepted_passed_validation_with_unresolvable_evidence"
    )
    assert receipt["observed"] == {
        "validation_status": "passed",
        "evidence_ref": "evidence/not-present.json",
        "evidence_resolves": False,
    }
    assert receipt["commands"][-1]["name"] == "validate-finding"
    assert receipt["commands"][-1]["returncode"] == 0
    assert receipt["commands"][-1]["stdout"]
    assert str(tmp_path) not in json.dumps(receipt)
    assert "fix_confirmed" not in json.dumps(receipt)
    assert receipt["host_package"]["path"] == "packages/claude-code/research-tree"
    assert receipt["inputs"]["finding"]["bytes"] > 0
    assert not (tmp_path / "alpha1-checkout").exists()
    assert not (tmp_path / "forged-validation-workspace").exists()


def test_forged_validation_cli_writes_redacted_semantic_receipt(tmp_path: Path) -> None:
    work_root = tmp_path / "work"
    receipt_path = tmp_path / "receipt.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evaluation.harness.alpha1_adversarial_forged_validation",
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
    assert json.loads(receipt_path.read_text()) == receipt
    assert receipt["observed"]["evidence_resolves"] is False
    assert receipt["commands"][0]["stdout_sha256"]
    assert receipt["commands"][0]["stderr_sha256"]
    assert receipt["commands"][0]["raw_stdout_sha256"] == receipt["commands"][0]["stdout_sha256"]
    assert receipt["commands"][0]["redacted_stdout_sha256"]
    assert str(tmp_path) not in json.dumps(receipt)
    assert not (work_root / "alpha1-checkout").exists()
    assert not (work_root / "forged-validation-workspace").exists()


def test_recorded_forged_validation_receipt_has_resolvable_oracle_metadata() -> None:
    result = json.loads(
        (ROOT / "evaluation/results/alpha1-adversarial-v1/forged-validation.json").read_text()
    )
    baseline = json.loads((ROOT / "evaluation/baselines/alpha1-0.0.1-a1.json").read_text())

    assert result["status"] == "vulnerability_reproduced"
    assert result["host_package"] == baseline["host_packages"]["claude-code"]
    assert result["observed"]["validation_status"] == "passed"
    assert result["observed"]["evidence_resolves"] is False
    assert result["commands"][0]["name"] == "validate-finding"
    assert result["commands"][0]["returncode"] == 0
    assert result["commands"][0]["stdout_sha256"]
    assert result["commands"][0]["stderr_sha256"]
    assert "/private/" not in json.dumps(result)
    assert "fix_confirmed" not in json.dumps(result)


def test_replay_cli_help_describes_caller_owned_work_root_cleanup() -> None:
    completed = _run_replay_cli("--help")

    assert completed.returncode == 0
    assert "caller-owned" in completed.stdout
    assert "left empty" in completed.stdout
