"""Issue #471 attack regressions: structural independence + post-confirm invalidation.

Red-first recipes reproduced by the v2 blind verifier (gate 3 residual):

1. Same-execution rename: an alignment verification / delivery review whose two
   identity strings merely differ (both self-declared by the coordinator) used
   to pass the #462 gates. After #471 the gate requires the review
   registration's durable ledger principal (issuer) to be the write-time
   binding of the declared identity pair, and a review whose principal is the
   coordinator's own principal fails closed.
2. Post-confirm revise: ``revise_strategy`` used to write a broad displayed
   projection into the durable ledger after confirmation with no invalidation
   marker. After #471 a post-confirm revision is written as a draft, the prior
   confirmed projection is explicitly invalidated by a supersession marker
   artifact, and the new revision must pass the full independent display gate
   again before anything displayed is authoritative.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from strategy_support import confirm_strategy
from test_independent_review import (
    MAIN_SESSION,
    RUN,
    SUBAGENT_IDENTITY,
    _alignment_payload,
    _custody_refs,
    _delivery_payload,
    _finding_pack,
    _initialize,
    _prepare_completed_ready,
    _projection_for_run,
)

from research_tree.coordinator import CoordinatorConflictError, ResearchRunCoordinator
from research_tree.domain import ArtifactRef
from research_tree.independent_review import INDEPENDENT_REVIEW_ISSUER
from research_tree.run_ledger import RunLedger
from research_tree.strategy_projection import StrategyProjection, latest_confirmed

INVALIDATION_KIND = "strategy-projection-invalidation"


# ---------------------------------------------------------------------------
# Attack helpers (write review registrations straight to the ledger)
# ---------------------------------------------------------------------------


def _write_raw_alignment_verification(
    ledger: RunLedger,
    projection_artifact,
    *,
    issuer: str,
    verifier: str = SUBAGENT_IDENTITY,
    session: str = MAIN_SESSION,
):
    """Append an alignment verification with an attacker-chosen ledger principal."""

    payload = _alignment_payload(projection_artifact, verifier=verifier, session=session)
    return ledger.append_completion_input(
        RUN,
        str(payload["id"]),
        "alignment_verification",
        "alignment-verification",
        payload,
        parent_refs=(ArtifactRef(RUN, projection_artifact.id, projection_artifact.revision),),
        issuer=issuer,
        issuer_evidence={"source": "issue-471-attack"},
        expected_revision=ledger.get_revision(RUN),
    )


def _confirmed_run(tmp_path: Path) -> tuple[RunLedger, ResearchRunCoordinator, StrategyProjection]:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-471")
    handoff = ledger.append_artifact(
        "run-471",
        "handoff-1",
        "alignment-handoff",
        {"confirmed": True},
        parent_refs=(),
        expected_revision=ledger.get_revision("run-471"),
    )
    target = ledger.append_artifact(
        "run-471",
        "target-1",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1"}]},
        parent_refs=(ArtifactRef("run-471", handoff.id, handoff.revision),),
        expected_revision=ledger.get_revision("run-471"),
    )
    coordinator = ResearchRunCoordinator(ledger)
    coordinator.initialize(
        run_id="run-471",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-471"),
    )
    return ledger, coordinator, confirm_strategy(ledger, coordinator, "run-471")


def _displayed_variant(artifact) -> StrategyProjection:
    """Rebuild a persisted projection revision as displayed (same content)."""

    draft = StrategyProjection.from_dict(dict(artifact.payload))
    return StrategyProjection.create(
        projection_id=draft.projection_id,
        run_id=draft.run_id,
        decision_frame_ref=draft.decision_frame_ref,
        alignment_handoff_ref=draft.alignment_handoff_ref,
        target_ref=draft.target_ref,
        current_understanding=draft.current_understanding,
        assumptions=draft.assumptions,
        decision_targets=draft.decision_targets,
        tracks=draft.tracks,
        method_hypotheses=draft.method_hypotheses,
        depth=draft.depth,
        evidence_expectations=draft.evidence_expectations,
        autonomy_envelope=draft.autonomy_envelope,
        replanning_policy=draft.replanning_policy,
        success_oracles=draft.success_oracles,
        delivery_contract=draft.delivery_contract,
        stop_rule=draft.stop_rule,
        preference_influences=draft.preference_influences,
        revision=draft.revision,
        status="displayed",
    )


# ---------------------------------------------------------------------------
# Attack 1: same-session different-name rename (v2 recipe, alignment gate)
# ---------------------------------------------------------------------------


def test_rename_attack_with_legacy_unbound_principal_fails_display_gate(tmp_path: Path) -> None:
    """The exact v2 rename: two differing names, legacy constant issuer, passes today."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    _write_raw_alignment_verification(ledger, projection_artifact, issuer=INDEPENDENT_REVIEW_ISSUER)

    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.display_strategy(RUN, projection_artifact, expected_revision=ledger.get_revision(RUN))


def test_coordinator_principal_self_issued_verification_fails_display_gate(tmp_path: Path) -> None:
    """A verification issued under the coordinator's own ledger principal is self-review."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    _write_raw_alignment_verification(ledger, projection_artifact, issuer="coordinator")

    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.display_strategy(RUN, projection_artifact, expected_revision=ledger.get_revision(RUN))


def test_verify_identity_independent_requires_write_time_principal_binding() -> None:
    """The identity rule binds the declared pair to the durable principal at the gate."""

    from research_tree.independent_review import verification_principal

    principal = verification_principal(SUBAGENT_IDENTITY, MAIN_SESSION)
    assert principal != INDEPENDENT_REVIEW_ISSUER
    # Honest bound pair passes; the legacy unbound constant and the coordinator
    # principal never do; a renamed verifier cannot ride another pair's principal.
    assert verify_bound(SUBAGENT_IDENTITY, MAIN_SESSION, principal) is True
    assert verify_bound(SUBAGENT_IDENTITY, MAIN_SESSION, INDEPENDENT_REVIEW_ISSUER) is False
    assert verify_bound(SUBAGENT_IDENTITY, MAIN_SESSION, "coordinator") is False
    assert verify_bound("agent-renamed", MAIN_SESSION, principal) is False
    # The coordinator principal can never be an independent verifier identity.
    assert verify_bound("coordinator", MAIN_SESSION, principal) is False
    assert verify_bound(MAIN_SESSION, "coordinator", principal) is False
    # Legacy two-argument #462 call sites keep their honest-path behavior.
    assert verify_bound(SUBAGENT_IDENTITY, MAIN_SESSION, None) is True
    assert verify_bound(MAIN_SESSION, MAIN_SESSION, None) is False


def verify_bound(verifier: str, session: str, issuer: str | None) -> bool:
    from research_tree.independent_review import verify_identity_independent

    if issuer is None:
        return verify_identity_independent(verifier, session)
    return verify_identity_independent(verifier, session, issuer=issuer)


def test_registrar_binds_review_principal_at_write_time(tmp_path: Path) -> None:
    """Honest #462 flows keep passing: the registrar writes the bound principal."""

    from research_tree.independent_review import verification_principal

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    from test_independent_review import _write_alignment_verification

    _write_alignment_verification(ledger, projection_artifact)
    principals = ledger.completion_input_registration_principals(RUN)
    assert principals[ArtifactRef(RUN, "alignment-verification-1", 1)] == verification_principal(
        SUBAGENT_IDENTITY, MAIN_SESSION
    )
    coordinator.display_strategy(RUN, projection_artifact, expected_revision=ledger.get_revision(RUN))


# ---------------------------------------------------------------------------
# Attack 2: rename at the delivery gate
# ---------------------------------------------------------------------------


def _attack_delivery_review(ledger: RunLedger, *, issuer: str) -> None:
    custody = _custody_refs(_finding_pack(ledger, "pack-independent-1"))
    payload = _delivery_payload(custody=custody)
    ledger.append_completion_input(
        RUN,
        str(payload["id"]),
        "delivery_review",
        "delivery-review",
        payload,
        parent_refs=custody,
        issuer=issuer,
        issuer_evidence={"source": "issue-471-attack"},
        expected_revision=ledger.get_revision(RUN),
    )


@pytest.mark.parametrize("issuer", [INDEPENDENT_REVIEW_ISSUER, "coordinator"])
def test_delivery_review_unbound_or_coordinator_principal_fails_gate(tmp_path: Path, issuer: str) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare_completed_ready(ledger, coordinator, review=False)
    _attack_delivery_review(ledger, issuer=issuer)

    why = coordinator.why_not_complete(RUN)
    assert why["field_diagnostics"]["independent_delivery_review"]["reason"] == "verifier_not_independent"
    from research_tree.coordinator import CompletionBlockedError

    with pytest.raises(CompletionBlockedError, match="independent_delivery_review"):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


# ---------------------------------------------------------------------------
# Attack 4: post-confirm revise_strategy writes an unauthorized displayed projection
# ---------------------------------------------------------------------------


def test_post_confirm_revise_invalidates_confirmation_and_regates(tmp_path: Path) -> None:
    ledger, coordinator, projection = _confirmed_run(tmp_path)
    confirmed_ref = ArtifactRef("run-471", projection.id, projection.revision)
    before_markers = [item for item in ledger.load_run("run-471").artifacts if item.kind == INVALIDATION_KIND]
    assert before_markers == []

    revised = coordinator.revise_strategy(
        "run-471",
        projection_ref=confirmed_ref,
        changes={"autonomy_envelope": {"allowed": ["research", "implementation"], "authority": "broad"}},
        expected_revision=ledger.get_revision("run-471"),
    )

    # The broad revision must NOT enter the ledger displayed.
    assert revised.payload["status"] == "draft"
    # The prior confirmed projection must be explicitly invalidated by a marker.
    markers = [item for item in ledger.load_run("run-471").artifacts if item.kind == INVALIDATION_KIND]
    assert len(markers) == 1
    marker = markers[0]
    assert ArtifactRef.from_dict(marker.payload["superseded_projection_ref"]) == confirmed_ref
    assert marker.payload["superseded_display_digest"] == projection.display_digest
    assert len(marker.payload["superseded_authority_fingerprint"]) == 64
    assert confirmed_ref in revised.parent_refs
    # The confirmation is void: no authoritative confirmed projection remains.
    assert latest_confirmed(ledger.load_run("run-471").artifacts) is None
    # The new revision cannot ride the old verification: the display gate fails closed.
    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.require_independent_alignment_verification("run-471", _displayed_variant(revised))
