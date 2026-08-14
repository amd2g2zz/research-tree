from pathlib import Path

import pytest

from research_tree import CaptureIncompleteError, ContentAddressedStore, DurableSourceCaptureService, RunLedger
from research_tree.coordinator import CoordinatorConflictError
from research_tree.domain import ArtifactRef
from test_search_portfolio_lineage import (
    _coordinator,
    _parents,
    _pivot_correction,
    _values,
    durable_evidence,
    worker_finished_event,
)


def test_worker_finished_requires_checkpoint(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-1")
    service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    with pytest.raises(CaptureIncompleteError, match="capture_incomplete"):
        service.validate_worker_finished(run_id="run-1", attempt_id="attempt-a", capture_refs=(), checkpoint_ref=None)


def test_portfolio_worker_finish_requires_durable_lineage(tmp_path: Path) -> None:
    ledger, coordinator, artifacts = _coordinator(tmp_path)
    capture, receipt, checkpoint, finding = durable_evidence(tmp_path, ledger)
    portfolio, execution = _values()
    lineage = coordinator.persist_search_portfolio_lineage(
        run_id="run-portfolio",
        attempt_id="attempt-1",
        portfolio=portfolio,
        execution=execution,
        capture_refs=(capture,),
        receipt_refs=(receipt,),
        checkpoint_refs=(checkpoint,),
        finding_refs=(finding,),
        **_parents(artifacts),
        expected_revision=ledger.get_revision("run-portfolio"),
    )

    with pytest.raises(CoordinatorConflictError, match="portfolio_lineage_required"):
        coordinator.ingest_host_event(
            worker_finished_event(ledger, capture, receipt, checkpoint, finding, event_id="finished-missing-lineage")
        )

    lineage_ref = ArtifactRef("run-portfolio", lineage.id, lineage.revision)
    assert (
        coordinator.ingest_host_event(
            worker_finished_event(ledger, capture, receipt, checkpoint, finding, lineage=lineage_ref)
        ).kind
        == "host-event"
    )


def test_portfolio_worker_finish_rejects_quarantined_lineage(tmp_path: Path) -> None:
    ledger, coordinator, artifacts = _coordinator(tmp_path)
    capture, receipt, checkpoint, finding = durable_evidence(tmp_path, ledger)
    portfolio, execution = _values(disposition="pivot")
    lineage = coordinator.persist_search_portfolio_lineage(
        run_id="run-portfolio",
        attempt_id="attempt-1",
        portfolio=portfolio,
        execution=execution,
        capture_refs=(capture,),
        receipt_refs=(receipt,),
        checkpoint_refs=(checkpoint,),
        finding_refs=(finding,),
        **_parents(artifacts),
        pivot_correction=_pivot_correction(artifacts),
        expected_revision=ledger.get_revision("run-portfolio"),
    )

    event = worker_finished_event(
        ledger,
        capture,
        receipt,
        checkpoint,
        finding,
        lineage=ArtifactRef("run-portfolio", lineage.id, lineage.revision),
    )
    with pytest.raises(CoordinatorConflictError, match="portfolio_lineage_reference_invalid"):
        coordinator._validate_host_event_payload(
            event,
            run_id="run-portfolio",
            attempt_id="attempt-1",
            work_item={"portfolio_id": "portfolio-1"},
        )
    with pytest.raises(CoordinatorConflictError, match="stale_digest"):
        coordinator.ingest_host_event(event)
