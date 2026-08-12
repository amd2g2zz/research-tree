from __future__ import annotations

import pytest

from research_tree.coordinator import (
    COMPLETION_RECORD_KIND,
    IllegalTransitionError,
    CoordinatorConflictError,
    CoordinatorEventConflictError,
    LEASE_KIND,
    LIFECYCLE_STATES,
    RESEARCH_RUN_STATE_KIND,
    ResearchRunCoordinator,
)
from research_tree.domain import ArtifactRef
from research_tree.decision_frame import DecisionFrame, IntentHypothesis
from research_tree.run_ledger import RunLedger
from research_tree.strategy_projection import StrategyProjection


def _append(ledger: RunLedger, run_id: str, artifact_id: str, kind: str, payload: dict, parents=()):
    return ledger.append_artifact(
        run_id,
        artifact_id,
        kind,
        payload,
        parent_refs=parents,
        expected_revision=ledger.get_revision(run_id),
    )


def _ready_frame(
    run_id: str = "run-57", frame_id: str = "frame-1", target_ref: ArtifactRef | None = None
) -> DecisionFrame:
    return DecisionFrame.create(
        frame_id=frame_id,
        run_id=run_id,
        requester_wording="Choose the customer decision to validate.",
        primary_decision={
            "id": "decision-1",
            "statement": "Choose the customer decision",
            "success_signal": "The payer and validation signal are explicit",
        },
        hypotheses=(
            IntentHypothesis(
                id="selected",
                interpretation="The selected customer decision",
                ambiguity="The choice is now explicit",
                owner="requester",
                researchable=False,
                decision_consequence="sets the research scope",
                source_refs=("input-1",),
                disposition="selected",
                next_action="form strategy",
                primary_decision_id="decision-1",
                material=True,
                evidence_ranked=True,
            ),
        ),
        target_ref=target_ref,
    )


def _prepare_strategy(ledger: RunLedger, coordinator: ResearchRunCoordinator) -> StrategyProjection:
    artifacts = ledger.load_run("run-57").artifacts
    handoff = next(item for item in artifacts if item.kind == "alignment-handoff")
    target = next(item for item in artifacts if item.kind == "blueprint-target")
    target_ref = ArtifactRef("run-57", target.id, target.revision)
    frame = coordinator.persist_decision_frame(
        _ready_frame(frame_id="strategy-frame", target_ref=target_ref),
        expected_revision=ledger.get_revision("run-57"),
    )
    projection = StrategyProjection.create(
        projection_id="strategy-projection",
        run_id="run-57",
        decision_frame_ref=ArtifactRef("run-57", frame.id, frame.revision),
        alignment_handoff_ref=ArtifactRef("run-57", handoff.id, handoff.revision),
        target_ref=target_ref,
        current_understanding="Validate the requester decision.",
        assumptions=("requester owns outcome",),
        decision_targets=("decision-1",),
        tracks=({"id": "track-1"},),
        method_hypotheses=({"method": "repository"},),
        depth="deep",
        evidence_expectations=("independent source",),
        autonomy_envelope={"allowed": ["research"]},
        replanning_policy={"same_round": ["depth"]},
        success_oracles=("oracle-1",),
        delivery_contract={"technical": "package", "human": "report"},
        stop_rule="oracles pass",
        revision=1,
        status="displayed",
    )
    coordinator.persist_strategy_projection(projection, expected_revision=ledger.get_revision("run-57"))
    return projection


def _confirm_strategy(ledger: RunLedger, coordinator: ResearchRunCoordinator) -> StrategyProjection:
    projection = _prepare_strategy(ledger, coordinator)
    coordinator.display_strategy("run-57", projection, expected_revision=ledger.get_revision("run-57"))
    coordinator.confirm_handoff(
        "run-57",
        projection_ref=ArtifactRef("run-57", projection.id, projection.revision),
        confirmation=f"I accept {projection.display_digest} and authorize research.",
        expected_revision=ledger.get_revision("run-57"),
    )
    return projection


def _setup(tmp_path):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-57")
    handoff = _append(ledger, "run-57", "handoff-1", "alignment-handoff", {"confirmed": True})
    target = _append(
        ledger,
        "run-57",
        "target-1",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1", "priority": "P0"}]},
        (ArtifactRef("run-57", handoff.id, handoff.revision),),
    )
    return ledger, ResearchRunCoordinator(ledger), handoff, target


def _initialize(tmp_path):
    ledger, coordinator, handoff, target = _setup(tmp_path)
    state = coordinator.initialize(
        run_id="run-57",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-57"),
        idempotency_key="init-1",
    )
    return ledger, coordinator, handoff, target, state


def _advance_to_awaiting_acceptance(ledger: RunLedger, coordinator: ResearchRunCoordinator) -> None:
    _confirm_strategy(ledger, coordinator)
    coordinator.transition("run-57", "batch_checkpoint", "coordinator", expected_revision=ledger.get_revision("run-57"))
    coordinator.transition("run-57", "all_slots_closed", "coordinator", expected_revision=ledger.get_revision("run-57"))
    coordinator.transition("run-57", "readiness_passed", "coordinator", expected_revision=ledger.get_revision("run-57"))
    coordinator.transition(
        "run-57", "deliveries_compiled", "coordinator", expected_revision=ledger.get_revision("run-57")
    )


def test_initialization_requires_exact_lineage_and_is_idempotent(tmp_path) -> None:
    ledger, coordinator, handoff, target = _setup(tmp_path)
    state = coordinator.initialize(
        run_id="run-57",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-57"),
        idempotency_key="init-1",
    )
    replay = coordinator.initialize(
        run_id="run-57",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=0,
        idempotency_key="init-1",
    )

    assert state == replay
    assert state.kind == RESEARCH_RUN_STATE_KIND
    assert state.payload["state"] == "alignment"
    assert state.payload["state_digest"]
    assert set(LIFECYCLE_STATES) >= {"alignment", "completed", "superseded"}


def test_initialization_rejects_foreign_or_unbound_blueprint(tmp_path) -> None:
    ledger, coordinator, handoff, _ = _setup(tmp_path)
    foreign = _append(ledger, "run-57", "target-foreign", "blueprint-target", {"decision_slots": []})

    with pytest.raises(CoordinatorConflictError, match="lineage"):
        coordinator.initialize(
            run_id="run-57",
            alignment_handoff=handoff,
            blueprint_target=foreign,
            expected_revision=ledger.get_revision("run-57"),
        )


def test_illegal_transition_is_rejected_without_state_mutation(tmp_path) -> None:
    ledger, coordinator, _, _, state = _initialize(tmp_path)

    with pytest.raises(IllegalTransitionError, match="illegal_transition"):
        coordinator.transition(
            run_id="run-57",
            event="delivery_accepted",
            actor="human",
            expected_revision=ledger.get_revision("run-57"),
        )

    assert coordinator.state("run-57") == state
    assert any(item.kind == "lifecycle-rejection" for item in ledger.load_run("run-57").artifacts)


def test_legal_transition_enforces_matrix_actor_and_replay(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection = _prepare_strategy(ledger, coordinator)
    first = coordinator.display_strategy(
        "run-57", projection, expected_revision=ledger.get_revision("run-57"), idempotency_key="projection-1"
    )
    replay = coordinator.display_strategy("run-57", projection, expected_revision=0, idempotency_key="projection-1")

    assert first == replay
    assert first.payload["state"] == "handoff_pending"

    with pytest.raises(IllegalTransitionError, match="actor"):
        coordinator.transition(
            run_id="run-57",
            event="handoff_confirmed",
            actor="worker",
            expected_revision=ledger.get_revision("run-57"),
        )


def test_completion_exposes_all_missing_obligations_and_ignores_worker_finish(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    coordinator.ingest_event(
        run_id="run-57",
        event_id="host-finished-1",
        attempt_id="attempt-1",
        payload={"worker_status": "finished", "all_tasks": True},
        expected_revision=ledger.get_revision("run-57"),
    )

    missing = coordinator.why_not_complete("run-57")
    assert "p0_closure_tokens" in missing["unmet_obligations"]
    assert coordinator.state("run-57").payload["state"] == "autonomous_research"

    coordinator.transition("run-57", "batch_checkpoint", "coordinator", expected_revision=ledger.get_revision("run-57"))
    with pytest.raises(IllegalTransitionError, match="guard_failed"):
        coordinator.transition(
            "run-57", "all_slots_closed", "coordinator", expected_revision=ledger.get_revision("run-57")
        )
    assert coordinator.state("run-57").payload["state"] == "synthesis"


def test_completion_requires_all_canonical_obligations_and_is_terminally_idempotent(tmp_path) -> None:
    ledger, coordinator, _, target, _ = _initialize(tmp_path)
    _append(
        ledger,
        "run-57",
        "closure-1",
        "slot-closure-assessment",
        {"slot_id": "slot-1", "status": "passed", "closure_token": "closure-token"},
        (ArtifactRef("run-57", target.id, target.revision),),
    )
    _append(ledger, "run-57", "insight-1", "insight-digest", {"status": "non_blocking"})
    _append(ledger, "run-57", "readiness-1", "readiness-record", {"status": "ready"})
    _append(ledger, "run-57", "evaluation-1", "blueprint-evaluation", {"status": "passed"})
    technical = _append(ledger, "run-57", "technical-1", "technical-research-package", {"status": "compiled"})
    human = _append(ledger, "run-57", "human-1", "human-research-report", {"status": "compiled"})
    _append(
        ledger,
        "run-57",
        "acceptance-1",
        "delivery-acceptance",
        {"decision": "accepted"},
        (ArtifactRef("run-57", technical.id, technical.revision), ArtifactRef("run-57", human.id, human.revision)),
    )
    _advance_to_awaiting_acceptance(ledger, coordinator)

    completed = coordinator.transition(
        "run-57", "delivery_accepted", "human", expected_revision=ledger.get_revision("run-57")
    )
    replay = coordinator.complete("run-57", actor="human", expected_revision=0)

    assert completed.payload["state"] == "completed"
    assert completed == replay
    assert completed.kind == RESEARCH_RUN_STATE_KIND
    assert any(
        item.id == "completion-record" and item.kind == COMPLETION_RECORD_KIND
        for item in ledger.load_run("run-57").artifacts
    )


def test_host_event_duplicate_is_idempotent_and_conflict_is_rejected(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    event = coordinator.ingest_event(
        run_id="run-57",
        event_id="event-1",
        attempt_id="attempt-1",
        payload={"kind": "finding", "value": 1},
        expected_revision=ledger.get_revision("run-57"),
    )
    replay = coordinator.ingest_event(
        run_id="run-57",
        event_id="event-1",
        attempt_id="attempt-1",
        payload={"kind": "finding", "value": 1},
        expected_revision=0,
    )
    assert event == replay

    with pytest.raises(CoordinatorEventConflictError, match="event_id_conflict"):
        coordinator.ingest_event(
            run_id="run-57",
            event_id="event-1",
            attempt_id="attempt-1",
            payload={"kind": "finding", "value": 2},
            expected_revision=0,
        )


def test_dispatch_requires_executable_oracle_and_recovery_quarantines_lease(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    with pytest.raises(CoordinatorConflictError, match="unverifiable_work_item"):
        coordinator.dispatch(
            run_id="run-57",
            work_item={"work_item_id": "work-1", "objective": "inspect"},
            worker_id="worker-1",
            expected_revision=ledger.get_revision("run-57"),
        )

    with pytest.raises(CoordinatorConflictError, match="strategy_projection"):
        coordinator.dispatch(
            run_id="run-57",
            work_item={"work_item_id": "work-1", "objective": "inspect", "success_oracle": "oracle-1"},
            worker_id="worker-1",
            expected_revision=ledger.get_revision("run-57"),
            attempt_id="attempt-1",
        )
    _confirm_strategy(ledger, coordinator)
    lease = coordinator.dispatch(
        run_id="run-57",
        work_item={"work_item_id": "work-1", "objective": "inspect", "success_oracle": "oracle-1"},
        worker_id="worker-1",
        expected_revision=ledger.get_revision("run-57"),
        attempt_id="attempt-1",
    )
    assert lease.kind == LEASE_KIND
    recovered = coordinator.recover("run-57")
    assert recovered["reconciled_attempts"] == ["attempt-1"]
    assert coordinator.recover("run-57")["reconciled_attempts"] == []


def test_decision_frame_gate_rejects_unready_without_mutation(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    frame = _ready_frame()
    blocked = DecisionFrame.create(
        frame_id=frame.frame_id,
        run_id=frame.run_id,
        requester_wording=frame.requester_wording,
        primary_decision=frame.primary_decision,
        hypotheses=(
            IntentHypothesis(
                id="unresolved",
                interpretation="A",
                ambiguity="B",
                owner="requester",
                researchable=False,
                decision_consequence="C",
                source_refs=("input-1",),
                disposition="unresolved",
                next_action="ask requester",
                primary_decision_id="decision-1",
            ),
            IntentHypothesis(
                id="other",
                interpretation="D",
                ambiguity="E",
                owner="requester",
                researchable=False,
                decision_consequence="F",
                source_refs=("input-1",),
                disposition="unresolved",
                next_action="ask requester",
                primary_decision_id="decision-1",
            ),
        ),
    )
    before = ledger.get_revision("run-57")
    artifact = coordinator.persist_decision_frame(blocked, expected_revision=before)
    after = ledger.get_revision("run-57")
    with pytest.raises(CoordinatorConflictError, match="ready_for_strategy"):
        coordinator.require_decision_frame(ArtifactRef("run-57", artifact.id, artifact.revision))
    assert after == before + 1
    assert coordinator.state("run-57").payload["state"] == "alignment"


def test_ready_frame_persistence_is_idempotent_and_exactly_current(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    frame = _ready_frame()
    artifact = coordinator.persist_decision_frame(frame, expected_revision=ledger.get_revision("run-57"))
    replay = coordinator.persist_decision_frame(frame, expected_revision=0)
    assert artifact == replay
    assert coordinator.require_decision_frame(ArtifactRef("run-57", artifact.id, artifact.revision)) == artifact


def test_frame_gate_rejects_cross_run_and_canonical_dispatch_bypass(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    before = ledger.get_revision("run-57")
    with pytest.raises(CoordinatorConflictError, match="decision_frame_required"):
        coordinator.dispatch(
            run_id="run-57",
            work_item={
                "work_item_id": "work-canonical",
                "objective": "inspect",
                "success_oracle": "oracle-1",
                "canonical": True,
            },
            worker_id="worker-1",
            expected_revision=before,
        )
    assert ledger.get_revision("run-57") == before

    ledger.create_run("run-other")
    frame = _ready_frame(run_id="run-other")
    frame_artifact = coordinator.persist_decision_frame(frame, expected_revision=ledger.get_revision("run-other"))
    with pytest.raises(CoordinatorConflictError, match="cross_run"):
        coordinator.require_decision_frame(
            ArtifactRef("run-other", frame_artifact.id, frame_artifact.revision), run_id="run-57"
        )


def test_ready_frame_is_retained_in_canonical_dispatch_lineage(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    frame_artifact = coordinator.persist_decision_frame(_ready_frame(), expected_revision=ledger.get_revision("run-57"))
    lease = coordinator.dispatch(
        run_id="run-57",
        work_item={
            "work_item_id": "work-canonical",
            "objective": "inspect",
            "success_oracle": "oracle-1",
            "canonical": True,
            "decision_frame_ref": ArtifactRef("run-57", frame_artifact.id, frame_artifact.revision).to_dict(),
        },
        worker_id="worker-1",
        expected_revision=ledger.get_revision("run-57"),
        attempt_id="attempt-canonical",
    )
    assert ArtifactRef("run-57", frame_artifact.id, frame_artifact.revision) in lease.parent_refs


def test_decision_frame_persistence_rolls_back_on_fault(tmp_path, monkeypatch) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    before = ledger.get_revision("run-57")

    def fail_before_commit() -> None:
        raise RuntimeError("injected frame failure")

    monkeypatch.setattr(RunLedger, "_before_commit", staticmethod(fail_before_commit))
    with pytest.raises(RuntimeError, match="injected frame failure"):
        coordinator.persist_decision_frame(_ready_frame(), expected_revision=before)
    assert ledger.get_revision("run-57") == before
    assert not [item for item in ledger.load_run("run-57").artifacts if item.kind == "decision-frame"]


def test_corrections_preserve_round_or_create_explicit_successor(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    replan = coordinator.record_same_round_replan(
        "run-57",
        reason="add a second independent source",
        expected_revision=ledger.get_revision("run-57"),
    )
    assert replan.kind == "same-round-replan"
    successor = coordinator.create_successor(
        "run-57",
        successor_run_id="run-57-next",
        reason="the target changed",
        expected_revision=ledger.get_revision("run-57"),
    )
    assert successor.payload["state"] == "superseded"
    assert ledger.load_run("run-57-next").record.parent_round_id == "run-57"


def test_transition_batch_fault_rolls_back_event_and_state(tmp_path, monkeypatch) -> None:
    ledger, coordinator, _, _, state = _initialize(tmp_path)
    before = ledger.get_revision("run-57")

    def fail_before_commit() -> None:
        raise RuntimeError("injected coordinator crash")

    monkeypatch.setattr(RunLedger, "_before_commit", staticmethod(fail_before_commit))
    with pytest.raises(RuntimeError, match="injected coordinator crash"):
        coordinator.transition(
            "run-57",
            "alignment_projection_ready",
            "coordinator",
            expected_revision=before,
        )

    assert ledger.get_revision("run-57") == before
    assert coordinator.state("run-57") == state
    assert not any(item.kind == "lifecycle-event" for item in ledger.load_run("run-57").artifacts)
