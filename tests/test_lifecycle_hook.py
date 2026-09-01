from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest

from research_tree.lifecycle_hook import (
    DebugTraceError,
    LifecycleHookError,
    emit_trace,
    host_response,
    observe,
    read_payload,
)


def project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "packages").mkdir()
    (tmp_path / "skill-src").mkdir()
    return tmp_path


def project_run(root: Path) -> None:
    manifest = root / ".research-tree" / "projects" / "topic-1" / "runs" / "run-1" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"project_id":"topic-1","run_id":"run-1"}\n', encoding="utf-8")


def test_observe_records_only_sanitized_metadata(tmp_path: Path) -> None:
    root = project(tmp_path)
    project_run(root)
    payload = {
        "cwd": str(root),
        "hook_event_name": "SessionStart",
        "session_id": "session-1",
        "prompt": "must not be persisted",
        "tool_input": {"secret": "must not be persisted"},
        "project_id": "topic-1",
        "run_id": "run-1",
    }

    result = observe(
        payload,
        host="codex",
        event="SessionStart",
        project_root=root,
        process_cwd=root,
    )

    record = json.loads((root / result["path"]).read_text(encoding="utf-8"))
    assert record["host"] == "codex"
    assert record["event"] == "SessionStart"
    assert record["session_id"] == "session-1"
    assert record["workspace"] == "."
    assert "prompt" not in record
    assert "tool_input" not in record


def test_observe_rejects_reported_workspace_outside_project(tmp_path: Path) -> None:
    root = project(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(LifecycleHookError, match="reported cwd"):
        observe(
            {
                "cwd": str(outside),
                "hook_event_name": "SessionStart",
                "project_id": "topic-1",
                "run_id": "run-1",
            },
            host="claude",
            event="SessionStart",
            project_root=root,
            process_cwd=root,
        )


def test_observe_rejects_event_mismatch(tmp_path: Path) -> None:
    root = project(tmp_path)
    with pytest.raises(LifecycleHookError, match="does not match"):
        observe(
            {"cwd": str(root), "hook_event_name": "Stop"},
            host="codex",
            event="SessionStart",
            project_root=root,
            process_cwd=root,
        )


@pytest.mark.parametrize("host", ["codex", "claude"])
def test_reentrant_stop_is_not_recorded(tmp_path: Path, host: str) -> None:
    root = project(tmp_path)
    result = observe(
        {
            "cwd": str(root),
            "hook_event_name": "Stop",
            "stop_hook_active": True,
        },
        host=host,
        event="Stop",
        project_root=root,
        process_cwd=root,
    )
    assert result["status"] == "skipped_reentrant_stop"
    assert not (root / ".research-tree-hooks").exists()


def test_hermes_session_event_and_response(tmp_path: Path) -> None:
    root = project(tmp_path)
    project_run(root)
    result = observe(
        {"cwd": str(root), "hook_event_name": "on_session_start", "project_id": "topic-1", "run_id": "run-1"},
        host="hermes",
        event="on_session_start",
        project_root=root,
        process_cwd=root,
    )
    assert result["status"] == "recorded"
    assert host_response("hermes") == {}
    assert host_response("codex") == {"continue": True}


def test_unbound_hook_is_non_persistent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path)
    monkeypatch.delenv("RESEARCH_TREE_PROJECT_ID", raising=False)
    monkeypatch.delenv("RESEARCH_TREE_RUN_ID", raising=False)

    result = observe(
        {"cwd": str(root), "hook_event_name": "SessionStart"},
        host="codex",
        event="SessionStart",
        project_root=root,
        process_cwd=root,
    )

    assert result["status"] == "skipped_inactive"
    assert not (root / ".research-tree-hooks").exists()


def test_global_hook_uses_explicit_environment_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = project(tmp_path)
    project_run(root)
    monkeypatch.setenv("RESEARCH_TREE_PROJECT_ID", "topic-1")
    monkeypatch.setenv("RESEARCH_TREE_RUN_ID", "run-1")

    result = observe(
        {"cwd": str(root), "hook_event_name": "SessionStart"},
        host="codex",
        event="SessionStart",
        project_root=root,
        process_cwd=root,
    )

    assert result["status"] == "recorded"
    record = json.loads((root / result["path"]).read_text(encoding="utf-8"))
    assert record["project_id"] == "topic-1"
    assert record["run_id"] == "run-1"


def test_debug_hook_emits_a_sanitized_trace_without_changing_response(tmp_path: Path) -> None:
    root = project(tmp_path)
    project_run(root)
    result = observe(
        {"cwd": str(root), "hook_event_name": "SessionStart", "project_id": "topic-1", "run_id": "run-1"},
        host="codex",
        event="SessionStart",
        project_root=root,
        process_cwd=root,
        debug=True,
    )

    trace_path = next((root / ".research-tree-debug" / "events").glob("*.json"))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert result["status"] == "recorded"
    assert trace["phase"] == "lifecycle_observed"
    assert trace["codes"] == ["event:SessionStart"]


def test_trace_emits_only_structured_sanitized_fields(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = emit_trace(
        host="codex",
        phase="alignment_blocked",
        status="blocked",
        codes=("missing-success-oracle", "awaiting-authority"),
        run_id="run-1",
        project_root=root,
    )

    record = json.loads((root / result["path"]).read_text(encoding="utf-8"))
    assert record == {
        "schema": 1,
        "source": "research-tree-debug",
        "recorded_at": record["recorded_at"],
        "host": "codex",
        "phase": "alignment_blocked",
        "status": "blocked",
        "codes": ["missing-success-oracle", "awaiting-authority"],
        "run_id": "run-1",
    }
    assert "prompt" not in record
    assert "tool_input" not in record


def test_trace_accepts_alignment_turn_without_transcript_fields(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = emit_trace(
        host="hermes",
        phase="alignment_turn",
        status="completed",
        codes=("model-delta",),
        project_root=root,
    )

    record = json.loads((root / result["path"]).read_text(encoding="utf-8"))
    assert record["phase"] == "alignment_turn"
    assert record["codes"] == ["model-delta"]
    assert "response" not in record
    assert "prompt" not in record


def test_trace_rejects_free_form_codes(tmp_path: Path) -> None:
    root = project(tmp_path)
    with pytest.raises(DebugTraceError, match="debug code"):
        emit_trace(
            host="hermes",
            phase="worker_blocked",
            status="blocked",
            codes=("contains user prompt",),
            project_root=root,
        )


def test_read_payload_is_bounded_and_requires_an_object() -> None:
    assert read_payload(BytesIO(b'{"cwd":"/tmp"}')) == {"cwd": "/tmp"}
    with pytest.raises(LifecycleHookError, match="JSON object"):
        read_payload(BytesIO(b"[]"))


def test_host_templates_use_native_wrappers_and_isolated_hermes_hook() -> None:
    root = Path(__file__).resolve().parents[1]
    codex = json.loads((root / "hooks" / "codex.hooks.template.json").read_text(encoding="utf-8"))
    claude = json.loads((root / "hooks" / "claude-code.settings.template.json").read_text(encoding="utf-8"))
    hermes = (root / "hooks" / "hermes.config.template.yaml").read_text(encoding="utf-8")

    assert set(codex["hooks"]) == {
        "SessionStart",
        "SessionEnd",
        "UserPromptSubmit",
        "PreCompact",
        "PostCompact",
        "SubagentStart",
        "SubagentStop",
        "Stop",
    }
    assert set(claude["hooks"]) == {
        "SessionStart",
        "SessionEnd",
        "UserPromptSubmit",
        "PreCompact",
        "SubagentStop",
        "PostToolUse",
        "Stop",
    }
    assert "on_session_start:" in hermes
    assert "on_session_end:" in hermes
    for serialized in (json.dumps(codex), json.dumps(claude)):
        # Issue #453 defect 1: no uv dependency, launcher-based, shell-level fail-open.
        assert "uv run" not in serialized
        assert "--locked" not in serialized
        assert "lifecycle_hook_launcher.py" in serialized
        assert "|| exit 0" in serialized
        # Issue #453 defect 2: UserPromptSubmit is registered with the launcher.
        assert "UserPromptSubmit" in serialized
        assert "research_orchestrator" not in serialized
    assert "hermes_runtime_hook.py" in hermes
    assert "research-tree-hook" not in hermes
    assert "subagent_start:" in hermes
    assert "post_tool_call:" in hermes
    # Hermes has no user-prompt hook mechanism: N/A by design.
    assert "UserPromptSubmit" not in hermes
    assert "uv run" not in hermes
    assert "--locked" not in hermes


def test_codex_subagent_start_records_binding_candidate(tmp_path: Path) -> None:
    root = project(tmp_path)
    project_run(root)
    payload = {
        "cwd": str(root),
        "hook_event_name": "SubagentStart",
        "session_id": "session-parent",
        "turn_id": "turn-9",
        "tool_response": {"agentId": "agent-codex-child-1", "summary": "TOP SECRET child briefing"},
        "project_id": "topic-1",
        "run_id": "run-1",
    }

    result = observe(payload, host="codex", event="SubagentStart", project_root=root, process_cwd=root)

    assert result["status"] == "recorded"
    record = json.loads((root / result["path"]).read_text(encoding="utf-8"))
    assert record["event"] == "SubagentStart"
    assert record["agent_id"] == "agent-codex-child-1"
    assert record["binding_status"] == "candidate"
    serialized = json.dumps(record)
    assert "TOP SECRET" not in serialized


def test_codex_subagent_start_drops_malformed_identity(tmp_path: Path) -> None:
    root = project(tmp_path)
    project_run(root)
    payload = {
        "cwd": str(root),
        "hook_event_name": "SubagentStart",
        "tool_response": {"agentId": {"nested": "object"}},
        "project_id": "topic-1",
        "run_id": "run-1",
    }

    result = observe(payload, host="codex", event="SubagentStart", project_root=root, process_cwd=root)

    record = json.loads((root / result["path"]).read_text(encoding="utf-8"))
    assert "agent_id" not in record
    assert record.get("binding_status") == "unknown_outcome"


def test_codex_subagent_stop_records_completed_identity(tmp_path: Path) -> None:
    root = project(tmp_path)
    project_run(root)
    payload = {
        "cwd": str(root),
        "hook_event_name": "SubagentStop",
        "session_id": "session-parent",
        "tool_response": {"agentId": "agent-codex-child-1", "outcome": "completed"},
        "project_id": "topic-1",
        "run_id": "run-1",
    }

    result = observe(payload, host="codex", event="SubagentStop", project_root=root, process_cwd=root)

    record = json.loads((root / result["path"]).read_text(encoding="utf-8"))
    assert record["agent_id"] == "agent-codex-child-1"
    assert record["binding_status"] == "candidate"
