from __future__ import annotations

import hashlib
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

    # record-batch is fail-closed since the delegation lifecycle contract: a
    # missing Finding Pack is rejected rather than echoed.
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
    assert batch.returncode == 1
    assert "finding" in batch.stdout

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


def _write_finding(workspace: Path, name: str, body: dict) -> Path:
    path = workspace / name
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _write_hook_observation(tmp_path: Path, run_id: str, delegation_id: str = "deleg-observed") -> None:
    events_root = tmp_path / ".research-tree" / "projects" / "project-hermes" / "runs" / run_id / "events"
    events_root.mkdir(parents=True, exist_ok=True)
    (events_root / "hook-1.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "source": "research-tree-hermes-hook",
                "event": "post_tool_call",
                "tool_name": "delegate_task",
                "delegation_id": delegation_id,
                "task_id": "task-observed",
                "child_subagent_id": "child-observed",
                "agent_id": "child-observed",
                "task_count": 1,
            }
        ),
        encoding="utf-8",
    )


def test_record_batch_fails_closed_on_missing_finding(tmp_path: Path) -> None:
    run_adapter(tmp_path, "init", "--run-id", "hermes-run", "--handoff", str(write_handoff(tmp_path)))
    _write_hook_observation(tmp_path, "hermes-run")

    batch = run_adapter(
        tmp_path,
        "record-batch",
        "--run-id",
        "hermes-run",
        "--batch-id",
        "wave-1",
        "--status",
        "verified",
        "--delegation-id",
        "deleg-observed",
        "--finding",
        str(tmp_path / "missing-finding.json"),
    )
    assert batch.returncode == 1
    assert "finding" in batch.stdout


def test_record_batch_fails_closed_on_empty_finding(tmp_path: Path) -> None:
    run_adapter(tmp_path, "init", "--run-id", "hermes-run", "--handoff", str(write_handoff(tmp_path)))
    (tmp_path / "empty-finding.json").write_text("", encoding="utf-8")

    batch = run_adapter(
        tmp_path,
        "record-batch",
        "--run-id",
        "hermes-run",
        "--batch-id",
        "wave-1",
        "--status",
        "verified",
        "--finding",
        str(tmp_path / "empty-finding.json"),
    )
    assert batch.returncode == 1
    assert "finding" in batch.stdout


def test_record_batch_fails_closed_on_non_object_finding(tmp_path: Path) -> None:
    run_adapter(tmp_path, "init", "--run-id", "hermes-run", "--handoff", str(write_handoff(tmp_path)))
    (tmp_path / "array-finding.json").write_text("[]", encoding="utf-8")

    batch = run_adapter(
        tmp_path,
        "record-batch",
        "--run-id",
        "hermes-run",
        "--batch-id",
        "wave-1",
        "--status",
        "verified",
        "--finding",
        str(tmp_path / "array-finding.json"),
    )
    assert batch.returncode == 1
    assert "finding" in batch.stdout


def test_record_batch_rejects_unbound_delegation_identity(tmp_path: Path) -> None:
    run_adapter(tmp_path, "init", "--run-id", "hermes-run", "--handoff", str(write_handoff(tmp_path)))
    _write_hook_observation(tmp_path, "hermes-run")
    finding = _write_finding(tmp_path, "finding.json", {"schema": 1, "kind": "finding-pack"})

    batch = run_adapter(
        tmp_path,
        "record-batch",
        "--run-id",
        "hermes-run",
        "--batch-id",
        "wave-1",
        "--status",
        "verified",
        "--delegation-id",
        "deleg-invented",
        "--finding",
        str(finding),
    )
    assert batch.returncode == 1
    assert "identity" in batch.stdout or "delegation" in batch.stdout


def test_record_batch_accepts_observed_identity_with_intact_finding(tmp_path: Path) -> None:
    run_adapter(tmp_path, "init", "--run-id", "hermes-run", "--handoff", str(write_handoff(tmp_path)))
    _write_hook_observation(tmp_path, "hermes-run")
    finding = _write_finding(
        tmp_path,
        "finding.json",
        {"schema": 1, "kind": "finding-pack", "run_id": "hermes-run"},
    )

    batch = run_adapter(
        tmp_path,
        "record-batch",
        "--run-id",
        "hermes-run",
        "--batch-id",
        "wave-1",
        "--status",
        "verified",
        "--delegation-id",
        "deleg-observed",
        "--finding",
        str(finding),
    )
    assert batch.returncode == 0, batch.stdout + batch.stderr
    result = json.loads(batch.stdout)
    assert result["batch_status"] == "verified"
    assert result["delegation_ids"] == ["deleg-observed"]
    assert result["authoritative"] is False
    finding_sha = hashlib.sha256(finding.read_bytes()).hexdigest()
    assert result["finding_digests"][0] == finding_sha
