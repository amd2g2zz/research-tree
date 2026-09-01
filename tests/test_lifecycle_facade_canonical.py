"""Issue #325: lifecycle facade reads canonical state; verify validates revision-bound receipt."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace


def _make_args(workspace, run_id, project_id="proj"):
    return SimpleNamespace(
        workspace=workspace,
        run_id=run_id,
        project_id=project_id,
        host=["claude-code"],
        source=Path("/nonexistent"),
        scope="user",
        home=Path("/tmp"),
        project_root=Path("/tmp"),
        codex_home=None,
    )


def test_status_projects_canonical_revision_and_unmet_obligations(tmp_path) -> None:
    from research_tree.cli import _status
    from research_tree.run_ledger import RunLedger

    workspace = tmp_path / "ws"
    workspace.mkdir()
    ledger = RunLedger(workspace)
    ledger.create_run("run-1")
    payload = _status(_make_args(workspace, "run-1"))
    assert payload["command"] == "status"
    assert payload["run"].get("authority_revision") == ledger.get_revision("run-1")
    # Issue #325 spec attack: the legacy single-string fake
    # 'independent_completion_receipt_absent' is gone; readiness carries
    # real reasons, and the 4 obligation names appear only when
    # canonically missing (not hard-coded as in alpha2).
    # In this empty-run case, no lifecycle_request exists; only the
    # workspace/project_workspace reasons are listed.
    readiness = payload["readiness"]
    assert readiness["ready"] is False
    # The 4 obligation reasons appear as real canonical reasons (read from
    # coordinator.why_not_complete), not the legacy single string.
    assert payload["result"].get("canonical_unmet_obligations") is not None


def test_status_surfaces_run_id_and_revision_even_for_empty_runs(tmp_path) -> None:
    from research_tree.cli import _status
    from research_tree.run_ledger import RunLedger

    workspace = tmp_path / "ws"
    workspace.mkdir()
    ledger = RunLedger(workspace)
    ledger.create_run("run-empty")
    payload = _status(_make_args(workspace, "run-empty", project_id="p"))
    assert payload["run"]["run_id"] == "run-empty"
    assert "authority_revision" in payload["run"]


def test_verify_returns_specific_field_level_reasons_not_legacy_string(tmp_path) -> None:
    from research_tree.cli import _verify
    from research_tree.run_ledger import RunLedger

    workspace = tmp_path / "ws"
    workspace.mkdir()
    ledger = RunLedger(workspace)
    ledger.create_run("run-1")
    payload = _verify(_make_args(workspace, "run-1"))
    assert payload["command"] == "verify"
    verification = payload["result"]["verification"]
    assert verification != "independent_completion_receipt_absent"
    assert isinstance(verification, dict)
    assert "verdict" in verification


def test_verify_no_legacy_verification_pending_shortcut(tmp_path) -> None:
    from research_tree.cli import _verify
    from research_tree.run_ledger import RunLedger

    workspace = tmp_path / "ws"
    workspace.mkdir()
    ledger = RunLedger(workspace)
    ledger.create_run("run-1")
    payload = _verify(_make_args(workspace, "run-1"))
    assert payload["status"] != "verification_pending" or "verdict" in payload["result"]["verification"]


def test_doctor_4_section_split_declared_in_source(tmp_path) -> None:
    from research_tree import cli

    source = inspect.getsource(cli._doctor)
    for section in ("installation", "host_capability", "run_readiness", "completion_verification"):
        assert section in source, f"_doctor must declare {section} section"
