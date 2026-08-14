from __future__ import annotations

import pytest

from research_tree.run_ledger import LedgerIntegrityError, RunLedger


@pytest.mark.parametrize(
    "kind",
    ("canonical-completion-input", "canonical-completion-input-issuer"),
)
def test_generic_ledger_append_cannot_create_canonical_completion_authority(kind: str, tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-156")

    with pytest.raises(LedgerIntegrityError, match="reserved canonical completion kind"):
        ledger.append_artifact(
            "run-156",
            "forged-input",
            kind,
            {"role": "readiness"},
            expected_revision=0,
        )

    assert ledger.get_revision("run-156") == 0
    assert ledger.load_run("run-156").artifacts == ()


def test_generic_ledger_batch_cannot_create_canonical_completion_authority(tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-156")

    with pytest.raises(LedgerIntegrityError, match="reserved canonical completion kind"):
        ledger.append_artifact_batch(
            "run-156",
            (("forged-input", "canonical-completion-input", {"role": "readiness"}, ()),),
            expected_revision=0,
        )

    assert ledger.get_revision("run-156") == 0
    assert ledger.load_run("run-156").artifacts == ()
