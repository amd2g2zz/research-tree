"""Issue #382: narrow ``except Exception`` in lifecycle facade helpers.

``_runtime_readiness`` and ``_validate_canonical_receipt`` must catch the
narrow set of coordinator / store / OS errors and map them to actionable
failure surface, *not* a flat ``verification_pending`` shortcut that
swallows every exception the way the legacy alpha2 path did.

Four regression tests cover:

1. ``_runtime_readiness`` surfaces ``LedgerConflictError`` (and other
   store errors) with a ``readiness_canonical_unreachable`` reason
   instead of swallowing.
2. ``_validate_canonical_receipt`` maps ``StaleStateError`` to
   ``verification_failed`` (the run really is in conflict; the caller
   should retry/re-enter alignment, not wait on a pending verdict).
3. ``_validate_canonical_receipt`` maps transient ``RuntimeStoreError``
   to ``verification_failed`` with a ``coordinator_error:`` reason so
   the failure is observable.
4. ``_validate_canonical_receipt`` lets unexpected exceptions
   (``ValueError`` etc.) propagate so the failure exit-code path can
   surface them — restoring the legitimate propagation that the bare
   ``except Exception`` had stripped away.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_tree.cli import _runtime_readiness, _validate_canonical_receipt
from research_tree.coordinator import (
    ResearchRunCoordinator,
    StaleStateError,
)
from research_tree.domain import RuntimeStoreError
from research_tree.run_ledger import LedgerConflictError, RunLedger


def _make_args(workspace: Path, run_id: str, project_id: str = "proj") -> SimpleNamespace:
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


def _bootstrap_workspace(tmp_path: Path, run_id: str = "run-1") -> tuple[Path, RunLedger]:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ledger = RunLedger(workspace)
    ledger.create_run(run_id)
    return workspace, ledger


def test_runtime_readiness_when_coordinator_raises_non_transient_surfaces_in_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    workspace, ledger = _bootstrap_workspace(tmp_path)
    caplog.set_level(logging.WARNING, logger="research_tree.cli")

    def _explode(self: str, run_id: str) -> dict[str, object]:
        raise LedgerConflictError("ledger revision conflict")

    monkeypatch.setattr(ResearchRunCoordinator, "why_not_complete", _explode)

    readiness, _runtime = _runtime_readiness(workspace, _make_args(workspace, "run-1"), ledger)

    assert readiness["ready"] is False
    assert "readiness_canonical_unreachable" in readiness["failure_reasons"]
    assert any(
        "ledger revision conflict" in record.getMessage()
        for record in caplog.records
        if record.name == "research_tree.cli"
    ), "logger must emit a warning with the underlying error"


def test_verify_when_coordinator_raises_stale_state_returns_verification_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, ledger = _bootstrap_workspace(tmp_path)

    def _explode(self: str, run_id: str) -> dict[str, object]:
        raise StaleStateError("complete", reason="stale_digest")

    monkeypatch.setattr(ResearchRunCoordinator, "why_not_complete", _explode)
    revision = ledger.get_revision("run-1")

    receipt = _validate_canonical_receipt(ledger, "run-1", revision)

    assert receipt["status"] == "verification_failed"
    assert receipt["details"]["verdict"] == "canonical_conflict"
    assert receipt["details"]["revision"] == revision
    reasons = receipt["details"]["reasons"]
    assert any(reason.startswith("coordinator_conflict:") for reason in reasons), reasons


def test_verify_when_coordinator_raises_transient_returns_verification_failed_with_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, ledger = _bootstrap_workspace(tmp_path)

    def _explode(self: str, run_id: str) -> dict[str, object]:
        raise RuntimeStoreError("store IO failure")

    monkeypatch.setattr(ResearchRunCoordinator, "why_not_complete", _explode)
    revision = ledger.get_revision("run-1")

    receipt = _validate_canonical_receipt(ledger, "run-1", revision)

    assert receipt["status"] == "verification_failed"
    assert receipt["details"]["verdict"] == "canonical_unreachable"
    reasons = receipt["details"]["reasons"]
    assert any(reason.startswith("coordinator_error:") for reason in reasons), reasons


def test_verify_propagates_unexpected_exception_to_caller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace, ledger = _bootstrap_workspace(tmp_path)

    def _explode(self: str, run_id: str) -> dict[str, object]:
        raise ValueError("unsupported ledger schema")

    monkeypatch.setattr(ResearchRunCoordinator, "why_not_complete", _explode)
    revision = ledger.get_revision("run-1")

    with pytest.raises(ValueError, match="unsupported ledger schema"):
        _validate_canonical_receipt(ledger, "run-1", revision)
