"""Independent subagent review gates (#462, #292 gate 3) named contract tests.

The alignment display gate and the delivery acceptance gate require a review
artifact produced by a distinct execution identity (a fresh subagent session),
never by the main agent session that drafted the work it reviews:

- ``alignment-verification`` (display gate): an independent restatement of
  outcome, scope, authority, and every success oracle, bound to the projection
  content by the authority fingerprint.
- ``delivery-review`` (delivery gate): per-oracle independent verdicts with
  evidence custody over run artifacts and an overall verdict.

Both gates run in conjunction with the #441 falsifiability review and the
#443 goal_satisfaction diagnostic — they never replace them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_goal_wiring import projection
from test_research_run_coordinator import (
    _initialize,
    _ready_frame,
    _register_canonical_completion_inputs,
)

from research_tree.completion_inputs import CompletionInputError, CompletionInputRegistrar
from research_tree.coordinator import (
    COMPLETION_RECORD_KIND,
    CompletionBlockedError,
    CoordinatorConflictError,
    IllegalTransitionError,
)
from research_tree.domain import ArtifactRef, ArtifactRevision
from research_tree.independent_review import (
    ALIGNMENT_VERIFICATION_KIND,
    DELIVERY_REVIEW_KIND,
    IndependentReviewError,
    validate_alignment_verification_payload,
    validate_delivery_review_payload,
    verify_identity_independent,
)
from research_tree.strategy_projection import authority_fingerprint

RUN = "run-57"
MAIN_SESSION = "session-main"
SUBAGENT_IDENTITY = "agent-verifier-1"
ORACLE_1 = {"id": "oracle-1", "evidence_standard_ids": ("standard-1",)}
ORACLE_2 = {"id": "oracle-2", "evidence_standard_ids": ("standard-2",)}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _finding_pack(ledger, artifact_id: str = "pack-independent-1"):
    return ledger.append_artifact(
        RUN,
        artifact_id,
        "finding-pack",
        {"id": artifact_id, "round_id": RUN},
        expected_revision=ledger.get_revision(RUN),
    )


def _projection_for_run(ledger, coordinator, success_oracles=(ORACLE_1,)):
    """Persist a falsifiable displayed projection for run-57 and return it."""

    artifacts = ledger.load_run(RUN).artifacts
    handoff = next(item for item in artifacts if item.kind == "alignment-handoff")
    target = next(item for item in artifacts if item.kind == "blueprint-target")
    target_ref = ArtifactRef(RUN, target.id, target.revision)
    frame = coordinator.persist_decision_frame(
        _ready_frame(frame_id="strategy-frame", target_ref=target_ref),
        expected_revision=ledger.get_revision(RUN),
    )
    goal_projection = projection(
        RUN,
        frame_ref=ArtifactRef(RUN, frame.id, frame.revision),
        handoff_ref=ArtifactRef(RUN, handoff.id, handoff.revision),
        target_ref=target_ref,
        decision_targets=({"id": "decision-1", "oracle_ids": tuple(o["id"] for o in success_oracles)},),
        success_oracles=success_oracles,
        status="displayed",
    )
    coordinator.persist_strategy_projection(goal_projection, expected_revision=ledger.get_revision(RUN))
    return goal_projection


def _alignment_payload(
    projection_artifact,
    *,
    verifier: str = SUBAGENT_IDENTITY,
    session: str = MAIN_SESSION,
    oracle_ids: tuple[str, ...] = ("oracle-1",),
) -> dict:
    return {
        "schema": 1,
        "id": "alignment-verification-1",
        "round_id": RUN,
        "projection_ref": {
            "round_id": RUN,
            "artifact_id": projection_artifact.id,
            "revision": projection_artifact.revision,
        },
        "authority_fingerprint": authority_fingerprint(projection_artifact),
        "verifier_identity": verifier,
        "session_context": session,
        "understood": {
            "outcome": "Independently restated outcome: validate the requester decision.",
            "scope": "Independently restated scope: research only, no implementation.",
            "authority": "Independently restated authority: autonomous research within the envelope.",
            "success_oracles": [
                {"id": oracle_id, "understanding": f"Independently restated oracle {oracle_id}."}
                for oracle_id in oracle_ids
            ],
        },
        "discrepancies": [],
    }


def _write_alignment_verification(
    ledger,
    projection_artifact,
    *,
    artifact_id: str = "alignment-verification-1",
    **payload_kwargs,
):
    registrar = CompletionInputRegistrar(ledger)
    return registrar.write_alignment_verification(
        round_id=RUN,
        verification_id=artifact_id,
        payload=_alignment_payload(projection_artifact, **payload_kwargs),
        expected_revision=ledger.get_revision(RUN),
    )


def _inject_alignment_verification(ledger, projection_artifact, payload: dict):
    """Append an alignment-verification straight to the ledger (bypass vector)."""

    return ledger.append_completion_input(
        RUN,
        str(payload["id"]),
        "alignment_verification",
        ALIGNMENT_VERIFICATION_KIND,
        payload,
        parent_refs=(
            ArtifactRef(
                RUN,
                payload["projection_ref"]["artifact_id"],
                payload["projection_ref"]["revision"],
            ),
        ),
        issuer="bypass-writer",
        issuer_evidence={"source": "bypass"},
        expected_revision=ledger.get_revision(RUN),
    )


def _custody_refs(*packs) -> tuple[ArtifactRef, ...]:
    """Artifact references for finding-pack fixture artifacts (or plain refs)."""

    refs = tuple(
        ArtifactRef(item.round_id, item.id, item.revision) if isinstance(item, ArtifactRevision) else item
        for item in packs
    )
    if any(ref.round_id != RUN for ref in refs):
        raise AssertionError("custody refs must belong to the fixture run")
    return refs


def _delivery_payload(
    *,
    artifact_id: str = "delivery-review-1",
    verifier: str = SUBAGENT_IDENTITY,
    session: str = MAIN_SESSION,
    per_oracle: dict | None = None,
    custody: tuple[ArtifactRef, ...] = (),
    verdict: str = "satisfied",
) -> dict:
    if per_oracle is None:
        per_oracle = {"oracle-1": {"verdict": "satisfied", "basis": "Finding pack evidence covers the oracle."}}
    return {
        "schema": 1,
        "id": artifact_id,
        "round_id": RUN,
        "verifier_identity": verifier,
        "session_context": session,
        "per_oracle": per_oracle,
        "evidence_custody": [ref.to_dict() for ref in custody],
        "verdict": verdict,
    }


def _write_delivery_review(
    ledger,
    custody: tuple[ArtifactRef, ...],
    *,
    artifact_id: str = "delivery-review-1",
    **payload_kwargs,
):
    registrar = CompletionInputRegistrar(ledger)
    return registrar.write_delivery_review(
        round_id=RUN,
        review_id=artifact_id,
        payload=_delivery_payload(artifact_id=artifact_id, custody=custody, **payload_kwargs),
        expected_revision=ledger.get_revision(RUN),
    )


def _satisfy_goal(ledger, oracle_id: str = "oracle-1") -> None:
    pack = _finding_pack(ledger, f"pack-goal-{oracle_id}")
    CompletionInputRegistrar(ledger).write_goal_satisfaction(
        round_id=RUN,
        registration_id=f"goal-{oracle_id}",
        oracle_id=oracle_id,
        verdict="satisfied",
        evidence_refs=(ArtifactRef(RUN, pack.id, pack.revision),),
        expected_revision=ledger.get_revision(RUN),
    )


def _advance(ledger, coordinator) -> None:
    for event in ("batch_checkpoint", "all_slots_closed", "readiness_passed", "deliveries_compiled"):
        coordinator.transition(RUN, event, "coordinator", expected_revision=ledger.get_revision(RUN))


def _target(ledger):
    artifacts = ledger.load_run(RUN).artifacts
    return next(item for item in artifacts if item.kind == "blueprint-target")


def _prepare_completed_ready(
    ledger, coordinator, *, success_oracles=(ORACLE_1,), review: bool = True, satisfy: bool = True
) -> None:
    """Drive run-57 to awaiting_acceptance with every completion piece but the review.

    The goal_satisfaction diagnostic (#443) and the alignment verification (#462)
    are in place by default, so the only optional pieces are the delivery review
    itself and the goal satisfaction verdicts. Every gate must stay conjunctive:
    the review gate fails on its own reason only, and the other gates still block
    independently.
    """

    projection_artifact = _projection_for_run(ledger, coordinator, success_oracles=success_oracles)
    _write_alignment_verification(
        ledger,
        projection_artifact,
        oracle_ids=tuple(oracle["id"] for oracle in success_oracles),
    )
    coordinator.display_strategy(RUN, projection_artifact, expected_revision=ledger.get_revision(RUN))
    coordinator.confirm_handoff(
        RUN,
        projection_ref=ArtifactRef(RUN, projection_artifact.id, projection_artifact.revision),
        confirmation=(
            f"I accept {projection_artifact.display_digest} "
            f"authority-fingerprint {authority_fingerprint(projection_artifact)} and authorize research."
        ),
        expected_revision=ledger.get_revision(RUN),
    )
    _register_canonical_completion_inputs(ledger, RUN, _target(ledger), review=review)
    if satisfy:
        for oracle in success_oracles:
            _satisfy_goal(ledger, oracle["id"])
    _advance(ledger, coordinator)


# ---------------------------------------------------------------------------
# Payload validators and the identity rule
# ---------------------------------------------------------------------------


def test_identity_rule_rejects_same_session_and_requires_both_identities() -> None:
    assert verify_identity_independent(SUBAGENT_IDENTITY, MAIN_SESSION) is True
    assert verify_identity_independent(MAIN_SESSION, MAIN_SESSION) is False
    assert verify_identity_independent("", MAIN_SESSION) is False
    assert verify_identity_independent(SUBAGENT_IDENTITY, "") is False
    assert verify_identity_independent("   ", MAIN_SESSION) is False


def test_alignment_payload_validator_enforces_exact_schema() -> None:
    payload = {
        "schema": 1,
        "id": "alignment-verification-1",
        "round_id": RUN,
        "projection_ref": {"round_id": RUN, "artifact_id": "strategy-projection", "revision": 1},
        "authority_fingerprint": "a" * 64,
        "verifier_identity": SUBAGENT_IDENTITY,
        "session_context": MAIN_SESSION,
        "understood": {
            "outcome": "restated",
            "scope": "restated",
            "authority": "restated",
            "success_oracles": [{"id": "oracle-1", "understanding": "restated"}],
        },
        "discrepancies": [],
    }
    parsed = validate_alignment_verification_payload(payload)
    assert parsed["verifier_identity"] == SUBAGENT_IDENTITY

    with pytest.raises(IndependentReviewError, match="fields do not match"):
        validate_alignment_verification_payload({**payload, "extra": 1})
    with pytest.raises(IndependentReviewError, match="schema"):
        validate_alignment_verification_payload({**payload, "schema": 2})
    with pytest.raises(IndependentReviewError, match="verifier_identity"):
        validate_alignment_verification_payload({**payload, "verifier_identity": "  "})
    with pytest.raises(IndependentReviewError, match="understood"):
        validate_alignment_verification_payload({**payload, "understood": {"outcome": "only"}})
    with pytest.raises(IndependentReviewError, match="discrepancies"):
        validate_alignment_verification_payload({**payload, "discrepancies": ["ok", 7]})


def test_delivery_payload_validator_enforces_exact_schema() -> None:
    payload = _delivery_payload(
        custody=(ArtifactRef(RUN, "pack-independent-1", 1),),
        per_oracle={"oracle-1": {"verdict": "partial", "basis": "thin but present"}},
        verdict="partial",
    )
    parsed = validate_delivery_review_payload(payload)
    assert parsed["verdict"] == "partial"

    with pytest.raises(IndependentReviewError, match="fields do not match"):
        validate_delivery_review_payload({**payload, "extra": 1})
    with pytest.raises(IndependentReviewError, match="verdict"):
        validate_delivery_review_payload({**payload, "verdict": "waived"})
    with pytest.raises(IndependentReviewError, match="per_oracle"):
        validate_delivery_review_payload({**payload, "per_oracle": {"oracle-1": "satisfied"}})
    with pytest.raises(IndependentReviewError, match="basis"):
        validate_delivery_review_payload({**payload, "per_oracle": {"oracle-1": {"verdict": "unmet", "basis": "  "}}})
    with pytest.raises(IndependentReviewError, match="evidence_custody"):
        validate_delivery_review_payload({**payload, "evidence_custody": []})
    with pytest.raises(IndependentReviewError, match="verifier_identity"):
        validate_delivery_review_payload({**payload, "verifier_identity": None})


# ---------------------------------------------------------------------------
# Alignment display gate
# ---------------------------------------------------------------------------


def test_display_rejects_missing_alignment_verification(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    state_before = coordinator.state(RUN)
    revision_before = ledger.get_revision(RUN)

    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.display_strategy(RUN, projection_artifact, expected_revision=revision_before)

    assert coordinator.state(RUN) == state_before
    assert ledger.get_revision(RUN) == revision_before
    assert not any(item.kind == "lifecycle-event" for item in ledger.load_run(RUN).artifacts)


def test_display_rejects_same_identity_self_review(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    _inject_alignment_verification(
        ledger,
        projection_artifact,
        _alignment_payload(projection_artifact, verifier=MAIN_SESSION, session=MAIN_SESSION),
    )
    state_before = coordinator.state(RUN)

    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.display_strategy(RUN, projection_artifact, expected_revision=ledger.get_revision(RUN))

    assert coordinator.state(RUN) == state_before


def test_display_rejects_verification_without_identity(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    _inject_alignment_verification(
        ledger,
        projection_artifact,
        _alignment_payload(projection_artifact, verifier="   "),
    )

    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.display_strategy(RUN, projection_artifact, expected_revision=ledger.get_revision(RUN))


def test_display_rejects_verification_of_different_content(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    stale_payload = _alignment_payload(projection_artifact)
    stale_payload["authority_fingerprint"] = "b" * 64
    _inject_alignment_verification(ledger, projection_artifact, stale_payload)

    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.display_strategy(RUN, projection_artifact, expected_revision=ledger.get_revision(RUN))


def test_display_accepts_independent_verification(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    verification = _write_alignment_verification(ledger, projection_artifact)

    assert verification.kind == ALIGNMENT_VERIFICATION_KIND
    coordinator.display_strategy(RUN, projection_artifact, expected_revision=ledger.get_revision(RUN))

    assert coordinator.state(RUN).payload["state"] == "handoff_pending"
    artifact = next(item for item in ledger.load_run(RUN).artifacts if item.id == "alignment-verification-1")
    assert ArtifactRef(RUN, projection_artifact.id, projection_artifact.revision) in artifact.parent_refs


def test_display_conjunction_falsifiability_fail_with_verification_present(tmp_path: Path) -> None:
    """The #441 falsifiability gate still blocks when an independent verification exists."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    _write_alignment_verification(ledger, projection_artifact)
    unfalsifiable = projection(
        RUN,
        frame_ref=projection_artifact.decision_frame_ref,
        handoff_ref=projection_artifact.alignment_handoff_ref,
        target_ref=projection_artifact.target_ref,
        decision_targets=({"id": "decision-1", "oracle_ids": ("oracle-1",)},),
        success_oracles=("oracle-1",),
        status="displayed",
        projection_id="projection-unfalsifiable",
    )
    coordinator.persist_strategy_projection(unfalsifiable, expected_revision=ledger.get_revision(RUN))
    state_before = coordinator.state(RUN)

    with pytest.raises(CoordinatorConflictError, match="evidence_standard_ids"):
        coordinator.display_strategy(RUN, unfalsifiable, expected_revision=ledger.get_revision(RUN))

    assert coordinator.state(RUN) == state_before


def test_direct_transition_requires_independent_verification(tmp_path: Path) -> None:
    """The gate holds for every caller of alignment_projection_ready."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    state_before = coordinator.state(RUN)

    with pytest.raises(IllegalTransitionError, match="independent_verification_required"):
        coordinator.transition(
            RUN,
            "alignment_projection_ready",
            "coordinator",
            expected_revision=ledger.get_revision(RUN),
            payload={
                "projection_ref": ArtifactRef(RUN, projection_artifact.id, projection_artifact.revision).to_dict(),
                "display_digest": projection_artifact.display_digest,
            },
        )

    assert coordinator.state(RUN) == state_before
    rejections = [item for item in ledger.load_run(RUN).artifacts if item.kind == "lifecycle-rejection"]
    assert len(rejections) == 1
    assert rejections[0].payload["reason"] == "independent_verification_required"


# ---------------------------------------------------------------------------
# Delivery gate
# ---------------------------------------------------------------------------


def test_delivery_rejects_missing_delivery_review(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare_completed_ready(ledger, coordinator, review=False)
    why = coordinator.why_not_complete(RUN)

    assert why["field_diagnostics"]["independent_delivery_review"]["reason"] == "independent_review_required"
    assert "independent_delivery_review" in why["unmet_obligations"]
    assert "resolve:independent_delivery_review" in why["next_actions"]

    with pytest.raises(CompletionBlockedError, match="independent_delivery_review"):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


def test_delivery_rejects_same_identity_review(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare_completed_ready(ledger, coordinator, review=False)
    custody = _custody_refs(_finding_pack(ledger, "pack-independent-1"))
    ledger.append_completion_input(
        RUN,
        "delivery-review-1",
        "delivery_review",
        DELIVERY_REVIEW_KIND,
        _delivery_payload(verifier=MAIN_SESSION, session=MAIN_SESSION, custody=custody),
        parent_refs=custody,
        issuer="bypass-writer",
        issuer_evidence={"source": "bypass"},
        expected_revision=ledger.get_revision(RUN),
    )

    why = coordinator.why_not_complete(RUN)
    assert why["field_diagnostics"]["independent_delivery_review"]["reason"] == "verifier_not_independent"

    with pytest.raises(CompletionBlockedError, match="independent_delivery_review"):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


def test_delivery_rejects_incomplete_oracle_coverage(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare_completed_ready(ledger, coordinator, success_oracles=(ORACLE_1, ORACLE_2), review=False)
    custody = _custody_refs(_finding_pack(ledger, "pack-independent-1"))
    _write_delivery_review(
        ledger,
        custody,
        artifact_id="delivery-review-1",
        per_oracle={"oracle-1": {"verdict": "satisfied", "basis": "covered"}},
    )

    why = coordinator.why_not_complete(RUN)
    detail = why["field_diagnostics"]["independent_delivery_review"]
    assert detail["reason"] == "oracle_uncovered"
    assert detail["oracles"] == ["oracle-2"]
    assert "resolve:independent_delivery_review:oracle-2" in why["next_actions"]

    with pytest.raises(CompletionBlockedError, match="independent_delivery_review"):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


def test_delivery_rejects_unmet_independent_verdict(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare_completed_ready(ledger, coordinator, review=False)
    custody = _custody_refs(_finding_pack(ledger, "pack-independent-1"))
    _write_delivery_review(
        ledger,
        custody,
        per_oracle={"oracle-1": {"verdict": "unmet", "basis": "Evidence does not cover the oracle."}},
        verdict="unmet",
    )

    why = coordinator.why_not_complete(RUN)
    assert why["field_diagnostics"]["independent_delivery_review"]["reason"] == "independent_review_unmet"

    with pytest.raises(CompletionBlockedError, match="independent_delivery_review"):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


def test_delivery_rejects_stale_evidence_custody(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare_completed_ready(ledger, coordinator)
    ledger.append_artifact(
        RUN,
        "pack-delivery-review",
        "finding-pack",
        {"id": "pack-delivery-review", "round_id": RUN, "replacement": True},
        expected_revision=ledger.get_revision(RUN),
    )

    why = coordinator.why_not_complete(RUN)
    assert why["field_diagnostics"]["independent_delivery_review"]["reason"] == "evidence_custody_stale"

    with pytest.raises(CompletionBlockedError, match="independent_delivery_review"):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


def test_delivery_accepts_independent_review_and_records_refs(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare_completed_ready(ledger, coordinator)

    completed = coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))

    assert completed.payload["state"] == "completed"
    record = next(item for item in ledger.load_run(RUN).artifacts if item.kind == COMPLETION_RECORD_KIND)
    refs = record.payload["manifold"]["independent_review_refs"]
    assert [ArtifactRef.from_dict(dict(ref)) for ref in refs] == [ArtifactRef(RUN, "delivery-review-1", 1)]
    assert coordinator.why_not_complete(RUN)["unmet_obligations"] == ()


def test_delivery_conjunction_goal_failure_with_review_present(tmp_path: Path) -> None:
    """The #443 goal_satisfaction gate still blocks when an independent review exists."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare_completed_ready(ledger, coordinator, review=False, satisfy=False)
    custody = _custody_refs(_finding_pack(ledger, "pack-independent-1"))
    _write_delivery_review(ledger, custody)
    CompletionInputRegistrar(ledger).write_goal_satisfaction(
        round_id=RUN,
        registration_id="goal-oracle-1",
        oracle_id="oracle-1",
        verdict="unmet",
        expected_revision=ledger.get_revision(RUN),
    )

    why = coordinator.why_not_complete(RUN)
    assert why["field_diagnostics"]["independent_delivery_review"]["status"] == "pass"
    assert "goal_satisfaction" in why["unmet_obligations"]

    with pytest.raises(CompletionBlockedError, match="goal_satisfaction"):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


# ---------------------------------------------------------------------------
# Registrar lineage and identity binding
# ---------------------------------------------------------------------------


def test_registrar_binds_review_lineage_and_rejects_identity_mismatch(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    registrar = CompletionInputRegistrar(ledger)

    verification = registrar.write_alignment_verification(
        round_id=RUN,
        verification_id="alignment-verification-1",
        payload=_alignment_payload(projection_artifact),
        expected_revision=ledger.get_revision(RUN),
    )
    assert verification.kind == ALIGNMENT_VERIFICATION_KIND
    assert ArtifactRef(RUN, projection_artifact.id, projection_artifact.revision) in verification.parent_refs

    with pytest.raises(CompletionInputError, match="id"):
        registrar.write_alignment_verification(
            round_id=RUN,
            verification_id="alignment-verification-2",
            payload=_alignment_payload(projection_artifact),
            expected_revision=ledger.get_revision(RUN),
        )

    custody = _custody_refs(_finding_pack(ledger, "pack-independent-1"))
    with pytest.raises(CompletionInputError, match="round_id"):
        registrar.write_delivery_review(
            round_id=RUN,
            review_id="delivery-review-1",
            payload={**_delivery_payload(custody=custody), "round_id": "run-other"},
            expected_revision=ledger.get_revision(RUN),
        )


def test_delivery_review_lineage_binds_finding_pack_custody(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _projection_for_run(ledger, coordinator)
    custody = _custody_refs(_finding_pack(ledger, "pack-independent-1"))

    review = _write_delivery_review(ledger, custody)

    assert review.kind == DELIVERY_REVIEW_KIND
    assert tuple(review.parent_refs) == custody
