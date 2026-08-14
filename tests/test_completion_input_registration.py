from __future__ import annotations

import pytest

from research_tree.completion_inputs import (
    CanonicalCompletionInputRegistrar,
    CompletionInputRegistrationError,
)
from research_tree.domain import ArtifactRef
from research_tree.insights import persist_insight_digest, synthesize_insights
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


def test_dedicated_completion_writer_commits_input_issuer_and_registration_atomically(tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-156")

    insight, issuer, registration = ledger.append_canonical_completion_input(
        "run-156",
        input_id="insight-1",
        input_kind="insight-digest",
        input_payload=synthesize_insights((), active_slot_ids=()),
        input_parent_refs=(),
        role="insight",
        issuer_id="issuer-1",
        registration_id="completion-input-1",
        expected_revision=0,
    )

    assert insight.kind == "insight-digest"
    assert issuer.kind == "canonical-completion-input-issuer"
    assert issuer.parent_refs == (ArtifactRef("run-156", insight.id, insight.revision),)
    assert registration.kind == "canonical-completion-input"
    assert registration.parent_refs == (
        ArtifactRef("run-156", insight.id, insight.revision),
        ArtifactRef("run-156", issuer.id, issuer.revision),
    )
    assert registration.payload == {
        "schema_version": 1,
        "run_id": "run-156",
        "role": "insight",
        "input_ref": ArtifactRef("run-156", insight.id, insight.revision).to_dict(),
        "issuer_ref": ArtifactRef("run-156", issuer.id, issuer.revision).to_dict(),
        "committed_revision": 1,
    }
    assert ledger.get_revision("run-156") == 3
    assert ledger.append_canonical_completion_input(
        "run-156",
        input_id="insight-1",
        input_kind="insight-digest",
        input_payload=synthesize_insights((), active_slot_ids=()),
        input_parent_refs=(),
        role="insight",
        issuer_id="issuer-1",
        registration_id="completion-input-1",
        expected_revision=3,
    ) == (insight, issuer, registration)
    assert ledger.get_revision("run-156") == 3
    accepted = CanonicalCompletionInputRegistrar(ledger).register(
        run_id="run-156",
        role="insight",
        input_artifact=insight,
        issuer_id="issuer-1",
        registration_id="completion-input-1",
        expected_revision=3,
    )
    assert accepted == registration


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


def test_registrar_rejects_structurally_valid_generic_role_without_dedicated_issuer(tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-156")
    generic = ledger.append_artifact(
        "run-156",
        "insight-1",
        "insight-digest",
        synthesize_insights((), active_slot_ids=()),
        expected_revision=0,
    )

    with pytest.raises(CompletionInputRegistrationError, match="dedicated writer"):
        CanonicalCompletionInputRegistrar(ledger).register(
            run_id="run-156",
            role="insight",
            input_artifact=generic,
            issuer_id="insight-writer",
            registration_id="completion-input-1",
            expected_revision=1,
        )

    assert ledger.get_revision("run-156") == 1
    assert len(ledger.load_run("run-156").artifacts) == 1


def test_canonical_insight_writer_creates_an_admissible_completion_input(tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-156")
    payload = synthesize_insights((), active_slot_ids=())

    insight = persist_insight_digest(
        ledger,
        round_id="run-156",
        insight_id="insight-1",
        payload=payload,
        parent_refs=(),
        expected_revision=0,
    )
    registration = next(
        item for item in ledger.load_run("run-156").artifacts if item.kind == "canonical-completion-input"
    )

    assert (
        CanonicalCompletionInputRegistrar(ledger).register(
            run_id="run-156",
            role="insight",
            input_artifact=insight,
            issuer_id=f"{insight.id}-issuer",
            registration_id=registration.id,
            expected_revision=3,
        )
        == registration
    )

    with pytest.raises(CompletionInputRegistrationError, match="issuer does not match"):
        CanonicalCompletionInputRegistrar(ledger).register(
            run_id="run-156",
            role="insight",
            input_artifact=insight,
            issuer_id="replacement-issuer",
            registration_id=registration.id,
            expected_revision=3,
        )


@pytest.mark.parametrize("parent_run", ("run-156", "run-foreign"))
def test_dedicated_completion_writer_rejects_stale_or_foreign_parent_atomically(tmp_path, parent_run: str) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-156")
    if parent_run == "run-foreign":
        ledger.create_run(parent_run)
    parent = ledger.append_artifact(
        parent_run,
        "parent-1",
        "input",
        {"state": "first"},
        expected_revision=0,
    )
    if parent_run == "run-156":
        ledger.append_artifact(
            "run-156",
            "parent-1",
            "input",
            {"state": "replacement"},
            expected_revision=1,
        )

    expected_revision = ledger.get_revision("run-156")
    with pytest.raises(LedgerIntegrityError, match="target run|not current"):
        ledger.append_canonical_completion_input(
            "run-156",
            input_id="insight-1",
            input_kind="insight-digest",
            input_payload=synthesize_insights((), active_slot_ids=()),
            input_parent_refs=(ArtifactRef(parent.round_id, parent.id, parent.revision),),
            role="insight",
            issuer_id="issuer-1",
            registration_id="completion-input-1",
            expected_revision=expected_revision,
        )

    assert ledger.get_revision("run-156") == expected_revision
    assert not [
        item for item in ledger.load_run("run-156").artifacts if item.kind.startswith("canonical-completion-input")
    ]


def test_dedicated_completion_writer_rejects_quarantined_parent_atomically(tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-156")
    parent = ledger.append_artifact(
        "run-156",
        "parent-1",
        "input",
        {"state": "first"},
        expected_revision=0,
    )
    parent_ref = ArtifactRef(parent.round_id, parent.id, parent.revision)
    ledger.append_artifact(
        "run-156",
        "quarantine-1",
        "stale-state-quarantine",
        {"dependent_refs": [parent_ref.to_dict()]},
        expected_revision=1,
    )

    with pytest.raises(LedgerIntegrityError, match="parent is quarantined"):
        ledger.append_canonical_completion_input(
            "run-156",
            input_id="insight-1",
            input_kind="insight-digest",
            input_payload=synthesize_insights((), active_slot_ids=()),
            input_parent_refs=(parent_ref,),
            role="insight",
            issuer_id="issuer-1",
            registration_id="completion-input-1",
            expected_revision=2,
        )

    assert ledger.get_revision("run-156") == 2


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
