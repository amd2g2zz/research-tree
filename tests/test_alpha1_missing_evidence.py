from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_missing_evidence_completion_replays_as_independent_task_lifecycle(
    tmp_path: Path,
) -> None:
    from evaluation.harness.alpha1_adversarial_missing_evidence import (
        replay_missing_evidence,
    )

    receipt = replay_missing_evidence(repository_root=ROOT, work_root=tmp_path)
    baseline = json.loads(
        (ROOT / "evaluation/baselines/alpha1-0.0.1-a1.json").read_text(
            encoding="utf-8"
        )
    )

    assert receipt["baseline"] == baseline["git"]
    assert receipt["host_package"] == baseline["host_packages"]["claude-code"]
    assert receipt["case_id"] == "missing-evidence"
    assert receipt["status"] == "vulnerability_reproduced"
    assert (
        receipt["semantic_predicate"]
        == "legacy_native_adapter_completed_run_after_unresolvable_review_anchor"
    )
    assert receipt["observed"] == {
        "evidence_anchor": "evidence/missing-experiment.json",
        "evidence_resolves": False,
        "finding_validation_result_present": False,
        "reviewed_task_status": "completed",
        "reviewed_task_verified": True,
        "run_complete": True,
        "run_status": "complete",
    }
    assert [command["name"] for command in receipt["commands"]] == [
        "init",
        "add-task",
        "start",
        "finish",
        "verify",
        "status",
        "complete",
    ]
    assert all(command["returncode"] == 0 for command in receipt["commands"])
    assert receipt["inputs"]["finding_template"]["bytes"] > 0
    assert receipt["inputs"]["finding"]["bytes"] > 0
    assert receipt["inputs"]["finding_template"] != receipt["inputs"]["finding"]
    assert receipt["inputs"]["handoff"]["bytes"] > 0
    assert receipt["inputs"]["technical"]["bytes"] >= 1024
    assert receipt["inputs"]["human"]["bytes"] >= 512
    assert receipt["observed"]["finding_validation_result_present"] is False
    assert "fix_confirmed" not in json.dumps(receipt)
    assert str(tmp_path) not in json.dumps(receipt)
    assert not (tmp_path / "alpha1-checkout").exists()
    assert not (tmp_path / "missing-evidence-workspace").exists()

    repeated = replay_missing_evidence(repository_root=ROOT, work_root=tmp_path)
    assert repeated["status"] == "vulnerability_reproduced"
    assert repeated["observed"]["evidence_resolves"] is False


def test_missing_evidence_cli_writes_redacted_receipt_and_cleans_by_default(
    tmp_path: Path,
) -> None:
    work_root = tmp_path / "work"
    receipt_path = tmp_path / "receipt.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evaluation.harness.alpha1_adversarial_missing_evidence",
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
    assert receipt["commands"][0]["stdout_sha256"]
    assert receipt["commands"][0]["stderr_sha256"]
    assert receipt["commands"][0]["redacted_stdout_sha256"]
    assert receipt["commands"][0]["redacted_stderr_sha256"]
    assert not (work_root / "alpha1-checkout").exists()
    assert not (work_root / "missing-evidence-workspace").exists()


def test_recorded_missing_evidence_receipt_binds_completion_to_absent_anchor() -> None:
    result = json.loads(
        (
            ROOT
            / "evaluation/results/alpha1-adversarial-v1/missing-evidence.json"
        ).read_text(encoding="utf-8")
    )
    baseline = json.loads(
        (ROOT / "evaluation/baselines/alpha1-0.0.1-a1.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["status"] == "vulnerability_reproduced"
    assert result["host_package"] == baseline["host_packages"]["claude-code"]
    assert result["semantic_predicate"].endswith(
        "completed_run_after_unresolvable_review_anchor"
    )
    assert result["observed"]["finding_validation_result_present"] is False
    assert result["observed"]["evidence_resolves"] is False
    assert result["observed"]["reviewed_task_verified"] is True
    assert result["observed"]["run_complete"] is True
    assert result["commands"][-1]["name"] == "complete"
    assert result["commands"][-1]["returncode"] == 0
    fixture = (
        ROOT
        / "evaluation/fixtures/alpha1-adversarial-v1/missing-evidence/finding.json"
    )
    fixture_bytes = fixture.read_bytes()
    assert result["inputs"]["finding_template"] == {
        "bytes": len(fixture_bytes),
        "sha256": hashlib.sha256(fixture_bytes).hexdigest(),
    }
    assert result["inputs"]["finding_template"] != result["inputs"]["finding"]
    assert "validation_result" not in json.loads(fixture_bytes)
    assert "/private/" not in json.dumps(result)
    assert "/tmp/research-tree-alpha1-missing-evidence" not in json.dumps(result)
    assert "fix_confirmed" not in json.dumps(result)


def test_missing_evidence_fixture_rejects_forged_validation_field_even_when_null(
    tmp_path: Path,
) -> None:
    from evaluation.harness.alpha1_adversarial_missing_evidence import (
        _load_missing_evidence_finding,
    )
    from evaluation.harness.alpha1_adversarial import Alpha1ReplayError

    finding = tmp_path / "finding.json"
    finding.write_text(json.dumps({"validation_result": None}), encoding="utf-8")

    try:
        _load_missing_evidence_finding(finding)
    except Alpha1ReplayError as error:
        assert "must not contain validation_result" in str(error)
    else:
        raise AssertionError("missing-evidence loader accepted forged validation field")


def test_missing_evidence_receipt_is_distinct_from_forged_validation() -> None:
    missing = json.loads(
        (
            ROOT
            / "evaluation/results/alpha1-adversarial-v1/missing-evidence.json"
        ).read_text(encoding="utf-8")
    )
    forged = json.loads(
        (
            ROOT
            / "evaluation/results/alpha1-adversarial-v1/forged-validation.json"
        ).read_text(encoding="utf-8")
    )

    assert missing["case_id"] != forged["case_id"]
    assert missing["semantic_predicate"] != forged["semantic_predicate"]
    assert "validation_status" not in missing["observed"]
    assert missing["observed"]["finding_validation_result_present"] is False
    assert "validate-finding" not in {
        command["name"] for command in missing["commands"]
    }
    assert [command["name"] for command in forged["commands"]] == [
        "validate-finding"
    ]
