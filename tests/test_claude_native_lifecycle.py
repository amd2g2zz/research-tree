from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from research_tree.lifecycle_hook import observe
from research_tree.project_workspace import initialize_project_run, write_installed_hook_launcher


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "native_execution_adapter.py"


def _run(*arguments: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ADAPTER), *arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _execution_run(tmp_path: Path, task_id: str = "agent-task") -> tuple[Path, dict[str, object]]:
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "schema": 1,
                "kind": "alignment-handoff",
                "run_id": "alignment-run",
                "alignment_digest": "a" * 64,
                "compiled_graph_digest": "a" * 64,
                "decision_slots": {"slot-agent": {"question": "Bind Claude children."}},
                "execution_context": {"authority": ["Read-only Agent probe."]},
            }
        ),
        encoding="utf-8",
    )
    initialized = _run(
        "--host",
        "claude",
        "--workspace",
        str(tmp_path),
        "init",
        "--project-id",
        "issue243",
        "--run-id",
        "run-243",
        "--handoff",
        str(handoff),
    )
    assert initialized.returncode == 0, initialized.stderr
    added = _run(
        "--host",
        "claude",
        "--workspace",
        str(tmp_path),
        "add-task",
        "--run-id",
        "run-243",
        "--task-id",
        task_id,
        "--decision-slot",
        "slot-agent",
        "--phase",
        "landscape",
        "--artifact",
        f"findings/{task_id}.json",
    )
    assert added.returncode == 0, added.stderr
    return tmp_path, json.loads(initialized.stdout)


def _start(tmp_path: Path, task_id: str = "agent-task") -> dict[str, object]:
    completed = _run(
        "--host", "claude", "--workspace", str(tmp_path), "start", "--run-id", "run-243", "--task-id", task_id
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _bind(tmp_path: Path, task_id: str, agent_id: str, attempt_id: str) -> subprocess.CompletedProcess[str]:
    return _run(
        "--host",
        "claude",
        "--workspace",
        str(tmp_path),
        "bind-agent",
        "--run-id",
        "run-243",
        "--task-id",
        task_id,
        "--attempt-id",
        attempt_id,
        "--agent-id",
        agent_id,
        "--session-id",
        "session-parent",
        "--causation-id",
        "tool-use-parent",
    )


def _hook_payload(tmp_path: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "cwd": str(tmp_path),
        "hook_event_name": "SubagentStop",
        "project_id": "issue243",
        "run_id": "run-243",
        "task_id": "agent-task",
        "attempt_id": "attempt-1",
        "agent_id": "agent-child-1",
        "session_id": "session-parent",
        "causation_id": "tool-use-parent",
        "stop_reason": "completed",
    }
    payload.update(overrides)
    return payload


def test_claude_subagent_stop_preserves_identity_and_binds_active_lease(tmp_path: Path) -> None:
    workspace, _state = _execution_run(tmp_path)
    task = _start(workspace)
    payload = _hook_payload(workspace, attempt_id=str(task["attempt_id"]))

    observed = observe(payload, host="claude", event="SubagentStop", project_root=workspace, process_cwd=workspace)
    record = json.loads((workspace / observed["path"]).read_text(encoding="utf-8"))
    assert record["binding_status"] == "candidate"
    assert tuple(record[key] for key in ("task_id", "attempt_id", "agent_id", "session_id", "causation_id")) == (
        "agent-task",
        task["attempt_id"],
        "agent-child-1",
        "session-parent",
        "tool-use-parent",
    )

    bound = _bind(workspace, "agent-task", "agent-child-1", str(task["attempt_id"]))
    assert bound.returncode == 0, bound.stderr
    binding = json.loads(bound.stdout)
    assert binding["agent_id"] == "agent-child-1"
    assert binding["attempt_id"] == task["attempt_id"]
    assert _run("--host", "claude", "--workspace", str(workspace), "status", "--run-id", "run-243").returncode == 0

    recovered = _run("--host", "claude", "--workspace", str(workspace), "recover", "--run-id", "run-243")
    assert recovered.returncode == 0, recovered.stderr
    restarted = _start(workspace)
    duplicate = _bind(workspace, "agent-task", "agent-child-1", str(restarted["attempt_id"]))
    assert duplicate.returncode == 1
    assert "agent identity is already bound" in duplicate.stderr


def test_unmatched_claude_stop_is_unknown_and_never_completes(tmp_path: Path) -> None:
    workspace, _state = _execution_run(tmp_path)
    _start(workspace)
    payload = _hook_payload(workspace, task_id=None, attempt_id=None, agent_id=None, causation_id=None)

    observed = observe(payload, host="claude", event="SubagentStop", project_root=workspace, process_cwd=workspace)
    record = json.loads((workspace / observed["path"]).read_text(encoding="utf-8"))
    summary = json.loads(
        _run("--host", "claude", "--workspace", str(workspace), "status", "--run-id", "run-243").stdout
    )
    assert record["binding_status"] == "unknown_outcome"
    assert summary["complete"] is False and summary["observed_complete"] is False


def test_installed_claude_hook_launcher_preserves_sanitized_identity(tmp_path: Path) -> None:
    workspace = initialize_project_run(tmp_path, project_id="issue243", run_id="run-243", host="claude")
    launcher = write_installed_hook_launcher(workspace)
    payload = _hook_payload(tmp_path, prompt="secret", tool_input={"secret": "value"})

    completed = subprocess.run(
        [sys.executable, str(launcher)],
        cwd=tmp_path,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    record = json.loads(next((workspace.run_root / "events").glob("*.json")).read_text(encoding="utf-8"))
    assert record["event"] == "SubagentStop"
    assert record["binding_status"] == "candidate"
    assert record["agent_id"] == "agent-child-1"
    assert "prompt" not in record and "tool_input" not in record

    completed = subprocess.run(
        [sys.executable, str(launcher)],
        cwd=tmp_path,
        input=json.dumps(
            payload
            | {
                "hook_event_name": "PostToolUse",
                "tool_name": "Agent",
                "tool_response": {"agentId": "agent-live-child"},
                "tool_use_id": "tool-use-live",
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    records = sorted((workspace.run_root / "events").glob("*.json"))
    post_tool = json.loads(records[-1].read_text(encoding="utf-8"))
    assert post_tool["binding_status"] == "host_identity_recorded"
    assert post_tool["agent_id"] == "agent-live-child"
    assert post_tool["causation_id"] == "tool-use-live"


def test_claude_post_agent_hook_records_host_identity_without_payload(tmp_path: Path) -> None:
    workspace, _state = _execution_run(tmp_path)
    task = _start(workspace)
    payload = {
        "cwd": str(workspace),
        "hook_event_name": "PostToolUse",
        "tool_name": "Agent",
        "tool_input": {"prompt": "secret"},
        "tool_response": {"agentId": "agent-live-child", "status": "completed"},
        "tool_use_id": "tool-use-live",
        "project_id": "issue243",
        "run_id": "run-243",
        "session_id": "session-parent",
    }

    observed = observe(payload, host="claude", event="PostToolUse", project_root=workspace, process_cwd=workspace)
    record = json.loads((workspace / observed["path"]).read_text(encoding="utf-8"))
    assert record["binding_status"] == "host_identity_recorded"
    assert record["agent_id"] == "agent-live-child"
    assert record["causation_id"] == "tool-use-live"
    assert "tool_input" not in record and "tool_response" not in record
    assert task["status"] == "running"


def test_claude_agent_workflow_and_hybrid_modes_are_independent() -> None:
    from research_tree.host_capabilities import HostCapabilityError, probe_host, project_workflow

    available = {
        "native_dynamic_workflow": "available",
        "dynamic_delegation": "available",
        "parallel_workers": "available",
        "lifecycle_hooks": "available",
        "background_execution": "available",
        "durable_resume": "available",
        "scheduled_drain": "available",
        "structured_event_transport": "available",
        "claude-agent-children": "available",
        "claude-native-workflow": "unavailable",
        "claude-hybrid-workflow": "unavailable",
    }
    probe = probe_host("claude-code", available)
    request = {
        "workflow_id": "workflow-agent",
        "script_id": "script-agent",
        "run_id": "run-243",
        "run_revision": 1,
        "strategy_revision": "strategy-1",
        "permission_profile": "read-only",
        "checkpoint_contract": "analysis-checkpoint-v1",
        "execution_mode": "agent",
        "max_phases": 2,
        "max_children": 2,
        "capability_probe": probe,
        "actions": ({"action_id": "action-a", "phase_id": "landscape", "dependencies": []},),
    }

    agent = project_workflow(request, "claude-code")
    assert probe["execution_modes"] == {
        "agent": "available",
        "workflow": "unavailable",
        "hybrid": "unavailable",
    }
    assert agent["execution_mode"] == "agent"
    assert agent["native_surface"] == "claude-agent-children"
    assert agent["workflow_evidence"] is None and agent["complete"] is False
    with pytest.raises(HostCapabilityError, match="claude-native-workflow is unavailable"):
        project_workflow(request | {"workflow_id": "workflow-invalid", "execution_mode": "workflow"}, "claude-code")

    workflow_available = probe_host(
        "claude-code", available | {"claude-native-workflow": "available", "claude-hybrid-workflow": "available"}
    )
    live = {
        "workflow_id": "wf-18ba89a7-913",
        "task_id": "wqv9knpd0",
        "script_id": "workflow-only-two-phases-wf-18ba89a7-913",
        "script_sha256": "10b780cb68154eb106344f74ddf0fe07d1dc92d08cf4bd8e440c5547d376fa2f",
        "run_id": "run-243",
        "phase_ids": ("phase-1", "phase-2"),
        "child_ids": (),
        "receipt_ref": ".research-tree/verification-runs/issue-243/agent-live/workflow-only-stream.jsonl",
    }
    workflow = project_workflow(
        request
        | {
            "workflow_id": "workflow-live",
            "execution_mode": "workflow",
            "capability_probe": workflow_available,
            "live_workflow": live,
        },
        "claude-code",
    )
    assert workflow["native_surface"] == "claude-dynamic-phases"
    assert workflow["workflow_evidence"]["phase_ids"] == ["phase-1", "phase-2"]
    with pytest.raises(HostCapabilityError, match="hybrid live workflow evidence requires child identities"):
        project_workflow(
            request
            | {
                "workflow_id": "workflow-hybrid-invalid",
                "execution_mode": "hybrid",
                "capability_probe": workflow_available,
                "live_workflow": live,
            },
            "claude-code",
        )
    hybrid = project_workflow(
        request
        | {
            "workflow_id": "workflow-hybrid",
            "execution_mode": "hybrid",
            "capability_probe": workflow_available,
            "live_workflow": live
            | {
                "workflow_id": "wf-279bcfe1-d21",
                "task_id": "wyiqtnuua",
                "script_id": "bounded-two-phase-probe-wf-279bcfe1-d21",
                "script_sha256": "ed99b102189d466c6d3fa9210112bc38a0195f5e8ab04cbbfc65105cde9fb2df",
                "phase_ids": ("phase-1", "replan", "phase-2"),
                "child_ids": ("a18775f000ea68d2d", "a03429889e9f9c949", "acbf3b6a492196feb"),
            },
        },
        "claude-code",
    )
    assert hybrid["native_surface"] == "claude-hybrid-workflow"
    assert len(hybrid["workflow_evidence"]["child_ids"]) == 3


def test_claude_finding_submission_requires_exact_active_binding(tmp_path: Path) -> None:
    workspace, _state = _execution_run(tmp_path, "finding-task")
    task = _start(workspace, "finding-task")
    artifact = tmp_path / "findings" / "finding-task.json"
    artifact.parent.mkdir()
    artifact.write_text(
        json.dumps(
            {
                "id": "finding-agent-task",
                "work_item_id": "finding-task",
                "decision_slot_id": "slot-agent",
                "attempt_id": task["attempt_id"],
                "phase": "landscape",
                "observations": [
                    {
                        "claim": "The live child returned the bounded answer.",
                        "anchor": {
                            "kind": "experiment",
                            "ref": ".research-tree/verification-runs/issue-243/agent-live/green-stream.jsonl",
                        },
                        "applicability": "Claude Agent live probe",
                        "confidence": "high",
                        "limitation": "The no-tool answer does not generalize to tool-using children.",
                    }
                ],
                "option_effects": [{"option": "agent-bound", "effect": "supports"}],
                "implementation_implications": [],
                "remaining_uncertainties": [],
            }
        ),
        encoding="utf-8",
    )
    unbound = _run(
        "--host",
        "claude",
        "--workspace",
        str(workspace),
        "finish",
        "--run-id",
        "run-243",
        "--task-id",
        "finding-task",
        "--result",
        "submitted",
    )
    assert unbound.returncode == 1
    assert "exact active agent binding" in unbound.stderr

    bound = _bind(workspace, "finding-task", "agent-live-child", str(task["attempt_id"]))
    assert bound.returncode == 0, bound.stderr
    submitted = _run(
        "--host",
        "claude",
        "--workspace",
        str(workspace),
        "finish",
        "--run-id",
        "run-243",
        "--task-id",
        "finding-task",
        "--result",
        "submitted",
    )
    assert submitted.returncode == 0, submitted.stderr
    assert json.loads(submitted.stdout)["status"] == "submitted"
