from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest


def test_initialize_migrates_legacy_roots_to_one_project_authority(tmp_path: Path) -> None:
    from research_tree.project_workspace import initialize_project_run

    legacy = tmp_path / ".research-tree-native" / "run-1"
    legacy.mkdir(parents=True)
    (legacy / "state.json").write_text('{"schema": 1}\n', encoding="utf-8")

    workspace = initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="codex")

    assert workspace.run_root == tmp_path / ".research-tree" / "projects" / "topic-1" / "runs" / "run-1"
    assert not legacy.exists()
    manifest = json.loads((workspace.run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["project_id"] == "topic-1"
    assert manifest["run_id"] == "run-1"
    assert manifest["migrated_legacy_roots"] == [".research-tree-native/run-1"]


def test_initialize_migrates_all_run_bound_legacy_authorities(tmp_path: Path) -> None:
    from research_tree.project_workspace import initialize_project_run

    for root in (".research-tree-native", ".research-tree-alignment"):
        legacy = tmp_path / root / "run-1"
        legacy.mkdir(parents=True)
        (legacy / "state.json").write_text('{"schema": 1}\n', encoding="utf-8")

    workspace = initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="codex")

    assert not (tmp_path / ".research-tree-native" / "run-1").exists()
    assert not (tmp_path / ".research-tree-alignment" / "run-1").exists()
    assert (workspace.run_root / "legacy" / "native" / "state.json").is_file()
    assert (workspace.run_root / "legacy" / "alignment" / "state.json").is_file()


def test_initialize_rejects_unattributed_global_legacy_root(tmp_path: Path) -> None:
    from research_tree.project_workspace import ProjectWorkspaceError, initialize_project_run

    (tmp_path / ".research-tree-hooks").mkdir()

    with pytest.raises(ProjectWorkspaceError, match="explicit migration"):
        initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="codex")


def test_installed_probe_records_unavailable_without_a_launcher(tmp_path: Path) -> None:
    from research_tree.project_workspace import initialize_project_run, probe_lifecycle_hook

    workspace = initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="claude")

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

    initialized = initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="codex")
    launcher = write_installed_hook_launcher(initialized)

    assert probe_lifecycle_hook(initialized, launcher=launcher).status == "available"
    resumed = resume_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="hermes")

    assert resumed.run_root == initialized.run_root
    assert resumed.manifest_path == initialized.manifest_path
    assert list((initialized.run_root / "events").glob("*.json"))


def test_project_hook_install_merges_configs_and_executes_configured_command(tmp_path: Path) -> None:
    from research_tree.project_workspace import initialize_project_run, install_project_hooks

    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "hooks.json").write_text(
        json.dumps({"custom": True, "hooks": {"SessionStart": [{"command": "keep"}]}}),
        encoding="utf-8",
    )
    workspace = initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="codex")

    first = install_project_hooks(tmp_path, workspace)
    second = install_project_hooks(tmp_path, workspace)

    codex = json.loads((tmp_path / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    assert codex["custom"] is True
    assert codex["hooks"]["SessionStart"][0]["command"] == "keep"
    owned = [
        entry
        for entry in codex["hooks"]["SessionStart"]
        if str(first["launcher"]) in entry.get("hooks", [{}])[0].get("command", "")
    ]
    assert len(owned) == 1
    assert first["launcher"] == second["launcher"]
    assert Path(first["hermes"]["config"]).is_relative_to(workspace.run_root)

    command = owned[0]["hooks"][0]["command"]
    completed = subprocess.run(
        shlex.split(command),
        cwd=tmp_path,
        input=json.dumps({"hook_event_name": "SessionStart", "cwd": str(tmp_path)}),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    records = list((workspace.run_root / "events").glob("*.json"))
    assert records
    assert json.loads(records[-1].read_text(encoding="utf-8"))["event"] == "SessionStart"


def test_project_hook_install_rolls_back_if_later_config_is_invalid(tmp_path: Path) -> None:
    from research_tree.project_workspace import ProjectWorkspaceError, initialize_project_run, install_project_hooks

    codex_path = tmp_path / ".codex" / "hooks.json"
    codex_path.parent.mkdir()
    original = '{"custom":true}\n'
    codex_path.write_text(original, encoding="utf-8")
    claude_path = tmp_path / ".claude" / "settings.json"
    claude_path.parent.mkdir()
    claude_path.write_text("[]", encoding="utf-8")
    workspace = initialize_project_run(tmp_path, project_id="topic-1", run_id="run-1", host="claude")

    with pytest.raises(ProjectWorkspaceError, match="must be an object"):
        install_project_hooks(tmp_path, workspace)

    assert codex_path.read_text(encoding="utf-8") == original


def test_native_init_rejects_bad_handoff_without_creating_project_authority(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    bad_handoff = tmp_path / "handoff.json"
    bad_handoff.write_text("{}", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts/native_execution_adapter.py"),
            "--host",
            "codex",
            "--workspace",
            str(tmp_path),
            "init",
            "--project-id",
            "topic-1",
            "--run-id",
            "run-1",
            "--handoff",
            str(bad_handoff),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert not (tmp_path / ".research-tree" / "projects" / "topic-1").exists()


@pytest.mark.parametrize(
    ("host", "relative_adapter"),
    [
        ("codex", Path("packages/codex/research-tree/scripts/native_execution_adapter.py")),
        (
            "claude",
            Path("packages/claude-code/research-tree/skills/research-tree/scripts/native_execution_adapter.py"),
        ),
    ],
)
def test_installed_native_package_initializes_without_source_imports(
    tmp_path: Path, host: str, relative_adapter: Path
) -> None:
    repository = Path(__file__).resolve().parents[1]
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "schema": 1,
                "kind": "alignment-handoff",
                "run_id": "alignment-run",
                "decision_slots": {"slot-1": {"question": "Bound the decision."}},
                "execution_context": {},
            }
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-E",
            "-B",
            str(repository / relative_adapter),
            "--host",
            host,
            "--workspace",
            str(tmp_path),
            "init",
            "--project-id",
            "topic-1",
            "--run-id",
            "run-1",
            "--handoff",
            str(handoff),
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["lifecycle_hooks"] == "available"
