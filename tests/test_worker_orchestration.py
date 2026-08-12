from pathlib import Path

import pytest

from research_tree import CaptureIncompleteError, ContentAddressedStore, DurableSourceCaptureService, RunLedger


def test_worker_finished_requires_checkpoint(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-1")
    service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    with pytest.raises(CaptureIncompleteError, match="capture_incomplete"):
        service.validate_worker_finished(run_id="run-1", attempt_id="attempt-a", capture_refs=(), checkpoint_ref=None)
