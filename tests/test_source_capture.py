from __future__ import annotations

from pathlib import Path

import pytest

from research_tree import (
    AcquisitionReceipt,
    AnalysisCheckpoint,
    CaptureIncompleteError,
    ContentAddressedStore,
    DurableSourceCaptureService,
    RunLedger,
    SourceCapture,
)


def _service(tmp_path: Path) -> tuple[DurableSourceCaptureService, RunLedger, ContentAddressedStore]:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-1")
    cas = ContentAddressedStore(tmp_path)
    return DurableSourceCaptureService(ledger, cas), ledger, cas


def test_capture_deduplicates_bytes_but_keeps_attempt_provenance(tmp_path: Path) -> None:
    service, ledger, cas = _service(tmp_path)
    first = service.capture(
        run_id="run-1",
        capture_id="capture-a",
        attempt_id="attempt-a",
        data=b"same",
        media_type="text/plain",
        method_id="web",
        provider_id="provider-a",
        expected_revision=0,
    )
    second = service.capture(
        run_id="run-1",
        capture_id="capture-b",
        attempt_id="attempt-b",
        data=b"same",
        media_type="text/plain",
        method_id="repository",
        provider_id="provider-b",
        expected_revision=1,
    )
    assert first.content_digest == second.content_digest
    assert first.attempt_id != second.attempt_id
    assert len(list(cas.cas_root.glob("*/*"))) == 1
    assert ledger.get_artifact(first.artifact_ref).kind == "source-capture"


def test_receipt_and_checkpoint_are_durable_and_resume_exactly(tmp_path: Path) -> None:
    service, ledger, _ = _service(tmp_path)
    capture = service.capture(
        run_id="run-1",
        capture_id="capture-a",
        attempt_id="attempt-a",
        data=b"source",
        media_type="application/pdf",
        method_id="web",
        provider_id="provider-a",
        expected_revision=0,
    )
    receipt = service.receipt(
        run_id="run-1",
        receipt_id="receipt-a",
        capture=capture,
        attempt_id="attempt-a",
        method_id="web",
        provider_id="provider-a",
        expected_revision=1,
    )
    checkpoint = service.checkpoint(
        run_id="run-1",
        checkpoint_id="checkpoint-a",
        attempt_id="attempt-a",
        action_id="action-a",
        source_capture_refs=(capture.artifact_ref,),
        facts=({"statement": "fact", "evidence_refs": ["capture-a"]},),
        expected_revision=2,
    )
    resumed = service.resume("run-1", "attempt-a")
    assert resumed.capture.content_digest == capture.content_digest
    assert resumed.receipt.receipt_id == receipt.receipt_id
    assert resumed.checkpoint.checkpoint_id == checkpoint.checkpoint_id
    assert ledger.get_artifact(checkpoint.artifact_ref).payload["attempt_id"] == "attempt-a"


def test_checkpoint_rejects_sensitive_fields_and_worker_finish_is_quarantined(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    with pytest.raises(ValueError, match="redaction"):
        service.checkpoint(
            run_id="run-1",
            checkpoint_id="checkpoint-a",
            attempt_id="attempt-a",
            action_id="action-a",
            source_capture_refs=(),
            facts=({"prompt": "private"},),
            expected_revision=0,
        )
    with pytest.raises(CaptureIncompleteError, match="capture_incomplete"):
        service.validate_worker_finished(
            run_id="run-1",
            attempt_id="attempt-a",
            capture_refs=(),
            checkpoint_ref=None,
        )


def test_contracts_round_trip_and_reject_wrong_run() -> None:
    capture = SourceCapture(
        capture_id="capture-a",
        run_id="run-1",
        attempt_id="attempt-a",
        locator={"url": "https://example.test"},
        content_digest="a" * 64,
        media_type="text/plain",
        size_bytes=1,
        captured_at="2026-01-01T00:00:00+00:00",
        method_id="web",
        provider_id="provider",
        provenance_group="provider",
        status="committed",
    )
    assert SourceCapture.from_dict(capture.to_dict()) == capture
    receipt = AcquisitionReceipt(
        receipt_id="receipt-a",
        capture_id="capture-a",
        attempt_id="attempt-a",
        method_id="web",
        provider_id="provider",
        requested_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:01+00:00",
        status="succeeded",
        failure_history=(),
    )
    assert AcquisitionReceipt.from_dict(receipt.to_dict()) == receipt
    with pytest.raises(ValueError, match="same run"):
        AnalysisCheckpoint(
            checkpoint_id="checkpoint-a",
            run_id="run-1",
            attempt_id="attempt-a",
            action_id="action-a",
            scope="scope",
            source_capture_refs=("run-2:capture:1",),
            facts=(),
            hypotheses=(),
            contradictions=(),
            open_questions=(),
            method_outcomes=(),
            next_actions=(),
            created_at="2026-01-01T00:00:00+00:00",
        ).validate_capture_runs("run-1")
