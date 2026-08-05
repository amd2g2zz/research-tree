from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "native_execution_adapter.py"


def _handoff(path: Path) -> Path:
    value = {
        "schema": 1,
        "kind": "alignment-handoff",
        "run_id": "alignment-native-events",
        "decision_slots": {"slot-a": {"question": "Primary"}},
        "execution_context": {"authority": ["research"]},
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _run(workspace: Path, *args: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(ADAPTER), "--host", "codex", "--workspace", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_native_adapter_emits_host_events_without_completion_authority(tmp_path: Path) -> None:
    handoff = _handoff(tmp_path / "handoff.json")
    _run(tmp_path, "init", "--run-id", "native-events", "--handoff", str(handoff))
    _run(
        tmp_path,
        "add-task",
        "--run-id",
        "native-events",
        "--task-id",
        "landscape-1",
        "--decision-slot",
        "slot-a",
        "--phase",
        "landscape",
        "--artifact",
        "findings/landscape.json",
    )
    started = _run(tmp_path, "start", "--run-id", "native-events", "--task-id", "landscape-1")
    assert started["status"] == "running"
    status = _run(tmp_path, "status", "--run-id", "native-events")
    assert status["host_event_count"] == 1
    state = json.loads((tmp_path / ".research-tree-native" / "native-events" / "state.json").read_text(encoding="utf-8"))
    event = state["host_events"][0]
    assert event["event_type"] == "attempt_started"
    assert event["host"] == "codex"
    assert event["payload"]["worker_id"] == "native-worker"
    assert status["canonical_complete"] is False


def test_host_specific_entrypoints_bind_their_native_host() -> None:
    codex = ROOT / "scripts" / "codex_execution_adapter.py"
    claude = ROOT / "scripts" / "claude_execution_adapter.py"
    assert codex.is_file() and claude.is_file()
    wrong = subprocess.run(
        [sys.executable, str(codex), "--host", "claude", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert wrong.returncode != 0
    assert "only accepts --host codex" in wrong.stderr or "only accepts --host codex" in wrong.stdout
