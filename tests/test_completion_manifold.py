from __future__ import annotations

from pathlib import Path

import pytest
from test_research_run_coordinator import _advance_to_awaiting_acceptance, _initialize

from research_tree.acceptance import DeliveryAcceptance, delivery_pair_digest
from research_tree.completion_inputs import CompletionInputRegistrar, delivery_manifest_digest
from research_tree.coordinator import COMPLETION_RECORD_KIND, CompletionBlockedError
from research_tree.domain import ArtifactRef
from research_tree.run_ledger import RunLedger


def _generic_chain(ledger: RunLedger, target) -> tuple:
    closure = ledger.append_completion_input(
        "run-57",
        "closure-generic",
        "closure",
        "slot-closure-assessment",
        {"slot_id": "slot-1", "status": "passed", "closure_token": "generic"},
        parent_refs=(ArtifactRef("run-57", target.id, target.revision),),
        issuer="generic-closure-writer",
        issuer_evidence={"source": "generic-test"},
        expected_revision=ledger.get_revision("run-57"),
    )
    for artifact_id, role, kind, payload, parents in (
        ("insight-generic", "insight", "insight-digest", {"status": "non_blocking"}, ()),
        ("readiness-generic", "readiness", "readiness-record", {"status": "ready"}, ()),
        ("evaluation-generic", "evaluation", "blueprint-evaluation", {"status": "passed"}, ()),
        ("technical-generic", "technical_delivery", "technical-research-package", {"status": "compiled"}, ()),
        (
            "human-generic",
            "human_delivery",
            "human-research-report",
            {
                "status": "compiled",
                "technical_package_ref": ArtifactRef("run-57", "technical-generic", 1).to_dict(),
            },
            (ArtifactRef("run-57", "technical-generic", 1),),
        ),
    ):
        ledger.append_completion_input(
            "run-57",
            artifact_id,
            role,
            kind,
            payload,
            parent_refs=parents,
            issuer=(
                "canonical-delivery-compiler-v1"
                if role in {"technical_delivery", "human_delivery"}
                else "generic-completion-writer"
            ),
            issuer_evidence={"source": "generic-test"},
            expected_revision=ledger.get_revision("run-57"),
        )
    ledger.append_artifact(
        "run-57",
        "acceptance-generic",
        "delivery-acceptance",
        {"decision": "accepted"},
        parent_refs=(
            ArtifactRef("run-57", "technical-generic", 1),
            ArtifactRef("run-57", "human-generic", 1),
        ),
        expected_revision=ledger.get_revision("run-57"),
    )
    return closure


def test_generic_latest_kind_chain_is_blocked_without_completion_record(tmp_path: Path) -> None:
    ledger, coordinator, _, target, _ = _initialize(tmp_path)
    _generic_chain(ledger, target)
    _advance_to_awaiting_acceptance(ledger, coordinator)

    with pytest.raises(CompletionBlockedError):
        coordinator.transition("run-57", "delivery_accepted", "human", expected_revision=ledger.get_revision("run-57"))

    why = coordinator.why_not_complete("run-57")
    assert "acceptance_ref" in why["unmet_obligations"]
    assert why["field_diagnostics"]["acceptance_ref"]["reason"] == "not_registered"
    assert not any(item.kind == COMPLETION_RECORD_KIND for item in ledger.load_run("run-57").artifacts)


def _register_minimal_manifold(ledger: RunLedger, target):
    registrar = CompletionInputRegistrar(ledger)
    run_id = "run-57"
    target_ref = ArtifactRef(run_id, target.id, target.revision)
    registrar.ledger.append_completion_input(
        run_id,
        "closure-registered",
        "closure",
        "slot-closure-assessment",
        {"slot_id": "slot-1", "status": "passed", "closure_token": "registered"},
        parent_refs=(target_ref,),
        issuer="core-evaluator-v1",
        issuer_evidence={"token": "registered"},
        expected_revision=ledger.get_revision(run_id),
    )
    for artifact_id, role, kind, payload in (
        ("insight-registered", "insight", "insight-digest", {"status": "non_blocking"}),
        ("readiness-registered", "readiness", "readiness-record", {"status": "ready"}),
        ("evaluation-registered", "evaluation", "blueprint-evaluation", {"status": "passed"}),
    ):
        ledger.append_completion_input(
            run_id,
            artifact_id,
            role,
            kind,
            payload,
            parent_refs=(),
            issuer=f"issuer-{role}",
            issuer_evidence={"source": role},
            expected_revision=ledger.get_revision(run_id),
        )
    technical, human = registrar.write_delivery_pair(
        round_id=run_id,
        technical_package_id="technical-registered",
        human_report_id="human-registered",
        technical_payload={"document": {"status": "compiled"}, "markdown": "technical"},
        human_payload={
            "technical_package_ref": ArtifactRef(run_id, "technical-registered", 1).to_dict(),
            "document": {"status": "compiled"},
            "markdown": "human",
        },
        technical_parent_refs=(),
        human_parent_refs=(ArtifactRef(run_id, "technical-registered", 1),),
        expected_revision=ledger.get_revision(run_id),
    )
    technical_revision = f"{technical.id}@{technical.revision}"
    human_revision = f"{human.id}@{human.revision}"
    acceptance = DeliveryAcceptance.create(
        "acceptance-registered",
        run_id,
        technical_revision,
        human_revision,
        delivery_pair_digest(run_id, technical_revision, human_revision),
        delivery_manifest_digest(technical, human),
        [
            {
                "feedback_id": "feedback-registered",
                "classification": "presentation",
                "statement": "I accept the displayed conclusions and trade-offs.",
                "target_refs": [technical.id, human.id],
            }
        ],
    )
    registrar.write_delivery_acceptance(
        round_id=run_id,
        technical_package=technical,
        human_research_report=human,
        acceptance=acceptance,
        expected_revision=ledger.get_revision(run_id),
    )


def test_registered_manifold_completes_once_and_records_digest(tmp_path: Path) -> None:
    ledger, coordinator, _, target, _ = _initialize(tmp_path)
    _register_minimal_manifold(ledger, target)
    _advance_to_awaiting_acceptance(ledger, coordinator)

    completed = coordinator.transition(
        "run-57", "delivery_accepted", "human", expected_revision=ledger.get_revision("run-57")
    )
    replay = coordinator.complete("run-57", actor="human", expected_revision=0)
    record = next(item for item in ledger.load_run("run-57").artifacts if item.kind == COMPLETION_RECORD_KIND)

    assert completed == replay
    assert record.payload["manifold_digest"]
    assert set(record.payload["manifold"]) == {
        "closure_refs",
        "insight_ref",
        "readiness_ref",
        "evaluation_ref",
        "technical_delivery_ref",
        "human_delivery_ref",
        "acceptance_ref",
    }
    assert coordinator.why_not_complete("run-57")["unmet_obligations"] == ()


def test_replaced_registered_parent_reopens_field_diagnostic(tmp_path: Path) -> None:
    ledger, coordinator, _, target, _ = _initialize(tmp_path)
    _register_minimal_manifold(ledger, target)
    _advance_to_awaiting_acceptance(ledger, coordinator)
    coordinator.transition("run-57", "delivery_accepted", "human", expected_revision=ledger.get_revision("run-57"))
    ledger.append_artifact(
        "run-57",
        "technical-registered",
        "technical-research-package",
        {"document": {"replacement": True}, "markdown": "replacement"},
        expected_revision=ledger.get_revision("run-57"),
    )

    why = coordinator.why_not_complete("run-57")
    assert why["field_diagnostics"]["technical_delivery_ref"]["reason"] in {"stale", "not_registered"}
    assert "technical_delivery_ref" in why["unmet_obligations"]


def test_ambiguous_singleton_registration_is_not_selected(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    for artifact_id in ("insight-a", "insight-b"):
        ledger.append_completion_input(
            "run-57",
            artifact_id,
            "insight",
            "insight-digest",
            {"status": "non_blocking"},
            parent_refs=(),
            issuer="test-insight-writer",
            issuer_evidence={"source": "ambiguous-test"},
            expected_revision=ledger.get_revision("run-57"),
        )

    why = coordinator.why_not_complete("run-57")

    assert why["field_diagnostics"]["insight_ref"]["reason"] == "ambiguous_registration"
    assert "insight_ref" in why["unmet_obligations"]


def test_quarantined_registered_parent_reopens_completion_without_mutating_history(tmp_path: Path) -> None:
    ledger, coordinator, _, target, _ = _initialize(tmp_path)
    _register_minimal_manifold(ledger, target)
    _advance_to_awaiting_acceptance(ledger, coordinator)
    coordinator.transition("run-57", "delivery_accepted", "human", expected_revision=ledger.get_revision("run-57"))
    technical = next(item for item in ledger.load_run("run-57").artifacts if item.id == "technical-registered")
    before = len(ledger.load_run("run-57").artifacts)
    ledger.append_artifact(
        "run-57",
        "quarantine-manifold-test",
        "stale-state-quarantine",
        {"stale_bindings": {}, "dependent_refs": [ArtifactRef("run-57", technical.id, technical.revision).to_dict()]},
        expected_revision=ledger.get_revision("run-57"),
    )

    why = coordinator.why_not_complete("run-57")

    assert why["field_diagnostics"]["technical_delivery_ref"]["reason"] == "not_registered"
    assert len(ledger.load_run("run-57").artifacts) == before + 1
    assert any(item.kind == COMPLETION_RECORD_KIND for item in ledger.load_run("run-57").artifacts)


def test_malformed_registered_delivery_ref_is_reported_as_lineage_mismatch(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    ledger.append_completion_input(
        "run-57",
        "technical-malformed",
        "technical_delivery",
        "technical-research-package",
        {"document": {}, "markdown": "technical"},
        parent_refs=(),
        issuer="canonical-delivery-compiler-v1",
        issuer_evidence={"surface": "technical"},
        expected_revision=ledger.get_revision("run-57"),
    )
    ledger.append_completion_input(
        "run-57",
        "human-malformed",
        "human_delivery",
        "human-research-report",
        {"technical_package_ref": {"malformed": True}, "document": {}, "markdown": "human"},
        parent_refs=(),
        issuer="canonical-delivery-compiler-v1",
        issuer_evidence={"surface": "human"},
        expected_revision=ledger.get_revision("run-57"),
    )

    why = coordinator.why_not_complete("run-57")

    assert why["field_diagnostics"]["technical_delivery_ref"]["reason"] == "pair_lineage_mismatch"
    assert why["field_diagnostics"]["human_delivery_ref"]["reason"] == "pair_lineage_mismatch"
