from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "hermes_execution_adapter.py"


def run_adapter(workspace: Path, command: str, *args: str) -> subprocess.CompletedProcess[str]:
    if command == "init" and "--project-id" not in args:
        args = ("--project-id", "project-hermes", *args)
    return subprocess.run(
        [sys.executable, str(ADAPTER), "--workspace", str(workspace), command, *args],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )


def write_handoff(workspace: Path) -> Path:
    path = workspace / "handoff.json"
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "kind": "alignment-handoff",
                "run_id": "alignment-hermes",
                "decision_slots": {"slot-a": {"question": "Bound the decision."}},
                "execution_context": {"authority": ["Autonomous research within scope."]},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_legacy_commands_are_non_authoritative_observations(tmp_path: Path) -> None:
    run_id = "hermes-run"
    initialized = run_adapter(
        tmp_path,
        "init",
        "--run-id",
        run_id,
        "--handoff",
        str(write_handoff(tmp_path)),
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    init_result = json.loads(initialized.stdout)
    assert init_result["status"] == "observed"
    assert init_result["project_id"] == "project-hermes"
    assert init_result["lifecycle_hooks"] == "available"
    assert (tmp_path / ".research-tree" / "projects" / "project-hermes" / "runs" / run_id).is_dir()
    assert init_result["authoritative"] is False
    assert init_result["completion_authority"] == "coordinator_only"

    batch = run_adapter(
        tmp_path,
        "record-batch",
        "--run-id",
        run_id,
        "--batch-id",
        "wave-1",
        "--status",
        "verified",
        "--finding",
        str(tmp_path / "missing-finding.json"),
    )
    assert batch.returncode == 0, batch.stdout + batch.stderr
    batch_result = json.loads(batch.stdout)
    assert batch_result["status"] == "observed"
    assert batch_result["batch_status"] == "verified"
    assert batch_result["authoritative"] is False

    completed = run_adapter(
        tmp_path,
        "complete",
        "--run-id",
        run_id,
        "--technical-report",
        str(tmp_path / "missing-technical.md"),
        "--human-report",
        str(tmp_path / "missing-human.md"),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = json.loads(completed.stdout)
    assert summary == {
        "run_id": run_id,
        "status": "delivery_pending",
        "complete": False,
        "observed_complete": True,
        "completion_authority": "coordinator_only",
        "authoritative": False,
    }
    assert not (tmp_path / ".research-tree-hermes" / run_id / "state.json").exists()


def test_recover_requires_canonical_attempt_snapshot(tmp_path: Path) -> None:
    missing = run_adapter(tmp_path, "recover", "--run-id", "hermes-run")
    assert missing.returncode == 1
    assert "canonical attempt" in missing.stdout

    snapshot = tmp_path / "attempt.json"
    snapshot.write_text(
        json.dumps(
            {
                "run_id": "hermes-run",
                "action_id": "action-1",
                "attempt_id": "attempt-1",
                "expected_revision": 12,
                "next_sequence": 3,
                "authorized_methods": ["documentation"],
            }
        ),
        encoding="utf-8",
    )
    recovered = run_adapter(
        tmp_path,
        "recover",
        "--run-id",
        "hermes-run",
        "--canonical-attempt",
        str(snapshot),
        "--unknown-event-id",
        "unknown-1",
        "--retry-event-id",
        "retry-1",
        "--retry-category",
        "transient",
        "--method",
        "documentation",
        "--created-at",
        "2026-08-11T00:00:00+00:00",
    )
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    events = json.loads(recovered.stdout)["events"]
    assert [event["kind"] for event in events] == ["unknown_outcome", "retry"]
    assert [event["sequence"] for event in events] == [3, 4]
    assert not (tmp_path / ".research-tree-hermes" / "hermes-run" / "state.json").exists()
