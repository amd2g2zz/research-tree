from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_installed_probe_records_unavailable_without_a_launcher(tmp_path: Path) -> None:
    from research_tree.project_workspace import initialize_project_run, probe_lifecycle_hook

    workspace = initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="pi")

    result = probe_lifecycle_hook(workspace, launcher=None)

    assert result.status == "unavailable"
    manifest = json.loads((workspace.run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["capabilities"]["lifecycle_hooks"] == "unavailable"


def test_live_hook_probe_and_cross_host_restart_share_one_manifest(tmp_path: Path) -> None:
    from research_tree.project_workspace import (
        initialize_project_run,
        probe_lifecycle_hook,
        resume_project_run,
        write_installed_hook_launcher,
    )

    initialized = initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="pi")
    launcher = write_installed_hook_launcher(initialized)

    assert probe_lifecycle_hook(initialized, launcher=launcher).status == "available"
    resumed = resume_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="pi")

    assert resumed.run_root == initialized.run_root
    assert resumed.manifest_path == initialized.manifest_path
    assert list((initialized.run_root / "events").glob("*.json"))


def test_project_hook_install_rolls_back_if_later_config_is_invalid(tmp_path: Path) -> None:
    from research_tree.project_workspace import ProjectWorkspaceError, initialize_project_run, install_project_hooks

    codex_path = tmp_path / ".codex" / "hooks.json"
    codex_path.parent.mkdir()
    original = '{"custom":true}\n'
    codex_path.write_text(original, encoding="utf-8")
    claude_path = tmp_path / ".claude" / "settings.json"
    claude_path.parent.mkdir()
    claude_path.write_text("[]", encoding="utf-8")
    workspace = initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="pi")

    with pytest.raises(ProjectWorkspaceError, match="must be an object"):
        install_project_hooks(tmp_path, workspace)

    assert codex_path.read_text(encoding="utf-8") == original


def test_initialize_keeps_old_format_roots_and_manifest_has_no_migration_record(tmp_path: Path) -> None:
    """Non-migration contract: old-format roots stay untouched; no migrated-roots record (#422)."""

    from research_tree.project_workspace import initialize_project_run

    old_root = tmp_path / ".research-tree-native" / "run-1"
    old_root.mkdir(parents=True)
    old_manifest = old_root / "manifest.json"
    old_manifest.write_text(json.dumps({"schema": 1, "run_id": "run-1"}), encoding="utf-8")

    workspace = initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="pi")

    assert old_root.is_dir()
    assert json.loads(old_manifest.read_text(encoding="utf-8")) == {"schema": 1, "run_id": "run-1"}
    manifest = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert "migrated_legacy_roots" not in manifest
    for directory in ("alignment", "plans", "attempts", "sessions", "events", "checkpoints", "logs", "deliveries"):
        assert (workspace.run_root / directory).is_dir()
