from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "native_execution_adapter.py"


def write_handoff(workspace: Path) -> Path:
    path = workspace / "handoff.json"
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "kind": "alignment-handoff",
                "run_id": "alignment-run",
                "decision_slots": {
                    "slot-a": {"question": "Primary decision"},
                    "slot-b": {"question": "Secondary decision"},
                },
                "execution_context": {
                    "authority": ["Autonomous research only; no target edits."],
                    "success_oracles": ["All P0 decisions are independently validated."],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def write_reports(workspace: Path) -> tuple[Path, Path]:
    technical = workspace / "technical-research-package.md"
    technical.write_text(
        "# Technical Research Package\n\n## Evidence\n\n## Validation\n" + "x" * 1100,
        encoding="utf-8",
    )
    human = workspace / "human-research-report.md"
    human.write_text(
        "# Human Research Report\n\n## Findings\n\n" + "x" * 600,
        encoding="utf-8",
    )
    return technical, human


def run_adapter(
    workspace: Path, host: str, command: str, *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--host",
            host,
            "--workspace",
            str(workspace),
            command,
            *args,
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )


def finding(
    task_id: str, slot: str, phase: str, attempt_id: str
) -> dict[str, object]:
    return {
        "id": f"finding-{task_id}",
        "work_item_id": task_id,
        "decision_slot_id": slot,
        "attempt_id": attempt_id,
        "phase": phase,
        "observations": [
            {
                "claim": "The inspected source supports the claim.",
                "anchor": {
                    "kind": "source",
                    "ref": "https://example.test/source",
                },
                "applicability": "Current representative fixture.",
                "confidence": "high",
                "limitation": "Not independently replicated.",
            }
        ],
        "option_effects": [{"option": "candidate-a", "effect": "supports"}],
        "implementation_implications": [],
        "remaining_uncertainties": [],
    }


@pytest.mark.parametrize("host", ["codex", "claude"])
def test_adapter_runs_dependency_wave_and_completes(tmp_path: Path, host: str) -> None:
    run_id = f"{host}-run"
    technical, human = write_reports(tmp_path)
    assert run_adapter(
        tmp_path, host, "init", "--run-id", run_id,
        "--handoff", str(write_handoff(tmp_path)),
    ).returncode == 0
    first = run_adapter(
        tmp_path,
        host,
        "add-task",
        "--run-id",
        run_id,
        "--task-id",
        "landscape-1",
        "--decision-slot",
        "slot-a",
        "--phase",
        "landscape",
        "--artifact",
        "findings/landscape-1.json",
    )
    assert first.returncode == 0, first.stderr
    second = run_adapter(
        tmp_path,
        host,
        "add-task",
        "--run-id",
        run_id,
        "--task-id",
        "validation-1",
        "--decision-slot",
        "slot-a",
        "--phase",
        "validation",
        "--artifact",
        "findings/validation-1.json",
        "--depends-on",
        "landscape-1",
    )
    assert second.returncode == 0, second.stderr

    initial = json.loads(run_adapter(tmp_path, host, "status", "--run-id", run_id).stdout)
    assert initial["ready"] == ["landscape-1"]
    assert initial["complete"] is False

    started = run_adapter(
        tmp_path,
        host,
        "start",
        "--run-id",
        run_id,
        "--task-id",
        "landscape-1",
        "--worker-id",
        "worker-1",
    )
    assert started.returncode == 0, started.stderr
    first_attempt_id = json.loads(started.stdout)["attempt_id"]
    recovered = json.loads(
        run_adapter(tmp_path, host, "recover", "--run-id", run_id).stdout
    )
    assert recovered["recovered_to_unknown"] == ["landscape-1"]

    restarted = run_adapter(
        tmp_path,
        host,
        "start",
        "--run-id",
        run_id,
        "--task-id",
        "landscape-1",
    )
    restarted_task = json.loads(restarted.stdout)
    assert restarted_task["attempt"] == 2
    artifact = tmp_path / "findings" / "landscape-1.json"
    artifact.parent.mkdir()
    artifact.write_text(
        json.dumps(
            finding("landscape-1", "slot-a", "landscape", first_attempt_id)
        ),
        encoding="utf-8",
    )
    stale = run_adapter(
        tmp_path,
        host,
        "finish",
        "--run-id",
        run_id,
        "--task-id",
        "landscape-1",
        "--result",
        "submitted",
    )
    assert stale.returncode == 1
    assert "active attempt" in stale.stderr
    artifact.write_text(
        json.dumps(
            finding(
                "landscape-1",
                "slot-a",
                "landscape",
                restarted_task["attempt_id"],
            )
        ),
        encoding="utf-8",
    )
    finished = run_adapter(
        tmp_path,
        host,
        "finish",
        "--run-id",
        run_id,
        "--task-id",
        "landscape-1",
        "--result",
        "submitted",
    )
    assert finished.returncode == 0, finished.stderr
    assert json.loads(finished.stdout)["status"] == "submitted"
    submitted = json.loads(
        run_adapter(tmp_path, host, "status", "--run-id", run_id).stdout
    )
    assert submitted["counts"]["submitted"] == 1
    assert submitted["ready"] == []
    assert submitted["complete"] is False
    assert run_adapter(
        tmp_path,
        host,
        "complete",
        "--run-id",
        run_id,
        "--technical-report",
        str(technical),
        "--human-report",
        str(human),
    ).returncode == 1
    unchecked = run_adapter(
        tmp_path,
        host,
        "verify",
        "--run-id",
        run_id,
        "--task-id",
        "landscape-1",
        "--reviewer-id",
        "coordinator",
        "--review-note",
        "No anchor was actually checked.",
    )
    assert unchecked.returncode == 1
    assert "missing anchors" in unchecked.stderr
    verified = run_adapter(
        tmp_path,
        host,
        "verify",
        "--run-id",
        run_id,
        "--task-id",
        "landscape-1",
        "--reviewer-id",
        "coordinator",
        "--review-note",
        "Opened the cited source and checked the atomic observation.",
        "--checked-anchor",
        "https://example.test/source",
    )
    assert verified.returncode == 0, verified.stderr
    mid = json.loads(run_adapter(tmp_path, host, "status", "--run-id", run_id).stdout)
    assert mid["ready"] == ["validation-1"]

    validation_start = run_adapter(
        tmp_path, host, "start", "--run-id", run_id, "--task-id", "validation-1"
    )
    assert validation_start.returncode == 0
    validation_task = json.loads(validation_start.stdout)
    validation = tmp_path / "findings" / "validation-1.json"
    validation.write_text(
        json.dumps(
            finding(
                "validation-1",
                "slot-a",
                "validation",
                validation_task["attempt_id"],
            )
        ),
        encoding="utf-8",
    )
    assert run_adapter(
        tmp_path,
        host,
        "finish",
        "--run-id",
        run_id,
        "--task-id",
        "validation-1",
        "--result",
        "submitted",
    ).returncode == 0
    assert run_adapter(
        tmp_path,
        host,
        "verify",
        "--run-id",
        run_id,
        "--task-id",
        "validation-1",
        "--reviewer-id",
        "coordinator",
        "--review-note",
        "Reproduced the validation evidence and checked limitations.",
        "--checked-anchor",
        "https://example.test/source",
    ).returncode == 0
    completed = run_adapter(
        tmp_path,
        host,
        "complete",
        "--run-id",
        run_id,
        "--technical-report",
        str(technical),
        "--human-report",
        str(human),
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["complete"] is True

    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    cascaded = json.loads(
        run_adapter(tmp_path, host, "recover", "--run-id", run_id).stdout
    )
    assert cascaded["recovered_to_unknown"] == ["landscape-1", "validation-1"]
    reopened = json.loads(
        run_adapter(tmp_path, host, "status", "--run-id", run_id).stdout
    )
    assert reopened["status"] == "running"
    assert reopened["ready"] == ["landscape-1"]


def test_adapter_rejects_invalid_finding_and_detects_tampering(tmp_path: Path) -> None:
    run_id = "integrity-run"
    run_adapter(
        tmp_path, "codex", "init", "--run-id", run_id,
        "--handoff", str(write_handoff(tmp_path)),
    )
    run_adapter(
        tmp_path,
        "codex",
        "add-task",
        "--run-id",
        run_id,
        "--task-id",
        "task-1",
        "--decision-slot",
        "slot-a",
        "--phase",
        "deep_dive",
        "--artifact",
        "finding.json",
    )
    run_adapter(
        tmp_path,
        "codex",
        "add-task",
        "--run-id",
        run_id,
        "--task-id",
        "task-2",
        "--decision-slot",
        "slot-b",
        "--phase",
        "validation",
        "--artifact",
        "finding-2.json",
        "--depends-on",
        "task-1",
    )
    started = run_adapter(
        tmp_path, "codex", "start", "--run-id", run_id, "--task-id", "task-1"
    )
    attempt_id = json.loads(started.stdout)["attempt_id"]
    artifact = tmp_path / "finding.json"
    artifact.write_text("{}", encoding="utf-8")
    invalid = run_adapter(
        tmp_path,
        "codex",
        "finish",
        "--run-id",
        run_id,
        "--task-id",
        "task-1",
        "--result",
        "submitted",
    )
    assert invalid.returncode == 1
    assert "Finding Pack" in invalid.stderr

    artifact.write_text(
        json.dumps(finding("task-1", "slot-a", "deep_dive", attempt_id)),
        encoding="utf-8",
    )
    assert run_adapter(
        tmp_path,
        "codex",
        "finish",
        "--run-id",
        run_id,
        "--task-id",
        "task-1",
        "--result",
        "submitted",
    ).returncode == 0
    assert run_adapter(
        tmp_path,
        "codex",
        "verify",
        "--run-id",
        run_id,
        "--task-id",
        "task-1",
        "--reviewer-id",
        "coordinator",
        "--review-note",
        "Checked the source anchor and applicability.",
        "--checked-anchor",
        "https://example.test/source",
    ).returncode == 0
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    summary = json.loads(
        run_adapter(tmp_path, "codex", "status", "--run-id", run_id).stdout
    )
    assert summary["complete"] is False
    assert summary["integrity_errors"] == ["task-1: artifact hash mismatch"]
    assert summary["ready"] == []
    assert summary["recovery_required"] == ["task-1"]

    recovered = json.loads(
        run_adapter(tmp_path, "codex", "recover", "--run-id", run_id).stdout
    )
    assert recovered["recovered_to_unknown"] == ["task-1"]
    after_recovery = json.loads(
        run_adapter(tmp_path, "codex", "status", "--run-id", run_id).stdout
    )
    assert after_recovery["ready"] == ["task-1"]
    restarted = json.loads(
        run_adapter(
            tmp_path,
            "codex",
            "start",
            "--run-id",
            run_id,
            "--task-id",
            "task-1",
        ).stdout
    )
    assert restarted["attempt"] == 2
    artifact.write_text(
        json.dumps(
            finding("task-1", "slot-a", "deep_dive", restarted["attempt_id"])
        ),
        encoding="utf-8",
    )
    assert run_adapter(
        tmp_path,
        "codex",
        "finish",
        "--run-id",
        run_id,
        "--task-id",
        "task-1",
        "--result",
        "submitted",
    ).returncode == 0
    assert run_adapter(
        tmp_path,
        "codex",
        "verify",
        "--run-id",
        run_id,
        "--task-id",
        "task-1",
        "--reviewer-id",
        "coordinator",
        "--review-note",
        "Rechecked the source after recovery.",
        "--checked-anchor",
        "https://example.test/source",
    ).returncode == 0
    final = json.loads(
        run_adapter(tmp_path, "codex", "status", "--run-id", run_id).stdout
    )
    assert final["ready"] == ["task-2"]
    assert final["integrity_errors"] == []


def test_adapter_rejects_artifacts_outside_workspace(tmp_path: Path) -> None:
    run_adapter(
        tmp_path, "claude", "init", "--run-id", "safe-run",
        "--handoff", str(write_handoff(tmp_path)),
    )
    outside = tmp_path.parent / "outside.json"
    completed = run_adapter(
        tmp_path,
        "claude",
        "add-task",
        "--run-id",
        "safe-run",
        "--task-id",
        "task-1",
        "--decision-slot",
        "slot-a",
        "--phase",
        "landscape",
        "--artifact",
        str(outside),
    )
    assert completed.returncode == 1
    assert "inside the workspace" in completed.stderr


def test_adapter_requires_handoff_and_rejects_unknown_decision_slot(tmp_path: Path) -> None:
    missing = run_adapter(tmp_path, "codex", "init", "--run-id", "missing-handoff")
    assert missing.returncode != 0
    assert "--handoff" in missing.stderr

    initialized = run_adapter(
        tmp_path, "codex", "init", "--run-id", "bound-run",
        "--handoff", str(write_handoff(tmp_path)),
    )
    assert initialized.returncode == 0, initialized.stderr
    state = json.loads(initialized.stdout)
    assert state["execution_context"]["authority"] == [
        "Autonomous research only; no target edits."
    ]
    rejected = run_adapter(
        tmp_path,
        "codex",
        "add-task",
        "--run-id",
        "bound-run",
        "--task-id",
        "task-x",
        "--decision-slot",
        "slot-not-confirmed",
        "--phase",
        "landscape",
        "--artifact",
        "finding-x.json",
    )
    assert rejected.returncode == 1
    assert "confirmed handoff" in rejected.stderr
