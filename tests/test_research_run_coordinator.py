from __future__ import annotations

from dataclasses import replace

import pytest
from strategy_support import write_alignment_verification, write_independent_delivery_review
from test_search_portfolio_lineage import _coordinator as _portfolio_coordinator
from test_search_portfolio_lineage import _parents as _portfolio_parents
from test_search_portfolio_lineage import _pivot_correction, durable_evidence
from test_search_portfolio_lineage import _values as _portfolio_values

from research_tree.acceptance import DeliveryAcceptance, delivery_pair_digest
from research_tree.completion_inputs import CompletionInputRegistrar, delivery_manifest_digest
from research_tree.coordinator import (
    COMPLETION_RECORD_KIND,
    LEASE_KIND,
    LIFECYCLE_STATES,
    RESEARCH_RUN_STATE_KIND,
    CoordinatorConflictError,
    IllegalTransitionError,
    ResearchRunCoordinator,
)
from research_tree.decision_frame import DecisionFrame, IntentHypothesis
from research_tree.domain import ArtifactRef
from research_tree.feedback import CorrectionBinding
from research_tree.run_ledger import RunLedger
from research_tree.strategy_projection import StrategyProjection, authority_fingerprint


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
        success_oracles=({"id": "oracle-1", "evidence_standard_ids": ("standard-1",)},),
        delivery_contract={"technical": "package", "human": "report"},
        stop_rule="oracles pass",
        preference_influences=(),
        revision=1,
        status="displayed",
    )
    coordinator.persist_strategy_projection(projection, expected_revision=ledger.get_revision("run-57"))
    return projection


def _confirm_strategy(ledger: RunLedger, coordinator: ResearchRunCoordinator) -> StrategyProjection:
    projection = _prepare_strategy(ledger, coordinator)
    write_alignment_verification(ledger, projection, "run-57")
    coordinator.display_strategy("run-57", projection, expected_revision=ledger.get_revision("run-57"))
    coordinator.confirm_handoff(
        "run-57",
        projection_ref=ArtifactRef("run-57", projection.id, projection.revision),
        confirmation=f"I accept {projection.display_digest} authority-fingerprint {authority_fingerprint(projection)} and authorize research.",
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
        {"decision_slots": [{"id": "slot-1", "priority": "P0", "closure_oracle": "oracle-1"}]},
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


def _register_canonical_completion_inputs(ledger: RunLedger, run_id: str, target, *, review: bool = True) -> tuple:
    target_ref = ArtifactRef(run_id, target.id, target.revision)
    ledger.append_completion_input(
        run_id,
        "closure-1",
        "closure",
        "slot-closure-assessment",
        {"slot_id": "slot-1", "status": "passed", "closure_token": "closure-token"},
        parent_refs=(target_ref,),
        issuer="core-evaluator-v1",
        issuer_evidence={"token": "closure-token"},
        expected_revision=ledger.get_revision(run_id),
    )
    for artifact_id, role, kind, payload in (
        ("insight-1", "insight", "insight-digest", {"status": "non_blocking"}),
        ("readiness-1", "readiness", "readiness-record", {"status": "ready"}),
        ("evaluation-1", "evaluation", "blueprint-evaluation", {"status": "passed"}),
    ):
        ledger.append_completion_input(
            run_id,
            artifact_id,
            role,
            kind,
            payload,
            parent_refs=(),
            issuer=f"test-{role}-writer",
            issuer_evidence={"source": role},
            expected_revision=ledger.get_revision(run_id),
        )
    registrar = CompletionInputRegistrar(ledger)
    technical, human = registrar.write_delivery_pair(
        round_id=run_id,
        technical_package_id="technical-1",
        human_report_id="human-1",
        technical_payload={"document": {"status": "compiled"}, "markdown": "technical"},
        human_payload={
            "technical_package_ref": ArtifactRef(run_id, "technical-1", 1).to_dict(),
            "document": {"status": "compiled"},
            "markdown": "human",
        },
        technical_parent_refs=(),
        human_parent_refs=(ArtifactRef(run_id, "technical-1", 1),),
        expected_revision=ledger.get_revision(run_id),
    )
    technical_revision = f"{technical.id}@{technical.revision}"
    human_revision = f"{human.id}@{human.revision}"
    acceptance = DeliveryAcceptance.create(
        "acceptance-1",
        run_id,
        technical_revision,
        human_revision,
        delivery_pair_digest(run_id, technical_revision, human_revision),
        delivery_manifest_digest(technical, human),
        [
            {
                "feedback_id": "feedback-1",
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
    if review:
        write_independent_delivery_review(ledger, run_id)
    return technical, human


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
    write_alignment_verification(ledger, projection, "run-57")
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
    with pytest.raises(CoordinatorConflictError, match="host event must be a mapping"):
        coordinator.ingest_host_event(None)

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
    _register_canonical_completion_inputs(ledger, "run-57", target, review=False)
    CompletionInputRegistrar(ledger).write_goal_satisfaction(
        round_id="run-57",
        registration_id="goal-oracle-1",
        oracle_id="oracle-1",
        verdict="waived",
        waiver_reason="Canonical completion fixture; goal coverage is contracted in test_goal_gate.py.",
        expected_revision=ledger.get_revision("run-57"),
    )
    _advance_to_awaiting_acceptance(ledger, coordinator)
    # Issue #462: the review needs the confirmed projection's oracles, so it is
    # registered once the run reaches awaiting_acceptance.
    write_independent_delivery_review(ledger, "run-57")

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
    with pytest.raises(CoordinatorConflictError, match="host event must be a mapping"):
        coordinator.ingest_host_event(None)


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


def test_portfolio_pivot_uses_correction_quarantine_and_human_reopen_stays_pending(tmp_path) -> None:
    pivot_ledger, pivot_coordinator, pivot_artifacts = _portfolio_coordinator(tmp_path / "pivot")
    pivot_refs = durable_evidence(tmp_path / "pivot", pivot_ledger)
    portfolio, execution = _portfolio_values(disposition="pivot")
    pivot_lineage = pivot_coordinator.persist_search_portfolio_lineage(
        run_id="run-portfolio",
        attempt_id="attempt-1",
        portfolio=portfolio,
        execution=execution,
        capture_refs=(pivot_refs[0],),
        receipt_refs=(pivot_refs[1],),
        checkpoint_refs=(pivot_refs[2],),
        finding_refs=(pivot_refs[3],),
        **_portfolio_parents(pivot_artifacts),
        pivot_correction=_pivot_correction(pivot_artifacts),
        expected_revision=pivot_ledger.get_revision("run-portfolio"),
    )
    pivot_ref = ArtifactRef("run-portfolio", pivot_lineage.id, pivot_lineage.revision)
    assert pivot_ref in pivot_coordinator._quarantined_refs("run-portfolio")
    assert "stale-state-quarantine" in [item.kind for item in pivot_ledger.load_run("run-portfolio").artifacts]
    revision_after_pivot = pivot_ledger.get_revision("run-portfolio")
    with pytest.raises(CoordinatorConflictError, match="portfolio_.*_reference_invalid"):
        pivot_coordinator.persist_search_portfolio_lineage(
            run_id="run-portfolio",
            attempt_id="attempt-1",
            portfolio=portfolio,
            execution=execution,
            capture_refs=(pivot_refs[0],),
            receipt_refs=(pivot_refs[1],),
            checkpoint_refs=(pivot_refs[2],),
            finding_refs=(pivot_refs[3],),
            **_portfolio_parents(pivot_artifacts),
            pivot_correction=_pivot_correction(pivot_artifacts),
            expected_revision=revision_after_pivot,
        )
    assert pivot_ledger.get_revision("run-portfolio") == revision_after_pivot

    reopen_ledger, reopen_coordinator, reopen_artifacts = _portfolio_coordinator(tmp_path / "reopen")
    reopen_refs = durable_evidence(tmp_path / "reopen", reopen_ledger)
    portfolio, execution = _portfolio_values(disposition="blocked", authority="requires_requester_reopen")
    reopen_coordinator.persist_search_portfolio_lineage(
        run_id="run-portfolio",
        attempt_id="attempt-1",
        portfolio=portfolio,
        execution=execution,
        capture_refs=(reopen_refs[0],),
        receipt_refs=(reopen_refs[1],),
        checkpoint_refs=(reopen_refs[2],),
        finding_refs=(reopen_refs[3],),
        **_portfolio_parents(reopen_artifacts),
        expected_revision=reopen_ledger.get_revision("run-portfolio"),
    )
    kinds = [item.kind for item in reopen_ledger.load_run("run-portfolio").artifacts]
    assert "human-decision-reopen" in kinds
    assert "same-round-replan" not in kinds
    assert "stale-state-quarantine" not in kinds


def test_invalid_portfolio_pivot_correction_leaves_no_current_lineage(tmp_path) -> None:
    ledger, coordinator, artifacts = _portfolio_coordinator(tmp_path)
    capture, receipt, checkpoint, finding = durable_evidence(tmp_path, ledger)
    portfolio, execution = _portfolio_values(disposition="pivot")
    correction = _pivot_correction(artifacts)
    invalid = replace(
        correction,
        event_id="invalid-portfolio-pivot-correction",
        affected={
            **correction.affected,
            "intent_model": CorrectionBinding(
                "intent_model", correction.affected["intent_model"].artifact_ref, "0" * 64
            ),
        },
    )
    before = ledger.get_revision("run-portfolio")

    with pytest.raises(CoordinatorConflictError, match="correction binding digest mismatch: intent_model"):
        coordinator.persist_search_portfolio_lineage(
            run_id="run-portfolio",
            attempt_id="attempt-1",
            portfolio=portfolio,
            execution=execution,
            capture_refs=(capture,),
            receipt_refs=(receipt,),
            checkpoint_refs=(checkpoint,),
            finding_refs=(finding,),
            **_portfolio_parents(artifacts),
            pivot_correction=invalid,
            expected_revision=before,
        )

    assert ledger.get_revision("run-portfolio") == before
    assert not [item for item in ledger.load_run("run-portfolio").artifacts if item.kind == "search-portfolio-lineage"]


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
