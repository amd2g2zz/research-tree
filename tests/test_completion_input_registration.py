from __future__ import annotations

import pytest

from research_tree.completion_inputs import (
    CanonicalCompletionInputRegistrar,
    CompletionInputRegistrationError,
)
from research_tree.domain import ArtifactRef
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


def test_dedicated_completion_registration_commits_issuer_and_registration_atomically(tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-156")
    readiness = ledger.append_artifact(
        "run-156",
        "readiness-1",
        "readiness-record",
        {"status": "ready"},
        expected_revision=0,
    )

    issuer, registration = ledger.append_canonical_completion_registration(
        "run-156",
        issuer_id="issuer-1",
        issuer_payload={"role": "readiness", "issuer": "readiness-verifier"},
        registration_id="completion-input-1",
        registration_payload={"role": "readiness"},
        input_ref=ArtifactRef("run-156", readiness.id, readiness.revision),
        expected_revision=1,
    )

    assert issuer.kind == "canonical-completion-input-issuer"
    assert issuer.parent_refs == (ArtifactRef("run-156", readiness.id, readiness.revision),)
    assert registration.kind == "canonical-completion-input"
    assert registration.parent_refs == (
        ArtifactRef("run-156", readiness.id, readiness.revision),
        ArtifactRef("run-156", issuer.id, issuer.revision),
    )
    assert ledger.get_revision("run-156") == 3


def test_registrar_rejects_malformed_generic_role_without_authority_artifacts(tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-156")
    malformed = ledger.append_artifact(
        "run-156",
        "readiness-1",
        "readiness-record",
        {"status": "ready"},
        expected_revision=0,
    )

    registrar = CanonicalCompletionInputRegistrar(ledger)
    with pytest.raises(CompletionInputRegistrationError, match="invalid completion input"):
        registrar.register(
            run_id="run-156",
            role="readiness",
            input_artifact=malformed,
            issuer_id="readiness-verifier",
            registration_id="completion-input-1",
            expected_revision=1,
        )

    assert ledger.get_revision("run-156") == 1
    assert {item.kind for item in ledger.load_run("run-156").artifacts} == {"readiness-record"}


def test_registrar_rejects_foreign_input_without_mutation(tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-156")
    ledger.create_run("run-foreign")
    foreign = ledger.append_artifact(
        "run-foreign",
        "readiness-1",
        "readiness-record",
        {"status": "ready"},
        expected_revision=0,
    )

    with pytest.raises(CompletionInputRegistrationError, match="target run"):
        CanonicalCompletionInputRegistrar(ledger).register(
            run_id="run-156",
            role="readiness",
            input_artifact=foreign,
            issuer_id="readiness-verifier",
            registration_id="completion-input-1",
            expected_revision=0,
        )

    assert ledger.get_revision("run-156") == 0
