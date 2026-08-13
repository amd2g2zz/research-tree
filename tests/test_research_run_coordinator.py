from __future__ import annotations

from datetime import datetime, timezone

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
from research_tree.host_events import HostEvent
from research_tree.run_ledger import RunLedger
from research_tree.content_store import ContentAddressedStore
from research_tree.search_portfolio import (
    MethodBoundary,
    SearchPortfolioService,
    assess_acquisition_batch,
)
from research_tree.source_capture import DurableSourceCaptureService
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
        preference_influences=(),
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


def _method() -> MethodBoundary:
    return MethodBoundary(
        method_id="repo-inspect",
        provider_id="git",
        corpus_id="source-tree",
        boundary_kind="repository_inspection",
        permission_profile="local-read",
        expected_evidence_class="source",
        available=True,
        provenance_group="repository:workspace",
        invocation_adapter="local-repository-read",
        extraction_path="line-symbol-v1",
        failure_boundary="filesystem:workspace",
    )


def _portfolio_dispatch_setup(tmp_path):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-portfolio")
    coordinator = ResearchRunCoordinator(ledger)
    intent = _append(ledger, "run-portfolio", "intent-1", "intent-model", {"desired_outcomes": ["inspect source"]})
    brief = _append(
        ledger,
        "run-portfolio",
        "brief-1",
        "working-brief",
        {"working_interpretation": "inspect source", "technical_outcome": "bound evidence"},
        (ArtifactRef("run-portfolio", intent.id, intent.revision),),
    )
    handoff = _append(ledger, "run-portfolio", "handoff-1", "alignment-handoff", {"confirmed": True})
    target = _append(
        ledger,
        "run-portfolio",
        "target-1",
        "blueprint-target",
        {"slots": [{"id": "slot-1", "question": "Which source confirms the mechanism?"}]},
        (
            ArtifactRef("run-portfolio", intent.id, intent.revision),
            ArtifactRef("run-portfolio", brief.id, brief.revision),
            ArtifactRef("run-portfolio", handoff.id, handoff.revision),
        ),
    )
    coordinator.initialize(
        run_id="run-portfolio",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    frame = coordinator.persist_decision_frame(
        _ready_frame(
            run_id="run-portfolio",
            frame_id="portfolio-frame",
            target_ref=ArtifactRef("run-portfolio", target.id, target.revision),
        ),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    projection = StrategyProjection.create(
        projection_id="portfolio-strategy",
        run_id="run-portfolio",
        decision_frame_ref=ArtifactRef("run-portfolio", frame.id, frame.revision),
        alignment_handoff_ref=ArtifactRef("run-portfolio", handoff.id, handoff.revision),
        target_ref=ArtifactRef("run-portfolio", target.id, target.revision),
        current_understanding="Inspect the source boundary.",
        assumptions=("research is bounded",),
        decision_targets=("slot-1",),
        tracks=({"id": "track-1"},),
        method_hypotheses=({"method": "repository"},),
        depth="deep",
        evidence_expectations=("source",),
        autonomy_envelope={"allowed": ["research"]},
        replanning_policy={"same_round": ["depth"]},
        success_oracles=("oracle-1",),
        delivery_contract={"technical": "package", "human": "report"},
        stop_rule="oracle passes",
        preference_influences=(),
        revision=1,
        status="displayed",
    )
    coordinator.persist_strategy_projection(projection, expected_revision=ledger.get_revision("run-portfolio"))
    coordinator.display_strategy("run-portfolio", projection, expected_revision=ledger.get_revision("run-portfolio"))
    coordinator.confirm_handoff(
        "run-portfolio",
        projection_ref=ArtifactRef("run-portfolio", projection.id, projection.revision),
        confirmation=f"I accept {projection.display_digest} and authorize research.",
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    strategy = ledger.get_artifact(ArtifactRef("run-portfolio", projection.id, projection.revision))
    portfolio = SearchPortfolioService(ledger).plan(
        run_id="run-portfolio",
        portfolio_id="portfolio-valid",
        intent_model=intent,
        working_brief=brief,
        strategy=strategy,
        decision_map=target,
        slot={"slot_id": "slot-1", "question": "Which source confirms the mechanism?", "closure_oracle": "oracle-1"},
        authority_envelope="confirmed research",
        available_methods=(_method(),),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    return ledger, coordinator, portfolio


def test_acquisition_dispatch_requires_current_search_portfolio_lineage(tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-portfolio")
    coordinator = ResearchRunCoordinator(ledger)
    intent = _append(ledger, "run-portfolio", "intent-1", "intent-model", {"desired_outcomes": ["inspect source"]})
    brief = _append(
        ledger,
        "run-portfolio",
        "brief-1",
        "working-brief",
        {"working_interpretation": "inspect source", "technical_outcome": "bound evidence"},
        (ArtifactRef("run-portfolio", intent.id, intent.revision),),
    )
    handoff = _append(ledger, "run-portfolio", "handoff-1", "alignment-handoff", {"confirmed": True})
    target = _append(
        ledger,
        "run-portfolio",
        "target-1",
        "blueprint-target",
        {"slots": [{"id": "slot-1", "question": "Which source confirms the mechanism?"}]},
        (
            ArtifactRef("run-portfolio", intent.id, intent.revision),
            ArtifactRef("run-portfolio", brief.id, brief.revision),
            ArtifactRef("run-portfolio", handoff.id, handoff.revision),
        ),
    )
    coordinator.initialize(
        run_id="run-portfolio",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    frame = coordinator.persist_decision_frame(
        _ready_frame(
            run_id="run-portfolio",
            frame_id="portfolio-frame",
            target_ref=ArtifactRef("run-portfolio", target.id, target.revision),
        ),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    projection = StrategyProjection.create(
        projection_id="portfolio-strategy",
        run_id="run-portfolio",
        decision_frame_ref=ArtifactRef("run-portfolio", frame.id, frame.revision),
        alignment_handoff_ref=ArtifactRef("run-portfolio", handoff.id, handoff.revision),
        target_ref=ArtifactRef("run-portfolio", target.id, target.revision),
        current_understanding="Inspect the source boundary.",
        assumptions=("research is bounded",),
        decision_targets=("slot-1",),
        tracks=({"id": "track-1"},),
        method_hypotheses=({"method": "repository"},),
        depth="deep",
        evidence_expectations=("source",),
        autonomy_envelope={"allowed": ["research"]},
        replanning_policy={"same_round": ["depth"]},
        success_oracles=("oracle-1",),
        delivery_contract={"technical": "package", "human": "report"},
        stop_rule="oracle passes",
        preference_influences=(),
        revision=1,
        status="displayed",
    )
    coordinator.persist_strategy_projection(projection, expected_revision=ledger.get_revision("run-portfolio"))
    coordinator.display_strategy("run-portfolio", projection, expected_revision=ledger.get_revision("run-portfolio"))
    coordinator.confirm_handoff(
        "run-portfolio",
        projection_ref=ArtifactRef("run-portfolio", projection.id, projection.revision),
        confirmation=f"I accept {projection.display_digest} and authorize research.",
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    strategy = ledger.get_artifact(ArtifactRef("run-portfolio", projection.id, projection.revision))
    portfolio = SearchPortfolioService(ledger).plan(
        run_id="run-portfolio",
        portfolio_id="portfolio-valid",
        intent_model=intent,
        working_brief=brief,
        strategy=strategy,
        decision_map=target,
        slot={"slot_id": "slot-1", "question": "Which source confirms the mechanism?", "closure_oracle": "oracle-1"},
        authority_envelope="confirmed research",
        available_methods=(_method(),),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    before = ledger.get_revision("run-portfolio")
    with pytest.raises(CoordinatorConflictError, match="search_portfolio_required"):
        coordinator.dispatch(
            run_id="run-portfolio",
            work_item={
                "work_item_id": "acquire-1",
                "objective": "Acquire primary implementation evidence.",
                "success_oracle": "oracle-1",
                "acquisition": True,
            },
            worker_id="worker-1",
            expected_revision=before,
        )
    forged = _append(ledger, "run-portfolio", "portfolio-forged", "search-portfolio", {"status": "active"})
    with pytest.raises(CoordinatorConflictError, match="search_portfolio_invalid"):
        coordinator.dispatch(
            run_id="run-portfolio",
            work_item={
                "work_item_id": "forged-acquire",
                "objective": "Acquire primary implementation evidence.",
                "success_oracle": "oracle-1",
                "acquisition": True,
                "decision_slot_id": "slot-1",
                "query_id": portfolio.payload["query_variants"][0]["query_id"],
                "method_id": "repo-inspect",
                "search_portfolio_ref": ArtifactRef("run-portfolio", forged.id, forged.revision).to_dict(),
            },
            worker_id="worker-1",
            expected_revision=ledger.get_revision("run-portfolio"),
        )
    lease = coordinator.dispatch(
        run_id="run-portfolio",
        work_item={
            "work_item_id": "acquire-1",
            "objective": "Acquire primary implementation evidence.",
            "success_oracle": "oracle-1",
            "acquisition": True,
            "decision_slot_id": "slot-1",
            "query_id": portfolio.payload["query_variants"][0]["query_id"],
            "method_id": "repo-inspect",
            "search_portfolio_ref": ArtifactRef("run-portfolio", portfolio.id, portfolio.revision).to_dict(),
        },
        worker_id="worker-1",
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    assert ArtifactRef("run-portfolio", portfolio.id, portfolio.revision) in lease.parent_refs

    with pytest.raises(CoordinatorConflictError, match="search_portfolio_invalid"):
        coordinator.dispatch(
            run_id="run-portfolio",
            work_item={
                "work_item_id": "acquire-without-slot",
                "objective": "Acquire primary implementation evidence.",
                "success_oracle": "oracle-1",
                "acquisition": True,
                "query_id": portfolio.payload["query_variants"][0]["query_id"],
                "method_id": "repo-inspect",
                "search_portfolio_ref": ArtifactRef("run-portfolio", portfolio.id, portfolio.revision).to_dict(),
            },
            worker_id="worker-1",
            expected_revision=ledger.get_revision("run-portfolio"),
        )


def test_acquisition_dispatch_rejects_portfolio_bound_to_other_strategy_or_slot(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection = _confirm_strategy(ledger, coordinator)
    foreign = _append(
        ledger,
        "run-57",
        "portfolio-foreign",
        "search-portfolio",
        {
            "decision_slot_id": "slot-other",
            "status": "active",
            "lineage": {
                "strategy_ref": ArtifactRef("run-57", projection.id, projection.revision).to_dict(),
                "decision_map_ref": projection.target_ref.to_dict(),
            },
        },
    )

    with pytest.raises(CoordinatorConflictError, match="search_portfolio_invalid"):
        coordinator.dispatch(
            run_id="run-57",
            work_item={
                "work_item_id": "acquire-foreign",
                "objective": "Acquire primary implementation evidence.",
                "success_oracle": "oracle-1",
                "acquisition": True,
                "decision_slot_id": "slot-1",
                "search_portfolio_ref": ArtifactRef("run-57", foreign.id, foreign.revision).to_dict(),
            },
            worker_id="worker-1",
            expected_revision=ledger.get_revision("run-57"),
        )


def test_acquisition_worker_finished_requires_persisted_batch_assessment(tmp_path) -> None:
    ledger, coordinator, portfolio = _portfolio_dispatch_setup(tmp_path)
    lease = coordinator.dispatch(
        run_id="run-portfolio",
        work_item={
            "work_item_id": "acquire-finish",
            "objective": "Acquire primary implementation evidence.",
            "success_oracle": "oracle-1",
            "acquisition": True,
            "decision_slot_id": "slot-1",
            "query_id": portfolio.payload["query_variants"][0]["query_id"],
            "method_id": "repo-inspect",
            "search_portfolio_ref": ArtifactRef("run-portfolio", portfolio.id, portfolio.revision).to_dict(),
        },
        worker_id="worker-1",
        expected_revision=ledger.get_revision("run-portfolio"),
        attempt_id="attempt-portfolio-finish",
    )
    _append(
        ledger,
        "run-portfolio",
        "assessment-forged",
        "batch-coverage-assessment",
        {"assessment": {"attempt_id": lease.id}},
        (ArtifactRef("run-portfolio", portfolio.id, portfolio.revision),),
    )
    event = HostEvent.from_value(
        {
            "event_id": "worker-finished-portfolio",
            "kind": "worker_finished",
            "run_id": "run-portfolio",
            "attempt_id": lease.id,
            "expected_revision": ledger.get_revision("run-portfolio"),
            "sequence": 1,
            "actor": "codex",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"outcome": {"status": "finished"}},
        }
    )

    with pytest.raises(CoordinatorConflictError, match="search_portfolio_assessment_required"):
        coordinator.ingest_host_event(event)


def test_acquisition_worker_finished_rejects_unbound_capture(tmp_path) -> None:
    ledger, coordinator, portfolio = _portfolio_dispatch_setup(tmp_path)
    portfolio_ref = ArtifactRef("run-portfolio", portfolio.id, portfolio.revision)
    lease = coordinator.dispatch(
        run_id="run-portfolio",
        work_item={
            "work_item_id": "acquire-finish-forged",
            "objective": "Acquire primary implementation evidence.",
            "success_oracle": "oracle-1",
            "acquisition": True,
            "decision_slot_id": "slot-1",
            "query_id": portfolio.payload["query_variants"][0]["query_id"],
            "method_id": "repo-inspect",
            "search_portfolio_ref": portfolio_ref.to_dict(),
        },
        worker_id="worker-1",
        expected_revision=ledger.get_revision("run-portfolio"),
        attempt_id="attempt-portfolio-forged",
    )
    capture = _append(
        ledger,
        "run-portfolio",
        "capture-finish-forged",
        "source-capture",
        {
            "schema_version": 1,
            "capture_id": "capture-finish-forged",
            "run_id": "run-portfolio",
            "attempt_id": lease.id,
            "locator": {"cas": "sha256:forged"},
            "content_digest": "a" * 64,
            "media_type": "text/plain",
            "size_bytes": 1,
            "captured_at": "2026-08-12T00:00:00+00:00",
            "method_id": "repo-inspect",
            "provider_id": "git",
            "provenance_group": "repository:workspace",
            "status": "committed",
            "selector": {},
            "license_note": None,
            "access_note": None,
            "parser_version": "unparsed",
            "origin_capture_id": None,
        },
    )
    receipt = _append(
        ledger,
        "run-portfolio",
        "receipt-finish-forged",
        "acquisition-receipt",
        {
            "schema_version": 1,
            "receipt_id": "receipt-finish-forged",
            "capture_id": capture.id,
            "attempt_id": lease.id,
            "method_id": "repo-inspect",
            "provider_id": "git",
            "requested_at": "2026-08-12T00:00:00+00:00",
            "completed_at": "2026-08-12T00:00:01+00:00",
            "status": "succeeded",
            "failure_history": [],
            "selector": {},
        },
        (ArtifactRef("run-portfolio", capture.id, capture.revision),),
    )
    checkpoint = _append(
        ledger,
        "run-portfolio",
        "checkpoint-finish-forged",
        "analysis-checkpoint",
        {
            "schema_version": 1,
            "checkpoint_id": "checkpoint-finish-forged",
            "run_id": "run-portfolio",
            "attempt_id": lease.id,
            "action_id": "assess-finish-forged",
            "scope": "bounded analysis",
            "source_capture_refs": [ArtifactRef("run-portfolio", capture.id, capture.revision).to_dict()],
            "facts": [],
            "hypotheses": [],
            "contradictions": [],
            "open_questions": [],
            "method_outcomes": [],
            "next_actions": [],
            "created_at": "2026-08-12T00:00:02+00:00",
        },
        (ArtifactRef("run-portfolio", capture.id, capture.revision),),
    )
    forged_assessment = assess_acquisition_batch(
        assessment_id="assessment-finish-forged",
        portfolio_id=portfolio.id,
        decision_slot_id="slot-1",
        attempt_id=lease.id,
        batch_id="batch-finish-forged",
        coverage="complete",
        novelty="new",
        source_depth="full_source",
        provenance_independence="independent",
        contradictions=(),
        implementation_uncertainty="low",
        oracle_readiness="ready",
        unresolved_decision_risk="bounded",
        causal_refs=("capture-finish-forged@1", "receipt-finish-forged@1", "checkpoint-finish-forged@1"),
        capture_refs=("capture-finish-forged@1",),
        receipt_refs=("receipt-finish-forged@1",),
        checkpoint_refs=("checkpoint-finish-forged@1",),
    )
    recorded = _append(
        ledger,
        "run-portfolio",
        "assessment-finish-forged",
        "batch-coverage-assessment",
        {
            "schema_version": 1,
            "kind": "batch-coverage-assessment",
            "run_id": "run-portfolio",
            "portfolio_ref": portfolio_ref.to_dict(),
            "assessment": forged_assessment.to_dict(),
            "status": "recorded",
        },
        (
            portfolio_ref,
            ArtifactRef("run-portfolio", capture.id, capture.revision),
            ArtifactRef("run-portfolio", receipt.id, receipt.revision),
            ArtifactRef("run-portfolio", checkpoint.id, checkpoint.revision),
        ),
    )
    event = HostEvent.from_value(
        {
            "event_id": "worker-finished-portfolio-forged",
            "kind": "worker_finished",
            "run_id": "run-portfolio",
            "attempt_id": lease.id,
            "expected_revision": ledger.get_revision("run-portfolio"),
            "sequence": 1,
            "actor": "codex",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "outcome": {"assessment_ref": ArtifactRef("run-portfolio", recorded.id, recorded.revision).to_dict()}
            },
        }
    )

    with pytest.raises(CoordinatorConflictError, match="search_portfolio_assessment_required"):
        coordinator.ingest_host_event(event)


def test_acquisition_worker_finished_accepts_real_batch_assessment(tmp_path) -> None:
    ledger, coordinator, portfolio = _portfolio_dispatch_setup(tmp_path)
    portfolio_ref = ArtifactRef("run-portfolio", portfolio.id, portfolio.revision)
    lease = coordinator.dispatch(
        run_id="run-portfolio",
        work_item={
            "work_item_id": "acquire-finish-valid",
            "objective": "Acquire primary implementation evidence.",
            "success_oracle": "oracle-1",
            "acquisition": True,
            "decision_slot_id": "slot-1",
            "query_id": portfolio.payload["query_variants"][0]["query_id"],
            "method_id": "repo-inspect",
            "search_portfolio_ref": portfolio_ref.to_dict(),
        },
        worker_id="worker-1",
        expected_revision=ledger.get_revision("run-portfolio"),
        attempt_id="attempt-portfolio-valid",
    )
    capture_service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    capture = capture_service.capture(
        run_id="run-portfolio",
        capture_id="capture-finish-valid",
        attempt_id=lease.id,
        data=b"primary implementation evidence",
        media_type="text/plain",
        method_id="repo-inspect",
        provider_id="git",
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    receipt = capture_service.receipt(
        run_id="run-portfolio",
        receipt_id="receipt-finish-valid",
        capture=capture,
        attempt_id=lease.id,
        method_id="repo-inspect",
        provider_id="git",
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    checkpoint = capture_service.checkpoint(
        run_id="run-portfolio",
        checkpoint_id="checkpoint-finish-valid",
        attempt_id=lease.id,
        action_id="assess-finish-valid",
        source_capture_refs=(capture.artifact_ref,),
        facts=({"claim": "capture is committed"},),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    recorded = SearchPortfolioService(ledger).record_assessment(
        run_id="run-portfolio",
        assessment=assess_acquisition_batch(
            assessment_id="assessment-finish-valid",
            portfolio_id=portfolio.id,
            decision_slot_id="slot-1",
            attempt_id=lease.id,
            batch_id="batch-finish-valid",
            coverage="complete",
            novelty="new",
            source_depth="full_source",
            provenance_independence="independent",
            contradictions=(),
            implementation_uncertainty="low",
            oracle_readiness="ready",
            unresolved_decision_risk="bounded",
            causal_refs=("capture-finish-valid@1", "receipt-finish-valid@1", "checkpoint-finish-valid@1"),
            capture_refs=("capture-finish-valid@1",),
            receipt_refs=("receipt-finish-valid@1",),
            checkpoint_refs=("checkpoint-finish-valid@1",),
        ),
        portfolio_ref=portfolio_ref,
        capture_artifacts=(ledger.get_artifact(capture.artifact_ref),),
        receipt_artifacts=(ledger.get_artifact(receipt.artifact_ref),),
        checkpoint_artifacts=(ledger.get_artifact(checkpoint.artifact_ref),),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    missing_ref_event = HostEvent.from_value(
        {
            "event_id": "worker-finished-portfolio-missing-ref",
            "kind": "worker_finished",
            "run_id": "run-portfolio",
            "attempt_id": lease.id,
            "expected_revision": ledger.get_revision("run-portfolio"),
            "sequence": 1,
            "actor": "codex",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"outcome": {"status": "finished"}},
        }
    )
    with pytest.raises(CoordinatorConflictError, match="search_portfolio_assessment_required"):
        coordinator.ingest_host_event(missing_ref_event)
    event = HostEvent.from_value(
        {
            "event_id": "worker-finished-portfolio-valid",
            "kind": "worker_finished",
            "run_id": "run-portfolio",
            "attempt_id": lease.id,
            "expected_revision": ledger.get_revision("run-portfolio"),
            "sequence": 1,
            "actor": "codex",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "outcome": {"assessment_ref": ArtifactRef("run-portfolio", recorded.id, recorded.revision).to_dict()}
            },
        }
    )

    observed = coordinator.ingest_host_event(event)

    assert observed.id == "worker-finished-portfolio-valid"


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
