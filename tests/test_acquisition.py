from pathlib import Path

from research_tree import ContentAddressedStore, DurableSourceCaptureService, RunLedger


def test_acquisition_receipt_is_bound_after_cas_capture(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-1")
    service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    capture = service.capture(
        run_id="run-1",
        capture_id="capture-a",
        attempt_id="attempt-a",
        data=b"bytes",
        media_type="text/plain",
        method_id="web",
        provider_id="provider",
        expected_revision=0,
    )
    receipt = service.receipt(
        run_id="run-1",
        receipt_id="receipt-a",
        capture=capture,
        attempt_id="attempt-a",
        method_id="web",
        provider_id="provider",
        expected_revision=1,
    )
    assert receipt.capture_id == capture.capture_id
    assert receipt.artifact_ref is not None
