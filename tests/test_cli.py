from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from research_tree import cli
from research_tree.coordinator import CompletionBlockedError, IllegalTransitionError

from test_host_event_protocol import _coordinator, _event


ROOT = Path(__file__).resolve().parents[1]
RETIRED_COMMANDS = (
    "create-round",
    "show-round",
    "tree-init",
    "tree-init-alignment",
    "tree-next",
    "tree-ingest",
    "tree-recover",
    "tree-deliver",
    "profile-inspect",
    "profile-correct",
    "profile-reset",
    "profile-delete",
)


@pytest.mark.parametrize("command", RETIRED_COMMANDS)
def test_retired_cli_commands_are_unparseable_without_creating_a_store(
    command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "retired-store"

    with pytest.raises(SystemExit) as exit_status:
        cli.main([command, "--store", str(store)])

    captured = capsys.readouterr()
    assert exit_status.value.code == 2
    assert command in captured.err
    assert "authority_blocked" not in captured.err
    assert "research-tree-migrate" not in captured.err
    assert captured.out == ""
    assert not store.exists()


def test_cli_help_does_not_discover_retired_commands() -> None:
    help_text = cli.build_parser().format_help()

    assert "canonical" in help_text.lower()
    for command in RETIRED_COMMANDS:
        assert command not in help_text


def test_migration_console_surface_and_public_exports_are_removed() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "research-tree-migrate" not in metadata["project"]["scripts"]
    assert not (ROOT / "src" / "research_tree" / "migration.py").exists()
    assert not (ROOT / "src" / "research_tree" / "migration_cli.py").exists()
    assert not hasattr(__import__("research_tree"), "Alpha1MigrationService")


def _json_output(capsys: pytest.CaptureFixture[str]) -> dict:
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def _assert_envelope(payload: dict, run_id: str) -> None:
    assert set(payload) >= {
        "code",
        "category",
        "retryability",
        "run_id",
        "safe_message",
        "unmet_obligations",
        "evidence_refs",
        "next_action",
    }
    assert payload["run_id"] == run_id


def _artifact_contract(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key not in {"created_at", "content_hash"}}


def test_current_cli_verbs_match_direct_coordinator_operations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = tmp_path / "workspace"
    ledger, _, _ = _coordinator(workspace)
    expected_workspace = tmp_path / "expected-workspace"
    expected_ledger, expected_coordinator, _ = _coordinator(expected_workspace)
    event = _event(expected_ledger)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event.to_dict()), encoding="utf-8")

    expected_ingest = expected_coordinator.ingest_host_event(event).to_dict()
    assert cli.main(["run", "--workspace", str(workspace), "ingest", "--event", str(event_path)]) == 0
    ingest = _json_output(capsys)
    _assert_envelope(ingest, "run-host")
    assert ingest["code"] == "ok"
    assert _artifact_contract(ingest["result"]) == _artifact_contract(expected_ingest)

    expected_why = expected_coordinator.why_not_complete("run-host")
    assert cli.main(["run", "--workspace", str(workspace), "why-not-complete", "--run-id", "run-host"]) == 0
    why = _json_output(capsys)
    _assert_envelope(why, "run-host")
    assert why["result"] == json.loads(json.dumps(expected_why))

    recovery_workspace = tmp_path / "recovery-workspace"
    recovery_ledger, recovery_coordinator, _ = _coordinator(recovery_workspace)
    recovery_coordinator.ingest_host_event(event)
    expected_recovery = recovery_coordinator.recover("run-host")
    assert cli.main(["run", "--workspace", str(workspace), "recover", "--run-id", "run-host"]) == 0
    recovery = _json_output(capsys)
    _assert_envelope(recovery, "run-host")
    assert _artifact_contract(recovery["result"]) == _artifact_contract(expected_recovery)


def test_ingest_error_envelope_preserves_run_identity_and_rejection_classification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = tmp_path / "workspace"
    ledger, _, _ = _coordinator(workspace)
    stale_event = _event(ledger, event_id="event-stale", expected_revision=0)
    event_path = tmp_path / "stale-event.json"
    event_path.write_text(json.dumps(stale_event.to_dict()), encoding="utf-8")

    assert cli.main(["run", "--workspace", str(workspace), "ingest", "--event", str(event_path)]) == 3
    stale = _json_output(capsys)
    _assert_envelope(stale, "run-host")
    assert stale["code"] == "stale_revision"
    assert stale["category"] == "conflict"
    assert stale["retryability"] is True

    invalid_workspace = tmp_path / "invalid-workspace"
    invalid_event = tmp_path / "invalid-event.json"
    invalid_event.write_text("not json", encoding="utf-8")
    assert cli.main(["run", "--workspace", str(invalid_workspace), "ingest", "--event", str(invalid_event)]) == 2
    invalid = _json_output(capsys)
    assert invalid["code"] == "event_json_invalid"
    assert invalid["category"] == "invalid_input"
    assert invalid["run_id"] is None
    assert not invalid_workspace.exists()


def test_complete_reports_unmet_obligations_from_the_coordinator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"

    def blocked_complete(*_args: object, **_kwargs: object) -> None:
        raise CompletionBlockedError(("closure_ref",))

    monkeypatch.setattr(cli.ResearchRunCoordinator, "complete", blocked_complete)

    assert (
        cli.main(
            [
                "run",
                "--workspace",
                str(workspace),
                "complete",
                "--run-id",
                "run-57",
                "--actor",
                "human",
                "--expected-revision",
                "0",
            ]
        )
        == 4
    )
    blocked = _json_output(capsys)
    _assert_envelope(blocked, "run-57")
    assert blocked["code"] == "completion_blocked"
    assert blocked["category"] == "blocked"
    assert blocked["unmet_obligations"] == ["closure_ref"]
    assert blocked["next_action"] == "resolve:closure_ref"


def test_complete_preserves_the_direct_coordinator_rejection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = tmp_path / "workspace"
    ledger, coordinator, _ = _coordinator(workspace)
    expected_revision = ledger.get_revision("run-host")

    with pytest.raises(IllegalTransitionError) as error:
        coordinator.complete("run-host", actor="human", expected_revision=expected_revision)

    assert (
        cli.main(
            [
                "run",
                "--workspace",
                str(workspace),
                "complete",
                "--run-id",
                "run-host",
                "--actor",
                "human",
                "--expected-revision",
                str(expected_revision),
            ]
        )
        == 10
    )
    payload = _json_output(capsys)
    _assert_envelope(payload, "run-host")
    assert payload["code"] == str(error.value)
    assert payload["category"] == "terminal"


@pytest.mark.parametrize("command", ("deliver", "accept", "reconcile-host", "status", *RETIRED_COMMANDS))
def test_unsupported_and_retired_verbs_are_unparseable(command: str, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    with pytest.raises(SystemExit) as error:
        cli.main(["run", "--workspace", str(workspace), command])

    assert error.value.code == 2
    assert not workspace.exists()


def test_help_lists_only_current_canonical_coordinator_verbs() -> None:
    help_text = cli.build_parser().format_help()

    for command in ("ingest", "recover", "why-not-complete", "complete"):
        assert command in help_text
    for command in ("deliver", "accept", "reconcile-host", "status", *RETIRED_COMMANDS):
        assert command not in help_text


def test_installed_wheel_exposes_only_the_current_cli(tmp_path: Path) -> None:
    distribution = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--offline", "--out-dir", str(distribution)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    environment = tmp_path / "environment"
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True, capture_output=True, text=True)
    scripts = environment / ("Scripts" if sys.platform == "win32" else "bin")
    python = scripts / ("python.exe" if sys.platform == "win32" else "python")
    wheel = next(distribution.glob("research_tree-*.whl"))
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )

    command = scripts / ("research-tree.exe" if sys.platform == "win32" else "research-tree")
    completed = subprocess.run([str(command), "--help"], check=False, capture_output=True, text=True)

    assert completed.returncode == 0
    for verb in ("ingest", "recover", "why-not-complete", "complete"):
        assert verb in completed.stdout
    assert not (
        scripts / ("research-tree-migrate.exe" if sys.platform == "win32" else "research-tree-migrate")
    ).exists()
