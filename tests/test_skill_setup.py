from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

import pytest

from research_tree.skill_setup import (
    SkillSetupError,
    _create_link,
    bootstrap_project_hooks,
    initialize_project_workspace,
    install_skill,
    main,
    resolve_package,
    resolve_skill_source,
    resolve_target,
    skill_status,
)


ROOT = Path(__file__).resolve().parents[1]


def test_project_workspace_is_stable_and_owns_one_run_tree(tmp_path: Path) -> None:
    first = initialize_project_workspace(tmp_path, project_id="topic-42", run_id="run-7", session_id="session-a")
    second = initialize_project_workspace(tmp_path, project_id="topic-42", run_id="run-7", session_id="session-b")

    assert first["project_root"] == second["project_root"]
    assert first["run_root"] == second["run_root"]
    assert Path(first["project_root"]) == tmp_path / ".research-tree" / "projects" / "topic-42"
    assert (Path(first["run_root"]) / "manifest.json").is_file()
    assert Path(first["session_root"]).name == "session-a"
    assert Path(second["session_root"]).name == "session-b"


def test_project_hook_bootstrap_merges_configs_and_keeps_hermes_local(tmp_path: Path) -> None:
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "hooks.json").write_text(
        json.dumps({"custom": True, "hooks": {"SessionStart": [{"command": "keep"}]}}),
        encoding="utf-8",
    )
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"model": "custom", "hooks": {"Stop": [{"command": "keep"}]}}),
        encoding="utf-8",
    )
    workspace = initialize_project_workspace(tmp_path, project_id="topic-42", run_id="run-7")

    first = bootstrap_project_hooks(tmp_path, workspace)
    second = bootstrap_project_hooks(tmp_path, workspace)

    codex = json.loads((tmp_path / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    claude = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert codex["custom"] is True
    assert codex["hooks"]["SessionStart"][0]["command"] == "keep"
    assert sum("research-tree-hook" in json.dumps(item) for item in codex["hooks"]["SessionStart"]) == 1
    assert claude["model"] == "custom"
    assert claude["hooks"]["Stop"][0]["command"] == "keep"
    assert sum("research-tree-hook" in json.dumps(item) for item in claude["hooks"]["Stop"]) == 1
    assert first["status"] == "configured"
    assert second["status"] == "configured"
    hermes_config = Path(first["hermes"]["config"])
    assert hermes_config.is_file()
    assert hermes_config.is_relative_to(Path(workspace["run_root"]))
    assert first["hermes"]["environment"] == {"HERMES_HOME": str(hermes_config.parent)}


def test_project_hook_bootstrap_rolls_back_all_configs_on_partial_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = initialize_project_workspace(tmp_path, project_id="topic-42", run_id="run-7")
    codex_config = tmp_path / ".codex" / "hooks.json"
    codex_config.parent.mkdir()
    codex_config.write_text('{"custom":true}', encoding="utf-8")

    from research_tree import skill_setup

    original = skill_setup._atomic_write_text
    calls = 0

    def fail_second_write(path: Path, text: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("interrupted write")
        original(path, text)

    monkeypatch.setattr(skill_setup, "_atomic_write_text", fail_second_write)

    with pytest.raises(SkillSetupError, match="interrupted write"):
        bootstrap_project_hooks(tmp_path, workspace)

    assert codex_config.read_text(encoding="utf-8") == '{"custom":true}'
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_rendered_hermes_hook_command_parses_and_records_its_declared_event(tmp_path: Path) -> None:
    workspace = initialize_project_workspace(tmp_path, project_id="topic-42", run_id="run-7")
    hermes_config = Path(bootstrap_project_hooks(tmp_path, workspace)["hermes"]["config"])
    rendered = hermes_config.read_text(encoding="utf-8")
    command = re.search(r"on_session_start:\n\s+- command: (.+)", rendered)

    assert command is not None
    arguments = shlex.split(json.loads(command.group(1)))
    assert "--event" in arguments
    assert arguments[arguments.index("--event") + 1] == "on_session_start"
    completed = subprocess.run(
        arguments,
        cwd=tmp_path,
        input=json.dumps({"cwd": str(tmp_path), "hook_event_name": "on_session_start"}),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {}
    assert list((Path(workspace["run_root"]) / "events").glob("*.json"))


def test_host_specific_user_and_project_targets(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"

    assert resolve_target("codex", scope="user", home=home, project_root=project) == (
        home / ".codex" / "skills" / "research-tree"
    )
    assert resolve_target("claude", scope="user", home=home, project_root=project) == (
        home / ".claude" / "skills" / "research-tree"
    )
    assert resolve_target("hermes", scope="user", home=home, project_root=project) == (
        home / ".hermes" / "skills" / "research-tree"
    )
    assert resolve_target("codex", scope="project", home=home, project_root=project) == (
        project / ".agents" / "skills" / "research-tree"
    )
    assert resolve_target("claude", scope="project", home=home, project_root=project) == (
        project / ".claude" / "skills" / "research-tree"
    )
    with pytest.raises(SkillSetupError, match="external_dirs"):
        resolve_target("hermes", scope="project", home=home, project_root=project)


def test_copy_install_uses_each_hosts_own_directory_and_complete_payload(
    tmp_path: Path,
) -> None:
    result = install_skill(
        ("codex", "claude", "hermes"),
        source=ROOT,
        scope="user",
        mode="copy",
        home=tmp_path / "home",
        project_root=tmp_path / "project",
    )

    targets = {item["host"]: Path(item["target"]) for item in result["installations"]}
    assert targets["codex"].parts[-3:] == (".codex", "skills", "research-tree")
    assert targets["claude"].parts[-3:] == (".claude", "skills", "research-tree")
    assert targets["hermes"].parts[-3:] == (".hermes", "skills", "research-tree")
    for installation in result["installations"]:
        target = Path(installation["target"])
        assert (target / "SKILL.md").is_file()
        for relative in installation["payload_files"]:
            assert (target / relative).is_file()


def test_install_preflights_all_hosts_before_writing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    conflict = home / ".claude" / "skills" / "research-tree"
    conflict.mkdir(parents=True)
    (conflict / "SKILL.md").write_text("existing", encoding="utf-8")

    with pytest.raises(SkillSetupError, match="unsupported"):
        install_skill(
            ("codex", "claude", "hermes"),
            source=ROOT,
            scope="user",
            mode="copy",
            home=home,
            project_root=tmp_path / "project",
        )

    assert not (home / ".codex" / "skills" / "research-tree").exists()
    assert not (home / ".hermes" / "skills" / "research-tree").exists()
    assert (conflict / "SKILL.md").read_text(encoding="utf-8") == "existing"


def test_link_install_rolls_back_earlier_host_when_a_later_write_fails(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").write_text("blocks the skills directory", encoding="utf-8")
    codex_target = home / ".codex" / "skills" / "research-tree"

    with pytest.raises(SkillSetupError):
        install_skill(
            ("codex", "claude"),
            source=ROOT,
            scope="user",
            mode="link",
            home=home,
            project_root=tmp_path / "project",
        )

    assert not os.path.lexists(codex_target)


def test_link_install_is_idempotent_and_tracks_the_source_checkout(tmp_path: Path) -> None:
    home = tmp_path / "home"
    first = install_skill(
        ("codex",),
        source=ROOT,
        scope="user",
        mode="link",
        home=home,
        project_root=tmp_path / "project",
    )
    second = install_skill(
        ("codex",),
        source=ROOT,
        scope="user",
        mode="link",
        home=home,
        project_root=tmp_path / "project",
    )

    target = Path(first["installations"][0]["target"])
    assert target.resolve() == resolve_package(ROOT, "codex").resolve()
    assert first["installations"][0]["action"] == "installed"
    assert second["installations"][0]["action"] == "unchanged"
    assert (
        skill_status(
            ("codex",),
            source=ROOT,
            scope="user",
            home=home,
            project_root=tmp_path / "project",
        )["installations"][0]["status"]
        == "current"
    )


def test_project_link_points_to_isolated_host_package(tmp_path: Path) -> None:
    result = install_skill(
        ("codex",),
        source=ROOT,
        scope="project",
        mode="link",
        home=tmp_path / "home",
        project_root=tmp_path / "project",
    )

    target = Path(result["installations"][0]["target"])
    assert target.resolve() == resolve_package(ROOT, "codex").resolve()


def test_legacy_repository_link_is_unsupported_without_reading_or_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    target = home / ".hermes" / "skills" / "research-tree"
    target.parent.mkdir(parents=True)
    _create_link(ROOT, target)

    from research_tree import skill_setup

    monkeypatch.setattr(
        skill_setup, "package_digests", lambda _: (_ for _ in ()).throw(AssertionError("must not read"))
    )

    with pytest.raises(SkillSetupError, match="unsupported"):
        install_skill(
            ("hermes",),
            source=ROOT,
            scope="user",
            mode="link",
            home=home,
            project_root=tmp_path / "project",
        )

    assert target.resolve() == ROOT.resolve()
    status = skill_status(
        ("hermes",),
        source=ROOT,
        scope="user",
        home=home,
        project_root=tmp_path / "project",
    )
    assert status["installations"][0]["status"] == "unsupported"


def test_claude_direct_install_uses_nested_skill_and_reports_plugin_package(
    tmp_path: Path,
) -> None:
    result = install_skill(
        ("claude",),
        source=ROOT,
        scope="user",
        mode="link",
        home=tmp_path / "home",
        project_root=tmp_path / "project",
    )

    installation = result["installations"][0]
    target = Path(installation["target"])
    assert target.resolve() == resolve_skill_source(ROOT, "claude").resolve()
    assert (target / "SKILL.md").is_file()
    assert Path(installation["package"]) == resolve_package(ROOT, "claude")
    assert Path(installation["skill_source"]) == resolve_skill_source(ROOT, "claude")


def test_legacy_claude_plugin_root_link_is_unsupported_without_mutation(tmp_path: Path) -> None:
    home = tmp_path / "home"
    target = home / ".claude" / "skills" / "research-tree"
    target.parent.mkdir(parents=True)
    _create_link(resolve_package(ROOT, "claude"), target)

    with pytest.raises(SkillSetupError, match="unsupported"):
        install_skill(
            ("claude",),
            source=ROOT,
            scope="user",
            mode="link",
            home=home,
            project_root=tmp_path / "project",
        )

    assert target.resolve() == resolve_package(ROOT, "claude").resolve()
    status = skill_status(
        ("claude",),
        source=ROOT,
        scope="user",
        home=home,
        project_root=tmp_path / "project",
    )
    assert status["installations"][0]["status"] == "unsupported"


def test_codex_home_override_is_used_for_user_scope(tmp_path: Path) -> None:
    configured = tmp_path / "custom-codex"
    assert (
        resolve_target(
            "codex",
            scope="user",
            home=tmp_path / "home",
            project_root=tmp_path / "project",
            codex_home=configured,
        )
        == configured / "skills" / "research-tree"
    )


def test_cli_dry_run_reports_all_host_targets(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "install",
            "--host",
            "all",
            "--source",
            str(ROOT),
            "--home",
            str(tmp_path / "home"),
            "--dry-run",
        ]
    )

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert {item["host"] for item in output["installations"]} == {
        "codex",
        "claude",
        "hermes",
    }
    assert {item["action"] for item in output["installations"]} == {"planned"}


def test_status_reports_existing_non_current_targets_as_unsupported(tmp_path: Path) -> None:
    home = tmp_path / "home"
    stale_source = tmp_path / "old-checkout" / "research-tree"
    stale_source.mkdir(parents=True)
    (stale_source / "SKILL.md").write_text("---\nname: research-tree\n---\nold", encoding="utf-8")
    codex_target = home / ".codex" / "skills" / "research-tree"
    codex_target.parent.mkdir(parents=True)
    _create_link(stale_source, codex_target)
    conflict = home / ".claude" / "skills" / "research-tree"
    conflict.mkdir(parents=True)
    (conflict / "SKILL.md").write_text("user-owned", encoding="utf-8")
    current = home / ".hermes" / "skills" / "research-tree"
    current.parent.mkdir(parents=True)
    shutil.copytree(resolve_skill_source(ROOT, "hermes"), current)

    result = skill_status(
        ("codex", "claude", "hermes"),
        source=ROOT,
        scope="user",
        home=home,
        project_root=tmp_path / "project",
    )
    statuses = {item["host"]: item for item in result["installations"]}

    assert statuses["codex"]["status"] == "unsupported"
    assert statuses["codex"]["activation_state"] == "discovered"
    assert statuses["codex"]["live_activation"] == "unproven"
    assert statuses["claude"]["status"] == "unsupported"
    assert statuses["hermes"]["status"] == "current"
    assert statuses["hermes"]["activation_state"] == "static_ready"

    assert codex_target.resolve() == stale_source.resolve()
    assert (conflict / "SKILL.md").read_text(encoding="utf-8") == "user-owned"


def test_broken_link_is_unsupported_and_status_does_not_repoint_it(tmp_path: Path) -> None:
    home = tmp_path / "home"
    missing = tmp_path / "removed" / "research-tree"
    missing.mkdir(parents=True)
    target = home / ".hermes" / "skills" / "research-tree"
    target.parent.mkdir(parents=True)
    _create_link(missing, target)
    missing.rmdir()

    result = skill_status(
        ("hermes",),
        source=ROOT,
        scope="user",
        home=home,
        project_root=tmp_path / "project",
    )

    assert result["installations"][0]["status"] == "unsupported"
    assert os.path.lexists(target)


def test_install_rejects_existing_link_without_refresh_path(tmp_path: Path) -> None:
    home = tmp_path / "home"
    stale_source = tmp_path / "old" / "research-tree"
    stale_source.mkdir(parents=True)
    (stale_source / "SKILL.md").write_text("---\nname: research-tree\n---\nold", encoding="utf-8")
    target = home / ".codex" / "skills" / "research-tree"
    target.parent.mkdir(parents=True)
    _create_link(stale_source, target)

    with pytest.raises(SkillSetupError, match="unsupported"):
        install_skill(
            ("codex",),
            source=ROOT,
            scope="user",
            mode="link",
            home=home,
            project_root=tmp_path / "project",
        )

    assert target.resolve() == stale_source.resolve()


def test_refresh_command_is_not_registered(tmp_path: Path) -> None:
    from research_tree import skill_setup

    assert "refresh" not in skill_setup.build_parser().format_help()
    assert not hasattr(skill_setup, "refresh_stale_links")

    with pytest.raises(SystemExit) as error:
        main(
            [
                "refresh",
                "--host",
                "codex",
                "--source",
                str(ROOT),
                "--home",
                str(tmp_path / "home"),
            ]
        )

    assert error.value.code == 2
