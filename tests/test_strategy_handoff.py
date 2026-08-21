from __future__ import annotations

import pytest

from research_tree.coordinator import CoordinatorConflictError, IllegalTransitionError, ResearchRunCoordinator
from research_tree.domain import ArtifactRef
from research_tree.decision_frame import DecisionFrame, IntentHypothesis
from research_tree.run_ledger import RunLedger
from research_tree.strategy_projection import StrategyProjection


def _append(ledger: RunLedger, run_id: str, artifact_id: str, kind: str, payload: dict, parents=()):
    return ledger.append_artifact(
        run_id, artifact_id, kind, payload, parent_refs=parents, expected_revision=ledger.get_revision(run_id)
    )


def _context(tmp_path):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-85")
    handoff = _append(ledger, "run-85", "handoff-1", "alignment-handoff", {"confirmed": True})
    target = _append(
        ledger,
        "run-85",
        "target-1",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1"}]},
        (ArtifactRef("run-85", handoff.id, handoff.revision),),
    )
    coordinator = ResearchRunCoordinator(ledger)
    state = coordinator.initialize(
        run_id="run-85",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-85"),
    )
    return ledger, coordinator, handoff, target, state


def _frame(coordinator: ResearchRunCoordinator, ledger: RunLedger, target):
    frame = DecisionFrame.create(
        frame_id="frame-1",
        run_id="run-85",
        requester_wording="Choose the customer decision to validate.",
        primary_decision={"id": "decision-1", "statement": "Choose the customer decision", "success_signal": "signal"},
        target_ref=ArtifactRef("run-85", target.id, target.revision),
        hypotheses=(
            IntentHypothesis(
                id="selected",
                interpretation="selected decision",
                ambiguity="explicit",
                owner="requester",
                researchable=False,
                decision_consequence="sets scope",
                source_refs=("input-1",),
                disposition="selected",
                next_action="form strategy",
                primary_decision_id="decision-1",
                material=True,
                evidence_ranked=True,
            ),
        ),
    )
    return coordinator.persist_decision_frame(frame, expected_revision=ledger.get_revision("run-85"))


def _projection(ledger, coordinator, handoff, target):
    frame_ref = _frame(coordinator, ledger, target)
    projection = StrategyProjection.create(
        projection_id="projection-1",
        run_id="run-85",
        decision_frame_ref=ArtifactRef("run-85", frame_ref.id, frame_ref.revision),
        alignment_handoff_ref=ArtifactRef("run-85", handoff.id, handoff.revision),
        target_ref=ArtifactRef("run-85", target.id, target.revision),
        current_understanding="Validate the requester decision.",
        assumptions=("requester owns outcome",),
        decision_targets=("decision-1",),
        tracks=({"id": "track-1", "question": "What evidence is decisive?"},),
        method_hypotheses=({"method": "repository"},),
        depth="deep",
        evidence_expectations=("independent source",),
        autonomy_envelope={"allowed": ["research"]},
        replanning_policy={"same_round": ["depth"]},
        success_oracles=("oracle-1",),
        delivery_contract={"technical": "package", "human": "report"},
        stop_rule="oracles pass",
        preference_influences=(),
        revision=1,
        status="displayed",
    )
    return coordinator.persist_strategy_projection(projection, expected_revision=ledger.get_revision("run-85"))


def test_direct_stage_skip_and_generic_confirmation_are_fail_closed(tmp_path) -> None:
    ledger, coordinator, _, _, state = _context(tmp_path)
    with pytest.raises(IllegalTransitionError, match="projection"):
        coordinator.transition(
            "run-85", "alignment_projection_ready", "coordinator", expected_revision=ledger.get_revision("run-85")
        )
    assert coordinator.state("run-85") == state
    assert not any(item.kind == "lifecycle-event" for item in ledger.load_run("run-85").artifacts)

    # A displayed projection still cannot be authorized by a generic response.
    handoff, target = (
        next(item for item in ledger.load_run("run-85").artifacts if item.kind == "alignment-handoff"),
        next(item for item in ledger.load_run("run-85").artifacts if item.kind == "blueprint-target"),
    )
    projection = _projection(ledger, coordinator, handoff, target)
    coordinator.display_strategy("run-85", projection, expected_revision=ledger.get_revision("run-85"))
    before = ledger.get_revision("run-85")
    with pytest.raises(CoordinatorConflictError, match="generic"):
        coordinator.confirm_handoff(
            "run-85",
            projection_ref=ArtifactRef("run-85", projection.id, projection.revision),
            confirmation="okay",
            expected_revision=before,
        )
    assert ledger.get_revision("run-85") == before


def test_contextual_confirmation_replays_and_stale_digest_rejects(tmp_path) -> None:
    ledger, coordinator, handoff, target, _ = _context(tmp_path)
    projection = _projection(ledger, coordinator, handoff, target)
    displayed = coordinator.display_strategy("run-85", projection, expected_revision=ledger.get_revision("run-85"))
    confirmed = coordinator.confirm_handoff(
        "run-85",
        projection_ref=ArtifactRef("run-85", projection.id, projection.revision),
        confirmation=f"I accept the displayed strategy {projection.display_digest} and authorize research within it.",
        expected_revision=ledger.get_revision("run-85"),
        idempotency_key="confirm-1",
    )
    assert confirmed.payload["state"] == "autonomous_research"
    assert (
        coordinator.confirm_handoff(
            "run-85",
            projection_ref=ArtifactRef("run-85", projection.id, projection.revision),
            confirmation=f"I accept the displayed strategy {projection.display_digest} and authorize research within it.",
            expected_revision=0,
            idempotency_key="confirm-1",
        )
        == confirmed
    )
    assert displayed.payload["macro_stage"] == 2


def test_same_round_revision_invalidates_confirmation_and_fault_rolls_back(tmp_path, monkeypatch) -> None:
    ledger, coordinator, handoff, target, _ = _context(tmp_path)
    projection = _projection(ledger, coordinator, handoff, target)
    before = ledger.get_revision("run-85")
    revised = coordinator.revise_strategy(
        "run-85",
        projection_ref=ArtifactRef("run-85", projection.id, projection.revision),
        changes={"depth": "recursive"},
        expected_revision=before,
    )
    assert revised.payload["revision"] == 2
    assert revised.parent_refs[0].artifact_id == projection.id
    assert coordinator.state("run-85").payload["state"] == "alignment"

    def fail() -> None:
        raise RuntimeError("projection fault")

    monkeypatch.setattr(RunLedger, "_before_commit", staticmethod(fail))
    with pytest.raises(CoordinatorConflictError, match="conflict"):
        coordinator.persist_strategy_projection(projection, expected_revision=ledger.get_revision("run-85"))
    assert ledger.get_revision("run-85") == before + 1
