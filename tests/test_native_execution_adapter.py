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
                "alignment_digest": "a" * 64,
                "compiled_graph_digest": "a" * 64,
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


def run_adapter(workspace: Path, host: str, command: str, *args: str) -> subprocess.CompletedProcess[str]:
    if command == "init" and "--project-id" not in args:
        args = ("--project-id", f"project-{host}", *args)
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


def write_lifecycle_observation(
    workspace: Path,
    host: str,
    run_id: str,
    agent_id: str,
    session_id: str,
    lease_id: str,
) -> None:
    events_root = workspace / ".research-tree" / "projects" / f"project-{host}" / "runs" / run_id / "events"
    events_root.mkdir(parents=True, exist_ok=True)
    (events_root / f"{agent_id}-{session_id}-{lease_id}.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "source": "research-tree-lifecycle-hook",
                "host": host,
                "event": "SubagentStart",
                "agent_id": agent_id,
                "session_id": session_id,
                "attempt_id": lease_id,
            }
        ),
        encoding="utf-8",
    )


def bind_claude(workspace: Path, host: str, run_id: str, task: dict[str, object]) -> None:
    agent_id = f"agent-{task['attempt_id']}"
    attempt_id = str(task["attempt_id"])
    write_lifecycle_observation(workspace, host, run_id, agent_id, "session-test", attempt_id)
    completed = run_adapter(
        workspace,
        host,
        "bind-agent",
        "--run-id",
        run_id,
        "--task-id",
        str(task["task_id"]),
        "--attempt-id",
        attempt_id,
        "--agent-id",
        agent_id,
        "--session-id",
        "session-test",
        "--causation-id",
        f"tool-{task['attempt_id']}",
    )
    assert completed.returncode == 0, completed.stderr


def review_args(
    workspace: Path,
    host: str,
    run_id: str,
    task_id: str,
    artifact: Path,
    *,
    reviewer_id: str = "agent-reviewer",
    session_id: str = "session-reviewer",
    lease_id: str = "lease-reviewer",
) -> tuple[str, ...]:
    custody = workspace / "review-custody" / f"{task_id}-{reviewer_id}.json"
    custody.parent.mkdir(parents=True, exist_ok=True)
    custody.write_bytes(artifact.read_bytes())
    write_lifecycle_observation(workspace, host, run_id, reviewer_id, session_id, lease_id)
    return (
        "--reviewer-id",
        reviewer_id,
        "--reviewer-host",
        host,
        "--reviewer-session-id",
        session_id,
        "--reviewer-lease-id",
        lease_id,
        "--review-custody",
        str(custody),
    )


def finding(task_id: str, slot: str, phase: str, attempt_id: str) -> dict[str, object]:
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
        "validation_result": {
            "status": "passed",
            "oracle": "The anchored source remains reproducible.",
            "evidence_ref": "https://example.test/source",
        },
    }


@pytest.mark.parametrize("host", ["codex", "claude"])
def test_adapter_runs_dependency_wave_and_completes(tmp_path: Path, host: str) -> None:
    run_id = f"{host}-run"
    technical, human = write_reports(tmp_path)
    initialized = run_adapter(
        tmp_path,
        host,
        "init",
        "--run-id",
        run_id,
        "--handoff",
        str(write_handoff(tmp_path)),
    )
    assert initialized.returncode == 0, initialized.stderr
    assert not (tmp_path / ".research-tree-native" / run_id).exists()
    assert (tmp_path / ".research-tree" / "projects" / f"project-{host}" / "runs" / run_id / "state.json").is_file()
    assert json.loads(initialized.stdout)["lifecycle_hooks"] == "available"
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
    recovered = json.loads(run_adapter(tmp_path, host, "recover", "--run-id", run_id).stdout)
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
    bind_claude(tmp_path, host, run_id, restarted_task)
    assert restarted_task["attempt"] == 2
    artifact = tmp_path / "findings" / "landscape-1.json"
    artifact.parent.mkdir()
    artifact.write_text(
        json.dumps(finding("landscape-1", "slot-a", "landscape", first_attempt_id)),
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
    submitted = json.loads(run_adapter(tmp_path, host, "status", "--run-id", run_id).stdout)
    assert submitted["counts"]["submitted"] == 1
    assert submitted["ready"] == []
    assert submitted["complete"] is False
    assert (
        run_adapter(
            tmp_path,
            host,
            "complete",
            "--run-id",
            run_id,
            "--technical-report",
            str(technical),
            "--human-report",
            str(human),
        ).returncode
        == 1
    )
    unchecked = run_adapter(
        tmp_path,
        host,
        "verify",
        "--run-id",
        run_id,
        "--task-id",
        "landscape-1",
        *review_args(tmp_path, host, run_id, "landscape-1", artifact),
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
        *review_args(tmp_path, host, run_id, "landscape-1", artifact),
        "--review-note",
        "Opened the cited source and checked the atomic observation.",
        "--checked-anchor",
        "https://example.test/source",
    )
    assert verified.returncode == 0, verified.stderr
    mid = json.loads(run_adapter(tmp_path, host, "status", "--run-id", run_id).stdout)
    assert mid["ready"] == ["validation-1"]

    validation_start = run_adapter(tmp_path, host, "start", "--run-id", run_id, "--task-id", "validation-1")
    assert validation_start.returncode == 0
    validation_task = json.loads(validation_start.stdout)
    bind_claude(tmp_path, host, run_id, validation_task)
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
    assert (
        run_adapter(
            tmp_path,
            host,
            "finish",
            "--run-id",
            run_id,
            "--task-id",
            "validation-1",
            "--result",
            "submitted",
        ).returncode
        == 0
    )
    assert (
        run_adapter(
            tmp_path,
            host,
            "verify",
            "--run-id",
            run_id,
            "--task-id",
            "validation-1",
            *review_args(tmp_path, host, run_id, "validation-1", validation),
            "--review-note",
            "Reproduced the validation evidence and checked limitations.",
            "--checked-anchor",
            "https://example.test/source",
        ).returncode
        == 0
    )
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
    completed_summary = json.loads(completed.stdout)
    assert completed_summary["complete"] is False
    assert completed_summary["observed_complete"] is True
    assert completed_summary["status"] == "delivery_pending"
    assert completed_summary["completion_authority"] == "coordinator_only"

    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    cascaded = json.loads(run_adapter(tmp_path, host, "recover", "--run-id", run_id).stdout)
    assert cascaded["recovered_to_unknown"] == ["landscape-1", "validation-1"]
    reopened = json.loads(run_adapter(tmp_path, host, "status", "--run-id", run_id).stdout)
    assert reopened["status"] == "running"
    assert reopened["ready"] == ["landscape-1"]


def test_adapter_rejects_invalid_finding_and_detects_tampering(tmp_path: Path) -> None:
    run_id = "integrity-run"
    run_adapter(
        tmp_path,
        "codex",
        "init",
        "--run-id",
        run_id,
        "--handoff",
        str(write_handoff(tmp_path)),
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
    started = run_adapter(tmp_path, "codex", "start", "--run-id", run_id, "--task-id", "task-1")
    started_task = json.loads(started.stdout)
    attempt_id = started_task["attempt_id"]
    bind_claude(tmp_path, "codex", run_id, started_task)
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
    assert (
        run_adapter(
            tmp_path,
            "codex",
            "finish",
            "--run-id",
            run_id,
            "--task-id",
            "task-1",
            "--result",
            "submitted",
        ).returncode
        == 0
    )
    assert (
        run_adapter(
            tmp_path,
            "codex",
            "verify",
            "--run-id",
            run_id,
            "--task-id",
            "task-1",
            *review_args(tmp_path, "codex", run_id, "task-1", artifact),
            "--review-note",
            "Checked the source anchor and applicability.",
            "--checked-anchor",
            "https://example.test/source",
        ).returncode
        == 0
    )
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    summary = json.loads(run_adapter(tmp_path, "codex", "status", "--run-id", run_id).stdout)
    assert summary["complete"] is False
    assert summary["integrity_errors"] == ["task-1: artifact hash mismatch"]
    assert summary["ready"] == []
    assert summary["recovery_required"] == ["task-1"]

    recovered = json.loads(run_adapter(tmp_path, "codex", "recover", "--run-id", run_id).stdout)
    assert recovered["recovered_to_unknown"] == ["task-1"]
    after_recovery = json.loads(run_adapter(tmp_path, "codex", "status", "--run-id", run_id).stdout)
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
    bind_claude(tmp_path, "codex", run_id, restarted)
    artifact.write_text(
        json.dumps(finding("task-1", "slot-a", "deep_dive", restarted["attempt_id"])),
        encoding="utf-8",
    )
    assert (
        run_adapter(
            tmp_path,
            "codex",
            "finish",
            "--run-id",
            run_id,
            "--task-id",
            "task-1",
            "--result",
            "submitted",
        ).returncode
        == 0
    )
    assert (
        run_adapter(
            tmp_path,
            "codex",
            "verify",
            "--run-id",
            run_id,
            "--task-id",
            "task-1",
            *review_args(tmp_path, "codex", run_id, "task-1", artifact),
            "--review-note",
            "Rechecked the source after recovery.",
            "--checked-anchor",
            "https://example.test/source",
        ).returncode
        == 0
    )
    final = json.loads(run_adapter(tmp_path, "codex", "status", "--run-id", run_id).stdout)
    assert final["ready"] == ["task-2"]
    assert final["integrity_errors"] == []


def test_adapter_rejects_artifacts_outside_workspace(tmp_path: Path) -> None:
    run_adapter(
        tmp_path,
        "claude",
        "init",
        "--run-id",
        "safe-run",
        "--handoff",
        str(write_handoff(tmp_path)),
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
        tmp_path,
        "codex",
        "init",
        "--run-id",
        "bound-run",
        "--handoff",
        str(write_handoff(tmp_path)),
    )
    assert initialized.returncode == 0, initialized.stderr
    state = json.loads(initialized.stdout)
    assert state["execution_context"]["authority"] == ["Autonomous research only; no target edits."]
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


def test_adapter_rejects_stale_handoff_before_creating_execution_state(tmp_path: Path) -> None:
    handoff = write_handoff(tmp_path)
    payload = json.loads(handoff.read_text(encoding="utf-8"))
    payload["compiled_graph_digest"] = "b" * 64
    handoff.write_text(json.dumps(payload), encoding="utf-8")

    rejected = run_adapter(
        tmp_path,
        "codex",
        "init",
        "--run-id",
        "stale-handoff-run",
        "--handoff",
        str(handoff),
    )

    assert rejected.returncode == 1
    assert "stale alignment confirmation" in rejected.stderr
    assert not list(tmp_path.glob(".research-tree/projects/*/runs/stale-handoff-run/state.json"))


def test_adapter_rejects_handoff_without_confirmation_digests(tmp_path: Path) -> None:
    handoff = write_handoff(tmp_path)
    payload = json.loads(handoff.read_text(encoding="utf-8"))
    payload.pop("alignment_digest")
    payload.pop("compiled_graph_digest")
    handoff.write_text(json.dumps(payload), encoding="utf-8")

    rejected = run_adapter(
        tmp_path,
        "codex",
        "init",
        "--run-id",
        "missing-confirmation-run",
        "--handoff",
        str(handoff),
    )

    assert rejected.returncode == 1
    assert "alignment confirmation digests" in rejected.stderr
    assert not list(tmp_path.glob(".research-tree/projects/*/runs/missing-confirmation-run/state.json"))


def test_host_event_uses_explicit_canonical_revision_not_local_state(tmp_path: Path) -> None:
    run_id = "canonical-revision-run"
    assert (
        run_adapter(
            tmp_path,
            "codex",
            "init",
            "--run-id",
            run_id,
            "--handoff",
            str(write_handoff(tmp_path)),
        ).returncode
        == 0
    )
    assert (
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
            "landscape",
            "--artifact",
            "finding.json",
        ).returncode
        == 0
    )
    started = run_adapter(
        tmp_path,
        "codex",
        "start",
        "--run-id",
        run_id,
        "--task-id",
        "task-1",
    )
    assert started.returncode == 0, started.stderr
    payload = tmp_path / "event.json"
    payload.write_text(json.dumps({"artifact_path": "reports/result.json"}), encoding="utf-8")
    emitted = run_adapter(
        tmp_path,
        "codex",
        "emit-event",
        "--run-id",
        run_id,
        "--task-id",
        "task-1",
        "--event-id",
        "event-canonical",
        "--kind",
        "observation",
        "--expected-revision",
        "77",
        "--sequence",
        "1",
        "--actor",
        "codex",
        "--payload",
        str(payload),
    )
    assert emitted.returncode == 0, emitted.stderr
    assert json.loads(emitted.stdout)["expected_revision"] == 77


def _codex_running_run(workspace: Path) -> tuple[str, dict]:
    run_id = "codex-bind-run"
    technical, human = write_reports(workspace)
    assert (
        run_adapter(
            workspace, "codex", "init", "--run-id", run_id, "--handoff", str(write_handoff(workspace))
        ).returncode
        == 0
    )
    assert (
        run_adapter(
            workspace,
            "codex",
            "add-task",
            "--run-id",
            run_id,
            "--task-id",
            "task-codex-1",
            "--decision-slot",
            "slot-a",
            "--phase",
            "landscape",
            "--artifact",
            str(technical),
        ).returncode
        == 0
    )
    started = run_adapter(
        workspace,
        "codex",
        "start",
        "--run-id",
        run_id,
        "--task-id",
        "task-codex-1",
        "--worker-id",
        "worker-codex",
    )
    assert started.returncode == 0, started.stderr
    return run_id, json.loads(started.stdout)


def _write_codex_hook_observation(
    workspace: Path,
    run_id: str,
    agent_id: str,
    *,
    session_id: str = "session-codex-1",
    attempt_id: str | None = None,
) -> None:
    events_root = workspace / ".research-tree" / "projects" / "project-codex" / "runs" / run_id / "events"
    events_root.mkdir(parents=True, exist_ok=True)
    (events_root / "hook-codex-1.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "source": "research-tree-lifecycle-hook",
                "host": "codex",
                "event": "SubagentStart",
                "agent_id": agent_id,
                "session_id": session_id,
                "turn_id": "turn-codex-1",
                **({"attempt_id": attempt_id} if attempt_id is not None else {}),
            }
        ),
        encoding="utf-8",
    )


def test_codex_bind_agent_requires_observed_identity(tmp_path: Path) -> None:
    run_id, task = _codex_running_run(tmp_path)

    result = run_adapter(
        tmp_path,
        "codex",
        "bind-agent",
        "--run-id",
        run_id,
        "--task-id",
        "task-codex-1",
        "--attempt-id",
        str(task["attempt_id"]),
        "--agent-id",
        "agent-unobserved",
        "--session-id",
        "session-codex-1",
        "--causation-id",
        "tool-codex-1",
    )

    assert result.returncode == 1
    assert "observed" in (result.stdout + result.stderr).lower()


def test_codex_bind_agent_binds_observed_identity(tmp_path: Path) -> None:
    run_id, task = _codex_running_run(tmp_path)
    _write_codex_hook_observation(tmp_path, run_id, "agent-codex-live")

    result = run_adapter(
        tmp_path,
        "codex",
        "bind-agent",
        "--run-id",
        run_id,
        "--task-id",
        "task-codex-1",
        "--attempt-id",
        str(task["attempt_id"]),
        "--agent-id",
        "agent-codex-live",
        "--session-id",
        "session-codex-1",
        "--causation-id",
        "tool-codex-1",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    binding = json.loads(result.stdout)
    assert binding["agent_id"] == "agent-codex-live"
    assert binding["attempt_id"] == task["attempt_id"]


def test_codex_bind_agent_rejects_identity_reuse(tmp_path: Path) -> None:
    run_id, first = _codex_running_run(tmp_path)
    _write_codex_hook_observation(tmp_path, run_id, "agent-codex-live")
    ok = run_adapter(
        tmp_path,
        "codex",
        "bind-agent",
        "--run-id",
        run_id,
        "--task-id",
        "task-codex-1",
        "--attempt-id",
        str(first["attempt_id"]),
        "--agent-id",
        "agent-codex-live",
        "--session-id",
        "session-codex-1",
        "--causation-id",
        "tool-codex-1",
    )
    assert ok.returncode == 0

    second_start = run_adapter(tmp_path, "codex", "start", "--run-id", run_id, "--task-id", "task-codex-1")
    assert second_start.returncode == 1  # already running; reuse via new attempt path not modeled here

    stale = run_adapter(
        tmp_path,
        "codex",
        "bind-agent",
        "--run-id",
        run_id,
        "--task-id",
        "task-codex-1",
        "--attempt-id",
        str(first["attempt_id"]),
        "--agent-id",
        "agent-codex-live",
        "--session-id",
        "session-codex-1",
        "--causation-id",
        "tool-codex-2",
    )
    assert stale.returncode == 1


def test_adapter_records_only_an_independently_reviewed_submission(tmp_path: Path) -> None:
    run_id, task = _codex_running_run(tmp_path)
    worker_id = "agent-codex-worker"
    _write_codex_hook_observation(
        tmp_path,
        run_id,
        worker_id,
        attempt_id=str(task["attempt_id"]),
    )
    bound = run_adapter(
        tmp_path,
        "codex",
        "bind-agent",
        "--run-id",
        run_id,
        "--task-id",
        "task-codex-1",
        "--attempt-id",
        str(task["attempt_id"]),
        "--agent-id",
        worker_id,
        "--session-id",
        "session-codex-1",
        "--causation-id",
        "tool-codex-worker",
    )
    assert bound.returncode == 0, bound.stderr
    artifact = tmp_path / "technical-research-package.md"
    artifact.write_text(
        json.dumps(finding("task-codex-1", "slot-a", "landscape", str(task["attempt_id"]))),
        encoding="utf-8",
    )
    submitted = run_adapter(
        tmp_path,
        "codex",
        "finish",
        "--run-id",
        run_id,
        "--task-id",
        "task-codex-1",
        "--result",
        "submitted",
    )
    assert submitted.returncode == 0, submitted.stderr
    custody = tmp_path / "review-custody.json"
    custody.write_bytes(artifact.read_bytes())
    reviewer_id = "agent-codex-reviewer"
    reviewer_lease = "review-lease-1"
    _write_codex_hook_observation(
        tmp_path,
        run_id,
        reviewer_id,
        session_id="session-codex-reviewer",
        attempt_id=reviewer_lease,
    )

    base = (
        "verify",
        "--run-id",
        run_id,
        "--task-id",
        "task-codex-1",
        "--reviewer-id",
        reviewer_id,
        "--reviewer-host",
        "codex",
        "--reviewer-session-id",
        "session-codex-reviewer",
        "--reviewer-lease-id",
        reviewer_lease,
        "--review-custody",
        str(custody),
        "--review-note",
        "Checked an independently held copy of the evidence.",
        "--checked-anchor",
        "https://example.test/source",
    )
    cases = (
        ("--reviewer-id", worker_id, "independent reviewer"),
        ("--reviewer-session-id", "session-codex-1", "independent reviewer"),
        ("--reviewer-lease-id", str(task["attempt_id"]), "independent reviewer"),
        ("--reviewer-host", "claude", "same host"),
        ("--reviewer-id", "agent-forged", "observed"),
        ("--review-custody", str(artifact), "custody"),
    )
    for flag, value, message in cases:
        arguments = list(base)
        arguments[arguments.index(flag) + 1] = value
        rejected = run_adapter(tmp_path, "codex", *arguments)
        assert rejected.returncode == 1
        assert message in rejected.stderr

    verified = run_adapter(tmp_path, "codex", *base)
    assert verified.returncode == 0, verified.stderr
    reviewed_task = json.loads(verified.stdout)
    assert reviewed_task["status"] == "submitted"
    assert reviewed_task["worker_id"] == "worker-codex"
    state = json.loads(
        (
            tmp_path
            / ".research-tree"
            / "projects"
            / "project-codex"
            / "runs"
            / run_id
            / "state.json"
        ).read_text(encoding="utf-8")
    )
    assert state["tasks"]["task-codex-1"]["agent_id"] == worker_id
    summary = json.loads(run_adapter(tmp_path, "codex", "status", "--run-id", run_id).stdout)
    assert summary["complete"] is False
    assert summary["observed_complete"] is True
