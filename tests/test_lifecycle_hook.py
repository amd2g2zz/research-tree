from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path

import pytest

from research_tree.lifecycle_hook import (
    LifecycleHookError,
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


def test_observe_records_only_sanitized_metadata(tmp_path: Path) -> None:
    root = project(tmp_path)
    payload = {
        "cwd": str(root),
        "hook_event_name": "SessionStart",
        "session_id": "session-1",
        "prompt": "must not be persisted",
        "tool_input": {"secret": "must not be persisted"},
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
            {"cwd": str(outside), "hook_event_name": "SessionStart"},
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


def test_claude_reentrant_stop_is_not_recorded(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = observe(
        {
            "cwd": str(root),
            "hook_event_name": "Stop",
            "stop_hook_active": True,
        },
        host="claude",
        event="Stop",
        project_root=root,
        process_cwd=root,
    )
    assert result["status"] == "skipped_reentrant_stop"
    assert not (root / ".research-tree-hooks").exists()


def test_hermes_session_event_and_response(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = observe(
        {"cwd": str(root), "hook_event_name": "on_session_start"},
        host="hermes",
        event="on_session_start",
        project_root=root,
        process_cwd=root,
    )
    assert result["status"] == "recorded"
    assert host_response("hermes") == {}
    assert host_response("codex") == {"continue": True}


def test_debug_hook_emits_a_sanitized_trace_without_changing_response(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = observe(
        {"cwd": str(root), "hook_event_name": "SessionStart"},
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


def test_read_payload_is_bounded_and_requires_an_object() -> None:
    assert read_payload(BytesIO(b'{"cwd":"/tmp"}')) == {"cwd": "/tmp"}
    with pytest.raises(LifecycleHookError, match="JSON object"):
        read_payload(BytesIO(b"[]"))


def test_host_templates_use_native_wrappers_and_isolated_hermes_hook() -> None:
    root = Path(__file__).resolve().parents[1]
    codex = json.loads(
        (root / "hooks" / "codex.hooks.template.json").read_text(encoding="utf-8")
    )
    claude = json.loads(
        (root / "hooks" / "claude-code.settings.template.json").read_text(
            encoding="utf-8"
        )
    )
    hermes = (root / "hooks" / "hermes.config.template.yaml").read_text(
        encoding="utf-8"
    )

    assert set(codex["hooks"]) == {"SessionStart", "Stop"}
    assert set(claude["hooks"]) == {"SessionStart", "Stop"}
    assert "on_session_start:" in hermes
    assert "on_session_end:" in hermes
    for serialized in (json.dumps(codex), json.dumps(claude)):
        assert "research-tree-hook" in serialized
        assert "research_orchestrator" not in serialized
    assert "hermes_runtime_hook.py" in hermes
    assert "research-tree-hook" not in hermes
    assert "subagent_start:" in hermes
    assert "post_tool_call:" in hermes
