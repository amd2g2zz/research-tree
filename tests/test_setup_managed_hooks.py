from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

from research_tree.lifecycle_hook import observe
from research_tree.skill_setup import SkillSetupError, install_skill, resolve_skill_source, skill_status


ROOT = Path(__file__).resolve().parents[1]


def _commands(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    commands: list[str] = []
    for entries in payload["hooks"].values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                command = hook.get("command")
                if isinstance(command, str):
                    commands.append(command)
    return commands


def test_setup_install_deploys_global_hooks_and_preserves_host_configuration(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    codex_config = home / ".codex" / "hooks.json"
    claude_config = home / ".claude" / "settings.json"
    hermes_config = home / ".hermes" / "config.yaml"
    codex_config.parent.mkdir(parents=True)
    claude_config.parent.mkdir(parents=True)
    hermes_config.parent.mkdir(parents=True)
    codex_config.write_text(
        json.dumps({"custom": True, "hooks": {"SessionStart": [{"command": "keep"}]}}),
        encoding="utf-8",
    )
    claude_config.write_text(json.dumps({"custom": {"theme": "dark"}}), encoding="utf-8")
    hermes_config.write_text('model: "example/model"\n', encoding="utf-8")

    result = install_skill(
        ("codex", "claude", "hermes"),
        source=ROOT,
        scope="user",
        mode="copy",
        home=home,
        project_root=project,
    )

    assert {item["status"] for item in result["hooks"]} == {"current"}
    assert {item["action"] for item in result["hooks"]} == {"installed"}
    assert json.loads(codex_config.read_text(encoding="utf-8"))["custom"] is True
    assert json.loads(claude_config.read_text(encoding="utf-8"))["custom"] == {"theme": "dark"}
    assert 'model: "example/model"' in hermes_config.read_text(encoding="utf-8")
    for host, config in (("codex", codex_config), ("claude", claude_config)):
        commands = [command for command in _commands(config) if "research-tree-hook" in command]
        assert commands
        assert all(f"--host {host}" in command for command in commands)
        assert all(str(ROOT) in command for command in commands)
    hermes_text = hermes_config.read_text(encoding="utf-8")
    assert hermes_text.count("# research-tree-setup managed") == 7
    assert str(home / ".hermes" / "skills" / "research-tree" / "scripts" / "hermes_runtime_hook.py") in hermes_text


def test_hermes_global_hook_preserves_unrelated_hook_entries(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config = home / ".hermes" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "hooks:\n"
        "  on_session_start:\n"
        "    - command: 'keep-existing-hook'\n"
        "      timeout: 3\n"
        "hooks_auto_accept: true\n",
        encoding="utf-8",
    )

    install_skill(
        ("hermes",),
        source=ROOT,
        scope="user",
        mode="copy",
        home=home,
        project_root=tmp_path / "project",
    )

    text = config.read_text(encoding="utf-8")
    assert "keep-existing-hook" in text
    assert "hooks_auto_accept: true" in text
    assert text.count("# research-tree-setup managed") == 7


def test_hermes_tampered_marker_is_repaired_without_duplicate_command(tmp_path: Path) -> None:
    home = tmp_path / "home"
    install_skill(
        ("hermes",),
        source=ROOT,
        scope="user",
        mode="copy",
        home=home,
        project_root=tmp_path / "project",
    )
    config = home / ".hermes" / "config.yaml"
    text = config.read_text(encoding="utf-8").replace("    # research-tree-setup managed\n", "", 1)
    config.write_text(text, encoding="utf-8")

    stale = skill_status(
        ("hermes",),
        source=ROOT,
        scope="user",
        home=home,
        project_root=tmp_path / "project",
    )["installations"][0]
    assert stale["hook_status"] == "conflict"

    install_skill(
        ("hermes",),
        source=ROOT,
        scope="user",
        mode="copy",
        home=home,
        project_root=tmp_path / "project",
    )
    repaired = config.read_text(encoding="utf-8")
    launcher = str(home / ".hermes" / "skills" / "research-tree" / "scripts" / "hermes_runtime_hook.py")
    assert repaired.count(launcher) == 7
    assert repaired.count("# research-tree-setup managed") == 7


def test_global_hook_skips_when_research_tree_is_not_active(tmp_path: Path) -> None:
    result = observe(
        {"cwd": str(tmp_path), "hook_event_name": "SessionStart"},
        host="codex",
        event="SessionStart",
        process_cwd=tmp_path,
    )

    assert result == {
        "status": "skipped_inactive",
        "host": "codex",
        "event": "SessionStart",
    }
    assert not (tmp_path / ".research-tree").exists()


def test_setup_hook_install_is_idempotent_and_project_scope_still_uses_global_config(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    first = install_skill(
        ("codex",),
        source=ROOT,
        scope="project",
        mode="copy",
        home=home,
        project_root=project,
    )
    second = install_skill(
        ("codex",),
        source=ROOT,
        scope="project",
        mode="copy",
        home=home,
        project_root=project,
    )

    config = home / ".codex" / "hooks.json"
    commands = [command for command in _commands(config) if "research-tree-hook" in command]
    assert len(commands) == 7
    assert first["hooks"][0]["action"] == "installed"
    assert second["hooks"][0]["action"] == "unchanged"
    assert not (project / ".codex" / "hooks.json").exists()


def test_setup_dry_run_reports_hooks_without_writing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    result = install_skill(
        ("codex", "claude", "hermes"),
        source=ROOT,
        scope="user",
        mode="copy",
        home=home,
        project_root=tmp_path / "project",
        dry_run=True,
    )

    assert {item["action"] for item in result["hooks"]} == {"planned"}
    assert not home.exists()


def test_setup_preflights_all_hook_configs_before_writing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    codex_config = home / ".codex" / "hooks.json"
    claude_config = home / ".claude" / "settings.json"
    codex_config.parent.mkdir(parents=True)
    claude_config.parent.mkdir(parents=True)
    original = '{"custom":true}\n'
    codex_config.write_text(original, encoding="utf-8")
    claude_config.write_text("[]", encoding="utf-8")

    with pytest.raises(SkillSetupError, match="hook configuration"):
        install_skill(
            ("codex", "claude"),
            source=ROOT,
            scope="user",
            mode="copy",
            home=home,
            project_root=tmp_path / "project",
        )

    assert codex_config.read_text(encoding="utf-8") == original
    assert not (home / ".codex" / "skills" / "research-tree").exists()
    assert not (home / ".claude" / "skills" / "research-tree").exists()


def test_status_requires_current_setup_managed_hooks(tmp_path: Path) -> None:
    home = tmp_path / "home"
    target = home / ".codex" / "skills" / "research-tree"
    target.parent.mkdir(parents=True)
    source = resolve_skill_source(ROOT, "codex")
    shutil.copytree(source, target)
    missing = skill_status(
        ("codex",),
        source=ROOT,
        scope="user",
        home=home,
        project_root=tmp_path / "project",
    )["installations"][0]
    assert missing["skill_status"] == "current"
    assert missing["hook_status"] == "missing"
    assert missing["status"] == "missing"
    assert missing["reason"] == "hooks_missing"

    install_skill(
        ("codex",),
        source=ROOT,
        scope="user",
        mode="copy",
        home=home,
        project_root=tmp_path / "project",
    )
    config = home / ".codex" / "hooks.json"
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["hooks"]["SessionStart"][-1]["hooks"][0]["command"] = "tampered"
    config.write_text(json.dumps(payload), encoding="utf-8")

    conflict = skill_status(
        ("codex",),
        source=ROOT,
        scope="user",
        home=home,
        project_root=tmp_path / "project",
    )["installations"][0]
    assert conflict["skill_status"] == "current"
    assert conflict["hook_status"] == "conflict"
    assert conflict["status"] == "conflict"
    assert conflict["reason"] == "hooks_mismatch"


def test_installed_global_hook_command_is_fail_open_in_an_unbound_workspace(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "unrelated"
    workspace.mkdir()
    install_skill(
        ("codex",),
        source=ROOT,
        scope="user",
        mode="copy",
        home=home,
        project_root=workspace,
    )
    command = next(
        command
        for command in _commands(home / ".codex" / "hooks.json")
        if "research-tree-hook" in command
    )

    completed = subprocess.run(
        shlex.split(command),
        cwd=workspace,
        input=json.dumps({"cwd": str(workspace), "hook_event_name": "SessionStart"}),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {"continue": True}
    assert not (workspace / ".research-tree").exists()
