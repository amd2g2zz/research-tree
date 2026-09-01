from __future__ import annotations

from research_tree.completion_inputs import CompletionInputRegistrar
from research_tree.coordinator import ResearchRunCoordinator
from research_tree.decision_frame import DecisionFrame, IntentHypothesis
from research_tree.domain import ArtifactRef
from research_tree.run_ledger import RunLedger
from research_tree.strategy_projection import StrategyProjection, authority_fingerprint, latest_confirmed

MAIN_SESSION = "session-main"
SUBAGENT_IDENTITY = "agent-verifier-support"


def _projection_oracle_ids(projection: StrategyProjection) -> list[str]:
    oracle_ids: list[str] = []
    for oracle in projection.display_payload.get("success_oracles") or ():
        if isinstance(oracle, dict) and str(oracle.get("id", "")).strip():
            oracle_id = str(oracle["id"])
        elif isinstance(oracle, str) and oracle.strip():
            oracle_id = oracle
        else:
            continue
        if oracle_id not in oracle_ids:
            oracle_ids.append(oracle_id)
    assert oracle_ids, "fixture projection carries no usable success oracles"
    return oracle_ids


def write_alignment_verification(ledger: RunLedger, projection: StrategyProjection, run_id: str) -> None:
    """Register the independent subagent alignment verification a display requires (#462)."""

    oracle_ids = _projection_oracle_ids(projection)
    CompletionInputRegistrar(ledger).write_alignment_verification(
        round_id=run_id,
        verification_id="alignment-verification-1",
        payload={
            "schema": 1,
            "id": "alignment-verification-1",
            "round_id": run_id,
            "projection_ref": {
                "round_id": run_id,
                "artifact_id": projection.projection_id,
                "revision": projection.revision,
            },
            "authority_fingerprint": authority_fingerprint(projection),
            "verifier_identity": SUBAGENT_IDENTITY,
            "session_context": MAIN_SESSION,
            "understood": {
                "outcome": "Independently restated: validate the requester decision.",
                "scope": "Independently restated: research only.",
                "authority": "Independently restated: autonomous research within the envelope.",
                "success_oracles": [
                    {"id": oracle_id, "understanding": f"Independently restated oracle {oracle_id}."}
                    for oracle_id in oracle_ids
                ],
            },
            "discrepancies": [],
        },
        expected_revision=ledger.get_revision(run_id),
    )


def write_independent_delivery_review(ledger: RunLedger, run_id: str) -> None:
    """Register the independent delivery review a delivery acceptance requires (#462)."""

    snapshot = ledger.load_run(run_id)
    projection = latest_confirmed(snapshot.artifacts)
    assert projection is not None, f"fixture run {run_id} has no confirmed projection"
    oracle_ids = _projection_oracle_ids(StrategyProjection.from_dict(projection.payload))
    pack = ledger.append_artifact(
        run_id,
        "pack-delivery-review",
        "finding-pack",
        {"id": "pack-delivery-review", "round_id": run_id},
        expected_revision=ledger.get_revision(run_id),
    )
    custody = ArtifactRef(run_id, pack.id, pack.revision)
    CompletionInputRegistrar(ledger).write_delivery_review(
        round_id=run_id,
        review_id="delivery-review-1",
        payload={
            "schema": 1,
            "id": "delivery-review-1",
            "round_id": run_id,
            "verifier_identity": SUBAGENT_IDENTITY,
            "session_context": MAIN_SESSION,
            "per_oracle": {
                oracle_id: {"verdict": "satisfied", "basis": "Pack evidence covers the oracle."}
                for oracle_id in oracle_ids
            },
            "evidence_custody": [custody.to_dict()],
            "verdict": "satisfied",
        },
        expected_revision=ledger.get_revision(run_id),
    )


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
    write_alignment_verification(ledger, projection, run_id)
    coordinator.display_strategy(run_id, projection, expected_revision=ledger.get_revision(run_id))
    coordinator.confirm_handoff(
        run_id,
        projection_ref=ArtifactRef(run_id, projection.id, projection.revision),
        confirmation=f"I accept {projection.display_digest} authority-fingerprint {authority_fingerprint(projection)} and authorize research.",
        expected_revision=ledger.get_revision(run_id),
    )
    return projection
