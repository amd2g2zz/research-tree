from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from research_tree.skill_setup import (
    SkillSetupError,
    _create_link,
    install_skill,
    main,
    resolve_package,
    resolve_skill_source,
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


def test_copy_status_is_digest_current_tamper_detected_and_reinstallable(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    installed = install_skill(
        ("codex", "claude", "hermes"),
        source=ROOT,
        scope="user",
        mode="copy",
        home=home,
        project_root=project,
    )
    statuses = skill_status(
        ("codex", "claude", "hermes"),
        source=ROOT,
        scope="user",
        home=home,
        project_root=project,
    )["installations"]
    assert {item["status"] for item in statuses} == {"current"}
    assert {item["reason"] for item in statuses} == {"payload_digest_match"}
    assert all(item["source_payload_digest"] == item["target_payload_digest"] for item in statuses)

    codex_target = Path(next(item for item in installed["installations"] if item["host"] == "codex")["target"])
    (codex_target / "SKILL.md").write_text("---\nname: research-tree\n---\ntampered", encoding="utf-8")
    tampered = skill_status(
        ("codex",),
        source=ROOT,
        scope="user",
        home=home,
        project_root=project,
    )["installations"][0]
    assert tampered["status"] == "conflict"
    assert tampered["reason"] == "payload_digest_mismatch"

    with pytest.raises(SkillSetupError, match="conflicting"):
        install_skill(
            ("codex",),
            source=ROOT,
            scope="user",
            mode="copy",
            home=home,
            project_root=project,
        )
    shutil.rmtree(codex_target)
    reinstalled = install_skill(
        ("codex",),
        source=ROOT,
        scope="user",
        mode="copy",
        home=home,
        project_root=project,
    )
    assert reinstalled["installations"][0]["action"] == "installed"
    assert skill_status(
        ("codex",),
        source=ROOT,
        scope="user",
        home=home,
        project_root=project,
    )["installations"][0]["status"] == "current"
    (codex_target / "references" / "codex-native-orchestration.md").unlink()
    missing_resource = skill_status(
        ("codex",),
        source=ROOT,
        scope="user",
        home=home,
        project_root=project,
    )["installations"][0]
    assert missing_resource["status"] == "conflict"
    assert missing_resource["reason"] == "missing_referenced_resource"


def test_install_preflights_all_hosts_before_writing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    conflict = home / ".claude" / "skills" / "research-tree"
    conflict.mkdir(parents=True)
    (conflict / "SKILL.md").write_text("existing", encoding="utf-8")

    with pytest.raises(SkillSetupError, match="conflicting"):
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

    with pytest.raises(SkillSetupError, match="conflicting"):
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
    assert status["installations"][0]["status"] == "conflict"


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

    with pytest.raises(SkillSetupError, match="conflicting"):
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
    assert status["installations"][0]["status"] == "conflict"


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

    assert statuses["codex"]["status"] == "conflict"
    assert statuses["codex"]["activation_state"] == "discovered"
    assert statuses["codex"]["live_activation"] == "unproven"
    assert statuses["claude"]["status"] == "conflict"
    assert statuses["hermes"]["skill_status"] == "current"
    assert statuses["hermes"]["hook_status"] == "missing"
    assert statuses["hermes"]["status"] == "missing"
    assert statuses["hermes"]["activation_state"] == "discovered"

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

    assert result["installations"][0]["status"] == "conflict"
    assert os.path.lexists(target)


def test_install_rejects_existing_link_without_refresh_path(tmp_path: Path) -> None:
    home = tmp_path / "home"
    stale_source = tmp_path / "old" / "research-tree"
    stale_source.mkdir(parents=True)
    (stale_source / "SKILL.md").write_text("---\nname: research-tree\n---\nold", encoding="utf-8")
    target = home / ".codex" / "skills" / "research-tree"
    target.parent.mkdir(parents=True)
    _create_link(stale_source, target)

    with pytest.raises(SkillSetupError, match="conflicting"):
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


def _build_pinned_anysearch_source(root: Path) -> Path:
    """Materialize the vendored upstream AnySearch v2.1.0 payload for tests."""

    from research_tree.skill_setup import ANYSEARCH_PAYLOAD_FILES

    source = root / "deps" / "anysearch-2.1.0" / "skills" / "anysearch"
    source.mkdir(parents=True)
    for relative in ANYSEARCH_PAYLOAD_FILES:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_upstream_anysearch_root() / relative, target)
    return source


def _upstream_anysearch_root() -> Path:
    return Path(__file__).resolve().parents[1] / ".research-tree" / "upstream-anysearch-v2.1.0"


def test_hermes_dependency_manifest_declares_pinned_anysearch() -> None:
    from research_tree.skill_setup import ANYSEARCH_PINNED_SHA256, hermes_dependency_manifest

    manifest = hermes_dependency_manifest()

    assert manifest["schema"] == 1
    anysearch = manifest["dependencies"]["anysearch"]
    assert anysearch["version"] == "2.1.0"
    assert anysearch["revision"] == "6ff6aa958ad9747659d669b5e9984f07c896f2aa"
    assert anysearch["install_path"] == "skills/anysearch"
    assert isinstance(anysearch["payload_files"], list) and anysearch["payload_files"]
    assert anysearch["payload_sha256"] == ANYSEARCH_PINNED_SHA256
    assert len(ANYSEARCH_PINNED_SHA256) == 64


def test_vendored_upstream_payload_matches_pinned_digest() -> None:
    upstream = _upstream_anysearch_root()
    if not upstream.is_dir():
        pytest.skip("vendored upstream AnySearch payload absent (fetched in live-evidence phase)")
    from research_tree.skill_setup import ANYSEARCH_PAYLOAD_FILES, ANYSEARCH_PINNED_SHA256
    from research_tree.skill_setup import _dependency_payload_digest

    assert _dependency_payload_digest(upstream, ANYSEARCH_PAYLOAD_FILES) == ANYSEARCH_PINNED_SHA256


def test_hermes_dependency_install_is_verified_and_idempotent(tmp_path: Path) -> None:
    if not _upstream_anysearch_root().is_dir():
        pytest.skip("vendored upstream AnySearch payload absent (fetched in live-evidence phase)")
    from research_tree.skill_setup import hermes_dependency_status, install_hermes_dependencies

    home = tmp_path / "hermes-home"
    source_root = tmp_path / "deps" / "anysearch-2.1.0"
    _build_pinned_anysearch_source(tmp_path)

    first = install_hermes_dependencies(home=home, source_root=source_root)
    assert first["status"] == "installed"
    assert first["dependencies"]["anysearch"]["revision"].startswith("6ff6aa9")

    second = install_hermes_dependencies(home=home, source_root=source_root)
    assert second["status"] == "installed"
    assert second["dependencies"]["anysearch"]["revision"] == first["dependencies"]["anysearch"]["revision"]

    status = hermes_dependency_status(home=home)
    assert status["dependencies"]["anysearch"]["status"] == "current"


def test_hermes_dependency_tampered_source_fails_closed(tmp_path: Path) -> None:
    from research_tree.skill_setup import SkillSetupError, install_hermes_dependencies

    tampered = tmp_path / "deps" / "anysearch-2.1.0"
    (tampered / "skills" / "anysearch").mkdir(parents=True)
    (tampered / "skills" / "anysearch" / "anysearch.py").write_text("# tampered payload\n", encoding="utf-8")

    with pytest.raises(SkillSetupError, match="missing pinned payload files"):
        install_hermes_dependencies(home=tmp_path / "hermes-home", source_root=tampered)


def test_hermes_dependency_install_does_not_touch_global_config(tmp_path: Path) -> None:
    if not _upstream_anysearch_root().is_dir():
        pytest.skip("vendored upstream AnySearch payload absent (fetched in live-evidence phase)")
    from research_tree.skill_setup import install_hermes_dependencies

    home = tmp_path / "hermes-home"
    source_root = tmp_path / "deps" / "anysearch-2.1.0"
    _build_pinned_anysearch_source(tmp_path)

    install_hermes_dependencies(home=home, source_root=source_root)

    assert (home / "skills" / "anysearch" / "SKILL.md").is_file()
    assert not (home / "config.yaml").exists()


def test_hermes_dependency_complete_but_modified_payload_fails_closed(tmp_path: Path) -> None:
    if not _upstream_anysearch_root().is_dir():
        pytest.skip("vendored upstream AnySearch payload absent (fetched in live-evidence phase)")
    from research_tree.skill_setup import SkillSetupError, install_hermes_dependencies

    source_root = tmp_path / "deps" / "anysearch-2.1.0"
    _build_pinned_anysearch_source(tmp_path)
    (source_root / "skills" / "anysearch" / "SKILL.md").write_text("# tampered\n", encoding="utf-8")

    with pytest.raises(SkillSetupError, match="pinned manifest digest"):
        install_hermes_dependencies(home=tmp_path / "hermes-home", source_root=source_root)
