from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from research_tree.skill_setup import (
    ACTIVATION_SENTINELS,
    SkillSetupError,
    _create_link,
    activation_status,
    install_skill,
    main,
    resolve_package,
    resolve_target,
    skill_status,
)


ROOT = Path(__file__).resolve().parents[1]


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

    with pytest.raises(SkillSetupError, match="refusing to overwrite"):
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
    assert skill_status(
        ("codex",),
        source=ROOT,
        scope="user",
        home=home,
        project_root=tmp_path / "project",
    )["installations"][0]["status"] == "current"


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


def test_legacy_repository_link_is_migrated_to_host_package(tmp_path: Path) -> None:
    home = tmp_path / "home"
    target = home / ".hermes" / "skills" / "research-tree"
    target.parent.mkdir(parents=True)
    _create_link(ROOT, target)

    result = install_skill(
        ("hermes",),
        source=ROOT,
        scope="user",
        mode="link",
        home=home,
        project_root=tmp_path / "project",
    )

    assert result["installations"][0]["action"] == "migrated"
    assert target.resolve() == resolve_package(ROOT, "hermes").resolve()


def test_stale_host_link_requires_explicit_refresh(tmp_path: Path) -> None:
    home = tmp_path / "home"
    stale_source = tmp_path / "old-checkout" / "packages" / "codex" / "research-tree"
    stale_source.mkdir(parents=True)
    (stale_source / "SKILL.md").write_text(
        "---\nname: research-tree\ndescription: old\n---\n", encoding="utf-8"
    )
    target = home / ".codex" / "skills" / "research-tree"
    _create_link(stale_source, target)

    with pytest.raises(SkillSetupError, match="--refresh-stale-link"):
        install_skill(
            ("codex",),
            source=ROOT,
            scope="user",
            mode="link",
            home=home,
            project_root=tmp_path / "project",
        )

    result = install_skill(
        ("codex",),
        source=ROOT,
        scope="user",
        mode="link",
        home=home,
        project_root=tmp_path / "project",
        refresh_stale_link=True,
    )
    assert result["installations"][0]["action"] == "refreshed_stale_link"
    assert target.resolve() == resolve_package(ROOT, "codex").resolve()


def test_activation_status_reports_static_proof_and_live_probe(tmp_path: Path) -> None:
    result = activation_status(
        ("codex",),
        source=ROOT,
        scope="user",
        home=tmp_path / "home",
        project_root=tmp_path / "project",
    )

    installation = result["installations"][0]
    assert installation["static_readiness"] == "blocked"
    assert installation["installation_status"] == "missing"
    assert installation["static_contract"]["sentinel"] == ACTIVATION_SENTINELS["codex"]
    assert installation["manual_probe"]["expected_response"].endswith(
        ACTIVATION_SENTINELS["codex"]
    )
    assert "model context" in installation["does_not_prove"][0]


def test_codex_home_override_is_used_for_user_scope(tmp_path: Path) -> None:
    configured = tmp_path / "custom-codex"
    assert resolve_target(
        "codex",
        scope="user",
        home=tmp_path / "home",
        project_root=tmp_path / "project",
        codex_home=configured,
    ) == configured / "skills" / "research-tree"


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
