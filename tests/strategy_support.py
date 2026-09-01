from __future__ import annotations

from research_tree.coordinator import ResearchRunCoordinator
from research_tree.decision_frame import DecisionFrame, IntentHypothesis
from research_tree.domain import ArtifactRef
from research_tree.run_ledger import RunLedger
from research_tree.strategy_projection import StrategyProjection, authority_fingerprint


def prepare_strategy(ledger: RunLedger, coordinator: ResearchRunCoordinator, run_id: str) -> StrategyProjection:
    artifacts = ledger.load_run(run_id).artifacts
    handoff = next(item for item in artifacts if item.kind == "alignment-handoff")
    target = next(item for item in artifacts if item.kind == "blueprint-target")
    target_ref = ArtifactRef(run_id, target.id, target.revision)
    frame = DecisionFrame.create(
        frame_id="strategy-frame",
        run_id=run_id,
        requester_wording="Choose the customer decision to validate.",
        primary_decision={"id": "decision-1", "statement": "Choose the customer decision", "success_signal": "signal"},
        target_ref=target_ref,
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
    frame_artifact = coordinator.persist_decision_frame(frame, expected_revision=ledger.get_revision(run_id))
    projection = StrategyProjection.create(
        projection_id="strategy-projection",
        run_id=run_id,
        decision_frame_ref=ArtifactRef(run_id, frame_artifact.id, frame_artifact.revision),
        alignment_handoff_ref=ArtifactRef(run_id, handoff.id, handoff.revision),
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
    coordinator.persist_strategy_projection(projection, expected_revision=ledger.get_revision(run_id))
    return projection


def confirm_strategy(ledger: RunLedger, coordinator: ResearchRunCoordinator, run_id: str) -> StrategyProjection:
    projection = prepare_strategy(ledger, coordinator, run_id)
    coordinator.display_strategy(run_id, projection, expected_revision=ledger.get_revision(run_id))
    coordinator.confirm_handoff(
        run_id,
        projection_ref=ArtifactRef(run_id, projection.id, projection.revision),
        confirmation=f"I accept {projection.display_digest} authority-fingerprint {authority_fingerprint(projection)} and authorize research.",
        expected_revision=ledger.get_revision(run_id),
    )
    return projection
