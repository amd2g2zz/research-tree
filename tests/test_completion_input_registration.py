from pathlib import Path

import pytest

from research_tree import synthesize_insights
from research_tree.domain import ArtifactRef
from research_tree.run_ledger import LedgerConflictError, LedgerIntegrityError, RunLedger


def test_generic_append_cannot_register_a_valid_looking_insight_digest(tmp_path: Path) -> None:
    from research_tree.completion_inputs import CompletionInputRegistrar

    ledger = RunLedger(tmp_path)
    ledger.create_run("run-completion")
    payload = synthesize_insights((), active_slot_ids=())

    generic = ledger.append_artifact(
        "run-completion",
        "generic-insight",
        "insight-digest",
        payload,
        expected_revision=0,
    )

    registrar = CompletionInputRegistrar(ledger)
    assert registrar.registered_inputs("run-completion") == ()

    registered = registrar.write_insight(
        round_id="run-completion",
        insight_id="canonical-insight",
        payload=payload,
        parent_refs=(),
        expected_revision=1,
    )

    assert registered.kind == "insight-digest"
    assert registrar.registered_inputs("run-completion") == (registered,)
    assert generic not in registrar.registered_inputs("run-completion")


def test_insight_registration_rejects_malformed_foreign_stale_and_quarantined_lineage(tmp_path: Path) -> None:
    from research_tree.completion_inputs import CompletionInputRegistrar

    ledger = RunLedger(tmp_path)
    ledger.create_run("run-completion")
    parent = ledger.append_artifact("run-completion", "finding", "finding-pack", {"value": 1}, expected_revision=0)
    payload = synthesize_insights((), active_slot_ids=())
    registrar = CompletionInputRegistrar(ledger)

    with pytest.raises(ValueError):
        registrar.write_insight(
            round_id="run-completion",
            insight_id="bad-schema",
            payload={"schema_version": 1},
            parent_refs=(),
            expected_revision=1,
        )
    with pytest.raises(LedgerIntegrityError, match="another run"):
        registrar.write_insight(
            round_id="run-completion",
            insight_id="foreign-parent",
            payload=dict(payload, parent_refs=["finding:finding"]),
            parent_refs=(ArtifactRef("other-run", "finding", 1),),
            expected_revision=1,
        )

    stale_payload = dict(payload, parent_refs=["finding:finding"])
    ledger.append_artifact("run-completion", "finding", "finding-pack", {"value": 2}, expected_revision=1)
    with pytest.raises(LedgerIntegrityError, match="stale or quarantined"):
        registrar.write_insight(
            round_id="run-completion",
            insight_id="stale-parent",
            payload=stale_payload,
            parent_refs=(ArtifactRef("run-completion", parent.id, parent.revision),),
            expected_revision=2,
        )

    current = ledger.get_artifact(ArtifactRef("run-completion", "finding", 2))
    ledger.append_artifact(
        "run-completion",
        "quarantine",
        "stale-state-quarantine",
        {"dependent_refs": [ArtifactRef("run-completion", current.id, current.revision).to_dict()]},
        expected_revision=2,
    )
    with pytest.raises(LedgerIntegrityError, match="stale or quarantined"):
        registrar.write_insight(
            round_id="run-completion",
            insight_id="quarantined-parent",
            payload=stale_payload,
            parent_refs=(ArtifactRef("run-completion", current.id, current.revision),),
            expected_revision=3,
        )
    assert registrar.registered_inputs("run-completion") == ()


def test_registration_is_revision_checked_and_rolls_back_artifact_and_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from research_tree.completion_inputs import CompletionInputRegistrar

    ledger = RunLedger(tmp_path)
    ledger.create_run("run-completion")
    registrar = CompletionInputRegistrar(ledger)
    payload = synthesize_insights((), active_slot_ids=())

    with pytest.raises(LedgerConflictError):
        registrar.write_insight(
            round_id="run-completion",
            insight_id="wrong-revision",
            payload=payload,
            parent_refs=(),
            expected_revision=1,
        )
    monkeypatch.setattr(ledger, "_before_commit", lambda: (_ for _ in ()).throw(RuntimeError("injected")))
    with pytest.raises(RuntimeError, match="injected"):
        registrar.write_insight(
            round_id="run-completion",
            insight_id="atomic-insight",
            payload=payload,
            parent_refs=(),
            expected_revision=0,
        )
    assert ledger.load_run("run-completion").artifacts == ()
    assert registrar.registered_inputs("run-completion") == ()
