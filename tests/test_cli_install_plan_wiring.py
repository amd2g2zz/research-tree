"""Issue #386: cli.py:_install must call plan_heterogeneous_install first.

Issue #328 (PR #330) shipped the data structure (``plan_heterogeneous_install``)
but the CLI ``_install`` handler still used the legacy ``install_skill`` +
``skill_status`` path.  ``plan_heterogeneous_install`` had 0 upstream
callers — the #328 acceptance was not actually delivered.  Issue #386 wires
``_install`` through the planner and dispatches per-entry by action.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from research_tree import cli


def _json_output(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    captured = capsys.readouterr()
    assert captured.err == ""
    return __import__("json").loads(captured.out)


def _install_arguments(tmp_path: Path, *, hosts: list[str], scope: str = "project") -> list[str]:
    return [
        "install",
        *[item for host in hosts for item in ("--host", host)],
        "--source",
        str(tmp_path / "src"),
        "--home",
        str(tmp_path / "home"),
        "--project-root",
        str(tmp_path / "project"),
        "--mode",
        "copy",
        "--scope",
        scope,
    ]


def test_install_mixed_hosts_uses_plan_heterogeneous(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mixed hosts: install entry → install_skill, skipped entry → dry-run payload."""

    plan_mock = MagicMock(
        return_value={
            "scope": "project",
            "mode": "copy",
            "dry_run": False,
            "aggregate_ready": False,
            "snippet_required": True,
            "snippet": {"yaml": "skills:\n  external_dirs:\n    - /tmp/src\n", "idempotent": True},
            "entries": [
                {
                    "host": "claude",
                    "scope": "project",
                    "mode": "copy",
                    "target": str(tmp_path / "project" / ".claude" / "skills" / "research-tree"),
                    "package": str(tmp_path / "src" / "packages" / "claude-code" / "research-tree"),
                    "skill_source": str(
                        tmp_path / "src" / "packages" / "claude-code" / "research-tree" / "skills" / "research-tree"
                    ),
                    "action": "install",
                    "discovery": "Claude Code personal/project skill discovery",
                    "rollback_boundary": str(tmp_path / "project" / ".claude" / "skills" / "research-tree"),
                    "required_config": None,
                    "reason": "install target=missing",
                },
                {
                    "host": "hermes",
                    "scope": "project",
                    "mode": "n/a",
                    "target": "n/a",
                    "package": str(tmp_path / "src" / "packages" / "hermes" / "research-tree"),
                    "skill_source": "n/a",
                    "action": "skipped",
                    "discovery": "Hermes primary skill directory",
                    "rollback_boundary": "n/a",
                    "required_config": {
                        "yaml": "skills:\n  external_dirs:\n    - /tmp/src\n",
                        "path": "/tmp/src",
                        "idempotent": True,
                        "source_parent": "/tmp/src",
                    },
                    "reason": "hermes has no native project scope; user scope or external_dirs required",
                },
            ],
        }
    )
    install_skill_mock = MagicMock(
        return_value={
            "repository": str(tmp_path / "src"),
            "scope": "project",
            "mode": "copy",
            "dry_run": False,
            "installations": [
                {
                    "host": "claude",
                    "scope": "project",
                    "mode": "copy",
                    "target": str(tmp_path / "project" / ".claude" / "skills" / "research-tree"),
                    "package": str(tmp_path / "src" / "packages" / "claude-code" / "research-tree"),
                    "skill_source": str(
                        tmp_path / "src" / "packages" / "claude-code" / "research-tree" / "skills" / "research-tree"
                    ),
                    "action": "installed",
                    "discovery": "Claude Code personal/project skill discovery",
                    "payload_files": ["SKILL.md"],
                }
            ],
            "hooks": [],
        }
    )

    monkeypatch.setattr(cli, "plan_heterogeneous_install", plan_mock)
    monkeypatch.setattr(cli, "install_skill", install_skill_mock)

    # partial readiness (hermes skipped) → exit code 4 (consistent with doctor/status)
    assert cli.main(_install_arguments(tmp_path, hosts=["claude", "hermes"], scope="project")) == 4
    payload = _json_output(capsys)

    # 1. Planner was called first
    assert plan_mock.call_count == 1
    plan_kwargs = plan_mock.call_args.kwargs
    assert plan_kwargs["hosts"] == ("claude", "hermes")
    assert plan_kwargs["scope"] == "project"

    # 2. install_skill dispatched only for the "install" entry (claude)
    assert install_skill_mock.call_count == 1
    install_kwargs = install_skill_mock.call_args
    assert install_kwargs.args[0] == ("claude",)
    assert install_kwargs.kwargs["scope"] == "project"

    # 3. Payload: aggregate readiness surfaced; skipped entry preserved with required_config
    assert payload["command"] == "install"
    assert payload["status"] == "partial"
    assert payload["readiness"]["ready"] is False
    assert any("hermes" in reason for reason in payload["readiness"]["failure_reasons"])

    result = payload["result"]
    assert result["aggregate_ready"] is False
    assert result["snippet_required"] is True

    by_host = {item["host"]: item for item in result["installations"]}
    assert by_host["claude"]["status"] == "current"
    assert by_host["claude"]["action"] == "installed"

    skipped = result["skipped_required_config"]
    assert len(skipped) == 1
    assert skipped[0]["host"] == "hermes"
    assert skipped[0]["required_config"]["idempotent"] is True
    assert "external_dirs" in skipped[0]["required_config"]["yaml"]


def test_install_hermes_only_with_required_config_returns_dry_run_payload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hermes-only on project scope: no install_skill call, required_config surfaced."""

    plan_mock = MagicMock(
        return_value={
            "scope": "project",
            "mode": "copy",
            "dry_run": True,
            "aggregate_ready": False,
            "snippet_required": True,
            "snippet": {"yaml": "skills:\n  external_dirs:\n    - /tmp/src\n", "idempotent": True},
            "entries": [
                {
                    "host": "hermes",
                    "scope": "project",
                    "mode": "n/a",
                    "target": "n/a",
                    "package": str(tmp_path / "src" / "packages" / "hermes" / "research-tree"),
                    "skill_source": "n/a",
                    "action": "skipped",
                    "discovery": "Hermes primary skill directory",
                    "rollback_boundary": "n/a",
                    "required_config": {
                        "yaml": "skills:\n  external_dirs:\n    - /tmp/src\n",
                        "path": "/tmp/src",
                        "idempotent": True,
                        "source_parent": "/tmp/src",
                    },
                    "reason": "hermes has no native project scope; user scope or external_dirs required",
                }
            ],
        }
    )
    install_skill_mock = MagicMock()

    monkeypatch.setattr(cli, "plan_heterogeneous_install", plan_mock)
    monkeypatch.setattr(cli, "install_skill", install_skill_mock)

    # partial readiness → exit code 4 (consistent with mixed-host partial)
    assert cli.main(_install_arguments(tmp_path, hosts=["hermes"], scope="project")) == 4
    payload = _json_output(capsys)

    # install_skill MUST NOT be called for skipped-only plans (issue #328 acceptance)
    assert install_skill_mock.call_count == 0
    assert plan_mock.call_count == 1

    # Payload exposes the required_config snippet and aggregate_ready=False
    result = payload["result"]
    assert result["aggregate_ready"] is False
    assert result["snippet_required"] is True
    assert result["skipped_required_config"][0]["required_config"]["idempotent"] is True
    assert "external_dirs" in result["skipped_required_config"][0]["required_config"]["yaml"]

    # No installations performed — installations list empty
    assert result["installations"] == []

    # Status reflects partial readiness (skipped host → not ready)
    assert payload["status"] == "partial"
    assert payload["readiness"]["ready"] is False
    assert any("hermes" in reason for reason in payload["readiness"]["failure_reasons"])


def test_install_current_action_returns_no_op_confirmation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-installed host: no install_skill call, current-status surfaced."""

    plan_mock = MagicMock(
        return_value={
            "scope": "user",
            "mode": "copy",
            "dry_run": False,
            "aggregate_ready": True,
            "snippet_required": False,
            "snippet": None,
            "entries": [
                {
                    "host": "codex",
                    "scope": "user",
                    "mode": "copy",
                    "target": str(tmp_path / "home" / ".codex" / "skills" / "research-tree"),
                    "package": str(tmp_path / "src" / "packages" / "codex" / "research-tree"),
                    "skill_source": str(tmp_path / "src" / "packages" / "codex" / "research-tree"),
                    "action": "current",
                    "discovery": "Codex Agent Skills user/repository discovery",
                    "rollback_boundary": str(tmp_path / "home" / ".codex" / "skills" / "research-tree"),
                    "required_config": None,
                    "reason": "install target=current",
                }
            ],
        }
    )
    install_skill_mock = MagicMock()

    monkeypatch.setattr(cli, "plan_heterogeneous_install", plan_mock)
    monkeypatch.setattr(cli, "install_skill", install_skill_mock)

    assert cli.main(_install_arguments(tmp_path, hosts=["codex"], scope="user")) == 0
    payload = _json_output(capsys)

    # install_skill MUST NOT be called when the host is already current
    assert install_skill_mock.call_count == 0
    assert plan_mock.call_count == 1

    result = payload["result"]
    assert result["aggregate_ready"] is True
    assert result["skipped_required_config"] == []

    # The current action is surfaced as a no-op confirmation
    by_host = {item["host"]: item for item in result["installations"]}
    assert by_host["codex"]["status"] == "current"
    assert by_host["codex"]["action"] == "current"
    assert by_host["codex"]["current"] is True

    # Status is installed because aggregate_ready=True
    assert payload["status"] == "installed"
    assert payload["readiness"] == {"ready": True, "failure_reasons": []}


def test_install_conflict_action_returns_failure_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Conflict action must surface as a SkillSetupError failure, not a partial install."""

    plan_mock = MagicMock(
        return_value={
            "scope": "user",
            "mode": "copy",
            "dry_run": False,
            "aggregate_ready": False,
            "snippet_required": False,
            "snippet": None,
            "entries": [
                {
                    "host": "codex",
                    "scope": "user",
                    "mode": "copy",
                    "target": str(tmp_path / "home" / ".codex" / "skills" / "research-tree"),
                    "package": str(tmp_path / "src" / "packages" / "codex" / "research-tree"),
                    "skill_source": str(tmp_path / "src" / "packages" / "codex" / "research-tree"),
                    "action": "conflict",
                    "discovery": "Codex Agent Skills user/repository discovery",
                    "rollback_boundary": str(tmp_path / "home" / ".codex" / "skills" / "research-tree"),
                    "required_config": None,
                    "reason": "link_target_mismatch",
                }
            ],
        }
    )
    install_skill_mock = MagicMock()

    monkeypatch.setattr(cli, "plan_heterogeneous_install", plan_mock)
    monkeypatch.setattr(cli, "install_skill", install_skill_mock)

    # Conflict must NOT proceed with install_skill
    assert cli.main(_install_arguments(tmp_path, hosts=["codex"], scope="user")) == 2
    assert install_skill_mock.call_count == 0

    captured = capsys.readouterr()
    import json as _json

    envelope = _json.loads(captured.out)
    assert envelope["code"].startswith("install_conflict")
    assert envelope["category"] == "invalid_input"
