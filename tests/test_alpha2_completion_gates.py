import pytest

from research_tree import ResearchRunCoordinator, SQLiteRunLedger
from tests.alpha2_runtime_helpers import satisfy_p0_closure


def _advance_to_research(coordinator):
    state = coordinator.create("run-1", authority={"scope": "research"})
    state = coordinator.transition("run-1", event="alignment_projection_ready", actor="coordinator", expected_revision=state["revision"], payload={"strategy_digest": state["authority_digest"]})
    return coordinator.transition("run-1", event="handoff_confirmed", actor="human", expected_revision=state["revision"], payload={"displayed_digest": state["authority_digest"]})


def test_coordinator_rejects_false_completion_and_lists_each_obligation(tmp_path):
    coordinator = ResearchRunCoordinator(tmp_path)
    state = _advance_to_research(coordinator)
    with pytest.raises(coordinator.error_type) as error:
        coordinator.transition("run-1", event="batch_checkpoint", actor="coordinator", expected_revision=state["revision"])
        coordinator.transition("run-1", event="all_slots_closed", actor="coordinator", expected_revision=state["revision"] + 1)
    assert error.value.code == "completion_gate_failed"
    why = coordinator.why_not_complete("run-1")
    assert "p0_closure" in why["unmet_obligations"]
    assert "acceptance" in why["unmet_obligations"]


def test_exact_delivery_pair_is_required_for_completion(tmp_path):
    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    state = _advance_to_research(coordinator)
    state = satisfy_p0_closure(ledger, state)
    state = coordinator.record_obligation("run-1", "insight_clear", evidence_ref="insight-evidence", expected_revision=state["revision"])
    state = coordinator.transition("run-1", event="batch_checkpoint", actor="coordinator", expected_revision=state["revision"])
    state = coordinator.transition("run-1", event="all_slots_closed", actor="coordinator", expected_revision=state["revision"])
    for name in ("readiness", "evaluation"):
        state = coordinator.record_obligation("run-1", name, evidence_ref=name + "-evidence", expected_revision=state["revision"])
    state = coordinator.transition("run-1", event="readiness_passed", actor="coordinator", expected_revision=state["revision"])
    state = coordinator.deliver("run-1", expected_revision=state["revision"], technical_digest="tech-1", human_digest="human-1")
    displayed_digest = coordinator.delivery_pair_digest(
        "run-1", "tech-1", "human-1"
    )
    assert state["displayed_digest"] == displayed_digest
    assert coordinator.events("run-1")[-1]["payload"]["displayed_digest"] == displayed_digest
    with pytest.raises(coordinator.error_type) as error:
        coordinator.accept("run-1", expected_revision=state["revision"], displayed_digest=displayed_digest, technical_revision="tech-old", human_revision="human-1", feedback="I accept the exact reports.")
    assert error.value.code == "stale_acceptance"
    with pytest.raises(coordinator.error_type) as digest_error:
        coordinator.accept("run-1", expected_revision=state["revision"], displayed_digest="f" * 64, technical_revision="tech-1", human_revision="human-1", feedback="I accept the exact reports.")
    assert digest_error.value.code == "stale_acceptance"
    done = coordinator.accept("run-1", expected_revision=state["revision"], displayed_digest=displayed_digest, technical_revision="tech-1", human_revision="human-1", feedback="I accept the exact reports.")
    assert done["lifecycle_state"] == "completed"


def test_material_feedback_invalidates_prior_completion_evidence(tmp_path):
    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    state = coordinator.create("run-1")
    state = satisfy_p0_closure(ledger, state)
    assert coordinator.obligations("run-1")["p0_closure"]["satisfied"] is True
    coordinator.record_feedback({"feedback_id": "feedback-1", "run_id": "run-1", "actor": "human", "kind": "correction", "message": "The target is different.", "target_refs": ["task:target"], "materiality": "material", "created_at": "2026-08-05T00:00:00+00:00"}, expected_revision=state["revision"])
    assert all(not item["satisfied"] for item in coordinator.obligations("run-1").values())


def test_arbitrary_p0_obligation_cannot_bypass_core_closure(tmp_path):
    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-1")
    with pytest.raises(coordinator.error_type) as error:
        coordinator.record_obligation(
            "run-1", "p0_closure", evidence_ref="worker-says-passed",
            expected_revision=state["revision"],
        )
    assert error.value.code == "closure_aggregate_required"
