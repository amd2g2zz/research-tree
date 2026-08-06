from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from research_tree.contracts import HostEvent
from research_tree.host_events import canonical_event_digest


ROOT = Path(__file__).resolve().parents[1]


def _native_input(path: Path) -> Path:
    value = {
        "event_id": "event-native-1",
        "event_type": "attempt_started",
        "run_id": "native-events",
        "round_id": "round-native-events",
        "slot_id": "slot-a",
        "action_id": "action-a",
        "attempt_id": "attempt-a",
        "causation_id": "dispatch-a",
        "correlation_id": "native-events",
        "sequence": 1,
        "expected_revision": 4,
        "emitted_at": "2026-08-06T00:00:00+00:00",
        "payload": {
            "worker_id": "native-worker",
            "lease_expires_at": "2026-08-06T00:15:00+00:00",
            "tool_capability_digest": "a" * 64,
            "started_at": "2026-08-06T00:00:00+00:00",
        },
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _run(adapter: Path, workspace: Path, event_input: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(adapter), "emit", "--input", str(event_input)],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("host", "entrypoint"),
    [
        ("codex", "codex_execution_adapter.py"),
        ("claude-code", "claude_execution_adapter.py"),
    ],
)
def test_source_adapter_is_a_stateless_host_event_translator(
    tmp_path: Path, host: str, entrypoint: str
) -> None:
    adapter = ROOT / "scripts" / entrypoint
    completed = _run(adapter, tmp_path, _native_input(tmp_path / "event.json"))

    assert completed.returncode == 0, completed.stderr
    event = HostEvent.from_dict(json.loads(completed.stdout))
    assert event.host == host
    assert event.event_type == "attempt_started"
    assert event.expected_revision == 4
    assert event.payload["worker_id"] == "native-worker"
    assert not (tmp_path / ".research-tree-native").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["event.json"]


@pytest.mark.parametrize(
    ("package_name", "entrypoint"),
    [
        ("codex", "codex_execution_adapter.py"),
        ("claude-code", "claude_execution_adapter.py"),
    ],
)
def test_copied_package_adapter_runs_without_source_checkout_imports(
    tmp_path: Path, package_name: str, entrypoint: str
) -> None:
    installed = tmp_path / "installed" / "research-tree"
    shutil.copytree(ROOT / "packages" / package_name / "research-tree", installed)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    completed = _run(
        installed / "scripts" / entrypoint,
        workspace,
        _native_input(workspace / "event.json"),
    )

    assert completed.returncode == 0, completed.stderr
    HostEvent.from_dict(json.loads(completed.stdout))
    assert not (workspace / ".research-tree-native").exists()


def test_codex_and_claude_translate_equivalent_events_to_same_semantics(
    tmp_path: Path,
) -> None:
    event_input = _native_input(tmp_path / "event.json")
    events = []
    for entrypoint in ("codex_execution_adapter.py", "claude_execution_adapter.py"):
        completed = _run(ROOT / "scripts" / entrypoint, tmp_path, event_input)
        assert completed.returncode == 0, completed.stderr
        events.append(json.loads(completed.stdout))

    assert canonical_event_digest([events[0]]) == canonical_event_digest([events[1]])


def test_host_specific_entrypoints_reject_a_conflicting_host_argument() -> None:
    codex = ROOT / "scripts" / "codex_execution_adapter.py"
    wrong = subprocess.run(
        [sys.executable, str(codex), "--host", "claude-code", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert wrong.returncode != 0
    assert "only accepts --host codex" in (wrong.stderr + wrong.stdout)
