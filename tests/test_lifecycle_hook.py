from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest

from research_tree.lifecycle_hook import (
    LifecycleHookError,
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
