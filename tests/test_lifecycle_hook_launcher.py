"""Issue #453 defect 1: self-contained launcher runs with system Python outside a checkout."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "lifecycle_hook_launcher.py"


def _plain_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "plain-workspace"
    workspace.mkdir()
    return workspace


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (root / "packages").mkdir()
    (root / "skill-src").mkdir()
    (root / "src" / "research_tree").mkdir(parents=True)
    (root / "src" / "research_tree" / "__init__.py").write_text("", encoding="utf-8")
    for name in ("lifecycle_hook.py", "origins.py", "skill_activation.py"):
        shutil.copy2(ROOT / "src" / "research_tree" / name, root / "src" / "research_tree" / name)
    return root


def _checkout_with_run(tmp_path: Path) -> Path:
    root = _checkout(tmp_path)
    manifest = root / ".research-tree" / "projects" / "topic-1" / "runs" / "run-1" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"project_id":"topic-1","run_id":"run-1"}', encoding="utf-8")
    return root


def _run_launcher(args: list[str], *, cwd: Path, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=cwd,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def _assert_single_response(completed: subprocess.CompletedProcess[str], expected: dict[str, bool]) -> None:
    assert completed.returncode == 0, f"launcher must never fail a host session: {completed.stderr}"
    assert "Traceback" not in completed.stderr
    assert completed.stdout.count("<rt:event ") == 1
    assert completed.stdout.count("</rt:event>") == 1
    inner = completed.stdout[completed.stdout.index(">") + 1 : completed.stdout.rindex("</rt:event>")]
    assert json.loads(inner) == expected


def _skill_copy(tmp_path: Path) -> Path:
    """Materialize an installed-style flat skill scripts directory."""
    skill_dir = tmp_path / "skill-scripts"
    skill_dir.mkdir()
    shutil.copy2(LAUNCHER, skill_dir / "lifecycle_hook_launcher.py")
    for name in ("lifecycle_hook.py", "origins.py", "skill_activation.py"):
        source = ROOT / "src" / "research_tree" / name
        shutil.copy2(source, skill_dir / name)
    return skill_dir


def test_launcher_exits_zero_outside_any_checkout(tmp_path: Path) -> None:
    workspace = _plain_workspace(tmp_path)
    payload = json.dumps({"cwd": str(workspace), "hook_event_name": "SessionStart"})

    completed = _run_launcher(["--host", "claude", "--event", "SessionStart"], cwd=workspace, stdin=payload)

    _assert_single_response(completed, {"continue": True})
    assert "uv" not in completed.stdout
    assert "uv" not in completed.stderr
    assert not (workspace / ".research-tree-debug").exists()
    assert not (workspace / ".research-tree").exists()


def test_launcher_survives_invalid_payload_inside_a_checkout(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    payload = "not json"

    completed = _run_launcher(["--host", "claude", "--event", "SessionStart"], cwd=checkout, stdin=payload)

    _assert_single_response(completed, {"continue": True})
    assert not (checkout / ".research-tree-debug" / "events").exists()


def test_launcher_records_through_the_checkout_source_tree(tmp_path: Path) -> None:
    checkout = _checkout_with_run(tmp_path)
    payload = json.dumps(
        {
            "cwd": str(checkout),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "No, use pytest not unittest",
        }
    )

    completed = _run_launcher(
        ["--host", "claude", "--event", "UserPromptSubmit", "--project-id", "topic-1", "--run-id", "run-1"],
        cwd=checkout,
        stdin=payload,
    )

    _assert_single_response(completed, {"continue": True})
    signals = list((checkout / ".research-tree-debug" / "signals").glob("*.json"))
    assert len(signals) == 1
    signal = json.loads(signals[0].read_text(encoding="utf-8"))
    assert signal["category"] == "correction"
    assert "pytest" not in json.dumps(signal)
    feeds = list((checkout / ".research-tree" / "projects" / "topic-1" / "runs" / "run-1" / "events").glob("*.json"))
    assert len(feeds) == 1
    feed = json.loads(feeds[0].read_text(encoding="utf-8"))
    assert feed["route"] == "apply_correction"


def test_launcher_records_through_an_installed_flat_copy(tmp_path: Path) -> None:
    checkout = _checkout_with_run(tmp_path)
    skill_dir = _skill_copy(tmp_path)
    launcher = skill_dir / "lifecycle_hook_launcher.py"
    payload = json.dumps(
        {
            "cwd": str(checkout),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "cancel that search",
            "project_id": "topic-1",
            "run_id": "run-1",
        }
    )

    completed = subprocess.run(
        [sys.executable, str(launcher), "--host", "claude", "--event", "UserPromptSubmit"],
        cwd=checkout,
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )

    _assert_single_response(completed, {"continue": True})
    signals = list((checkout / ".research-tree-debug" / "signals").glob("*.json"))
    assert len(signals) == 1
    signal = json.loads(signals[0].read_text(encoding="utf-8"))
    assert signal["category"] == "interruption"
    run_events = checkout / ".research-tree" / "projects" / "topic-1" / "runs" / "run-1" / "events"
    assert not run_events.exists()


def test_launcher_unknown_flags_still_exit_zero(tmp_path: Path) -> None:
    workspace = _plain_workspace(tmp_path)
    payload = json.dumps({"cwd": str(workspace), "hook_event_name": "SessionStart"})

    completed = _run_launcher(
        ["--host", "claude", "--event", "SessionStart", "--unknown-flag", "value"],
        cwd=workspace,
        stdin=payload,
    )

    _assert_single_response(completed, {"continue": True})
