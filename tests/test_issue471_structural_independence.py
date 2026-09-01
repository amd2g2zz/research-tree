"""Issue #471 attack regressions: structural independence + post-confirm invalidation.

Attack recipes reproduced by the v2 blind verifier plus reviewer A/B findings
(gate 3 residual):

1. Same-execution rename: an alignment verification / delivery review whose two
   identity strings merely differ (both self-declared by the coordinator) used
   to pass the #462 gates. After #471 the gate requires the review
   registration's durable ledger principal (issuer) to be the write-time HMAC
   binding — keyed with the ledger's secret per-run salt — of the declared
   identity pair; unbound, coordinator, or self-minted principals fail closed,
   and the two-argument #462 predicate is compatibility-only.
2. Post-confirm revise: ``revise_strategy`` used to write a broad displayed
   projection into the durable ledger after confirmation with no invalidation
   marker. After #471 every revision of a once-confirmed projection id is
   written as a draft behind a supersession marker (draft-first ordering), and
   the superseding draft can reach re-confirmation only through the full #462
   display gate via the re-alignment edge.
"""

from __future__ import annotations

import hashlib
import re
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

from research_tree.completion_inputs import CompletionInputRegistrar
from research_tree.coordinator import CompletionBlockedError, CoordinatorConflictError, ResearchRunCoordinator
from research_tree.domain import ArtifactRef, canonical_json_bytes
from research_tree.independent_review import (
    INDEPENDENT_REVIEW_ISSUER,
    verification_principal,
    verify_identity_independent,
    verify_independent_review_principal,
)
from research_tree.run_ledger import RunLedger
from research_tree.strategy_projection import StrategyProjection, authority_fingerprint, latest_confirmed

INVALIDATION_KIND = "strategy-projection-invalidation"


def _legacy_public_mint(verifier: str, session: str) -> str:
    """The pre-#471 public-material principal: bare SHA-256 of the identity pair."""

    material = {
        "issuer": INDEPENDENT_REVIEW_ISSUER,
        "session_context": session,
        "verifier_identity": verifier,
    }
    return f"{INDEPENDENT_REVIEW_ISSUER}@{hashlib.sha256(canonical_json_bytes(material)).hexdigest()}"


# ---------------------------------------------------------------------------
# Attack helpers
# ---------------------------------------------------------------------------


def _write_raw_alignment_verification(
    ledger: RunLedger,
    projection_artifact,
    *,
    artifact_id: str = "alignment-verification-1",
    issuer: str,
    verifier: str = SUBAGENT_IDENTITY,
    session: str = MAIN_SESSION,
):
    """Append an alignment verification with an attacker-chosen ledger principal."""

    payload = _alignment_payload(projection_artifact, verifier=verifier, session=session)
    payload["id"] = artifact_id
    return ledger.append_completion_input(
        RUN,
        artifact_id,
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


def _redisplayed(artifact, *, revision: int | None = None) -> StrategyProjection:
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
        revision=draft.revision if revision is None else revision,
        status="displayed",
    )


# ---------------------------------------------------------------------------
# Attack 1: same-session different-name rename (v2 recipe, alignment gate)
# ---------------------------------------------------------------------------


def test_rename_attack_with_legacy_unbound_principal_fails_display_gate(tmp_path: Path) -> None:
    """The exact v2 rename: two differing names, legacy constant issuer, passed before."""

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


# ---------------------------------------------------------------------------
# Attack 2: minting — public material must not yield a passing principal
# ---------------------------------------------------------------------------


def test_self_minted_principals_cannot_satisfy_display_gate(tmp_path: Path) -> None:
    """Bare public-material minting (old scheme) and foreign-salt HMAC both fail."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    attempts = [
        _legacy_public_mint(SUBAGENT_IDENTITY, MAIN_SESSION),
        verification_principal("attacker-forged-salt", SUBAGENT_IDENTITY, MAIN_SESSION),
    ]
    for index, issuer in enumerate(attempts, start=1):
        _write_raw_alignment_verification(
            ledger,
            projection_artifact,
            artifact_id=f"alignment-verification-{index}",
            issuer=issuer,
        )

    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.display_strategy(RUN, projection_artifact, expected_revision=ledger.get_revision(RUN))
    run_principal = ledger.verification_principal(RUN, SUBAGENT_IDENTITY, MAIN_SESSION)
    assert run_principal not in attempts
    assert run_principal != _legacy_public_mint(SUBAGENT_IDENTITY, MAIN_SESSION)


def test_verify_identity_predicates_contract() -> None:
    """Compat two-arg path keeps #462; production predicate requires the principal."""

    principal = verification_principal("run-salt-1", SUBAGENT_IDENTITY, MAIN_SESSION)
    # Salted HMAC: different salts bind different principals; public material
    # alone cannot produce the run's principal.
    assert verification_principal("salt-b", SUBAGENT_IDENTITY, MAIN_SESSION) != principal
    assert principal != _legacy_public_mint(SUBAGENT_IDENTITY, MAIN_SESSION)
    # Production predicate: issuer and principal are required keywords, and a
    # gate lookup miss (issuer=None) fails closed instead of open.
    assert verify_independent_review_principal(SUBAGENT_IDENTITY, MAIN_SESSION, issuer=principal, principal=principal)
    assert not verify_independent_review_principal(SUBAGENT_IDENTITY, MAIN_SESSION, issuer=None, principal=principal)
    assert not verify_independent_review_principal(SUBAGENT_IDENTITY, MAIN_SESSION, issuer=principal, principal="x")
    # Gate scenario for a renamed pair: the durable issuer stays bound to the
    # original pair while the gate recomputes the principal from the payload's
    # (renamed) pair — the mismatch must fail.
    renamed_principal = verification_principal("run-salt-1", "agent-renamed", MAIN_SESSION)
    assert not verify_independent_review_principal(
        "agent-renamed", MAIN_SESSION, issuer=principal, principal=renamed_principal
    )
    assert not verify_independent_review_principal("coordinator", MAIN_SESSION, issuer=principal, principal=principal)
    with pytest.raises(TypeError):
        verify_independent_review_principal(SUBAGENT_IDENTITY, MAIN_SESSION, issuer=principal)  # type: ignore[call-arg]
    import inspect

    signature = inspect.signature(verify_independent_review_principal)
    assert signature.parameters["issuer"].default is inspect.Parameter.empty
    assert signature.parameters["principal"].default is inspect.Parameter.empty
    # The two-argument #462 compatibility path keeps its honest behavior and
    # its name for existing callers, but is not the production predicate.
    assert verify_identity_independent(SUBAGENT_IDENTITY, MAIN_SESSION) is True
    assert verify_identity_independent(MAIN_SESSION, MAIN_SESSION) is False
    assert verify_identity_independent("coordinator", MAIN_SESSION) is False


def test_every_src_call_site_passes_issuer() -> None:
    """MEDIUM: src never calls the compat predicate; production calls pass issuer."""

    src_dir = Path(__file__).resolve().parents[1] / "src" / "research_tree"
    compat_call = re.compile(r"verify_identity_independent\s*\(")
    production_call = re.compile(r"verify_independent_review_principal\s*\(")
    offenders: list[str] = []
    production_call_sites = 0
    for path in sorted(src_dir.glob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            window = "\n".join(lines[index : index + 8])
            if compat_call.search(line) and not line.strip().startswith("def "):
                offenders.append(f"{path.name}:{index + 1}: compat predicate called in src")
            if production_call.search(line) and not line.strip().startswith("def "):
                production_call_sites += 1
                if "issuer=" not in window:
                    offenders.append(f"{path.name}:{index + 1}: production call missing issuer=")
    assert offenders == []
    assert production_call_sites >= 2, "both coordinator gates must use the production predicate"


def test_registrar_binds_review_principal_at_write_time(tmp_path: Path) -> None:
    """Honest #462 flows keep passing: the registrar writes the salted principal."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    projection_artifact = _projection_for_run(ledger, coordinator)
    from test_independent_review import _write_alignment_verification

    _write_alignment_verification(ledger, projection_artifact)
    principals = ledger.completion_input_registration_principals(RUN)
    recorded = principals[ArtifactRef(RUN, "alignment-verification-1", 1)]
    assert recorded == ledger.verification_principal(RUN, SUBAGENT_IDENTITY, MAIN_SESSION)
    assert recorded != _legacy_public_mint(SUBAGENT_IDENTITY, MAIN_SESSION)
    coordinator.display_strategy(RUN, projection_artifact, expected_revision=ledger.get_revision(RUN))


# ---------------------------------------------------------------------------
# Attack 3: rename at the delivery gate
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


@pytest.mark.parametrize(
    "issuer",
    [
        INDEPENDENT_REVIEW_ISSUER,
        "coordinator",
        _legacy_public_mint(SUBAGENT_IDENTITY, MAIN_SESSION),
    ],
)
def test_delivery_review_unbound_or_coordinator_principal_fails_gate(tmp_path: Path, issuer: str) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare_completed_ready(ledger, coordinator, review=False)
    _attack_delivery_review(ledger, issuer=issuer)

    why = coordinator.why_not_complete(RUN)
    assert why["field_diagnostics"]["independent_delivery_review"]["reason"] == "verifier_not_independent"
    with pytest.raises(CompletionBlockedError, match="independent_delivery_review"):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


# ---------------------------------------------------------------------------
# Attack 4: post-confirm revise with broad authority (the v2 write attack)
# ---------------------------------------------------------------------------


def test_post_confirm_revise_invalidates_confirmation_and_regates(tmp_path: Path) -> None:
    ledger, coordinator, projection = _confirmed_run(tmp_path)
    confirmed_ref = ArtifactRef("run-471", projection.id, projection.revision)
    before = [item for item in ledger.load_run("run-471").artifacts if item.kind == INVALIDATION_KIND]
    assert before == []

    revised = coordinator.revise_strategy(
        "run-471",
        projection_ref=confirmed_ref,
        changes={"autonomy_envelope": {"allowed": ["research", "implementation"], "authority": "broad"}},
        expected_revision=ledger.get_revision("run-471"),
    )

    # The broad revision must NOT enter the ledger displayed.
    assert revised.payload["status"] == "draft"
    # The superseded revision is explicitly invalidated by a marker.
    markers = [item for item in ledger.load_run("run-471").artifacts if item.kind == INVALIDATION_KIND]
    assert len(markers) == 1
    assert ArtifactRef.from_dict(markers[0].payload["superseded_projection_ref"]) == confirmed_ref
    assert markers[0].payload["superseded_display_digest"] == projection.display_digest
    assert len(markers[0].payload["superseded_authority_fingerprint"]) == 64
    # The confirmation is void: no authoritative confirmed projection remains.
    assert latest_confirmed(ledger.load_run("run-471").artifacts) is None
    # The new revision cannot ride the old verification: the display gate fails closed.
    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.require_independent_alignment_verification("run-471", _redisplayed(revised))


# ---------------------------------------------------------------------------
# Attack 5: second post-confirm revise falls back to the displayed branch
# ---------------------------------------------------------------------------


def test_second_post_confirm_revise_stays_draft_with_second_marker(tmp_path: Path) -> None:
    """Review A/B HIGH-1: revise #2 must not fall back to the legacy displayed branch.

    After revise #1 supersedes the confirmation, ``latest_confirmed`` is
    permanently None — post-confirm semantics derive from the projection id's
    confirmation history, so revise #2 also stays a draft with its own marker.
    """

    ledger, coordinator, projection = _confirmed_run(tmp_path)
    first = coordinator.revise_strategy(
        "run-471",
        projection_ref=ArtifactRef("run-471", projection.id, projection.revision),
        changes={"autonomy_envelope": {"allowed": ["research"], "authority": "narrow-1"}},
        expected_revision=ledger.get_revision("run-471"),
    )
    assert first.payload["status"] == "draft"

    second = coordinator.revise_strategy(
        "run-471",
        projection_ref=ArtifactRef("run-471", first.id, first.revision),
        changes={"autonomy_envelope": {"allowed": ["research", "implementation"], "authority": "broad-2"}},
        expected_revision=ledger.get_revision("run-471"),
    )

    assert second.payload["status"] == "draft"
    assert second.payload["revision"] == first.payload["revision"] + 1
    markers = [item for item in ledger.load_run("run-471").artifacts if item.kind == INVALIDATION_KIND]
    assert len(markers) == 2
    assert ArtifactRef.from_dict(markers[1].payload["superseded_projection_ref"]) == ArtifactRef(
        "run-471", first.id, first.revision
    )
    assert latest_confirmed(ledger.load_run("run-471").artifacts) is None
    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.require_independent_alignment_verification("run-471", _redisplayed(second))


# ---------------------------------------------------------------------------
# Review B: the superseding draft can reach re-confirmation through the gate
# ---------------------------------------------------------------------------


def test_superseding_draft_reaches_reconfirmation_via_alignment_feedback(tmp_path: Path) -> None:
    ledger, coordinator, projection = _confirmed_run(tmp_path)
    revised = coordinator.revise_strategy(
        "run-471",
        projection_ref=ArtifactRef("run-471", projection.id, projection.revision),
        changes={"autonomy_envelope": {"allowed": ["research", "review"], "authority": "fixed"}},
        expected_revision=ledger.get_revision("run-471"),
    )
    assert revised.payload["status"] == "draft"

    # The human returns the run to alignment over the superseding revision.
    coordinator.transition("run-471", "alignment_feedback", "human", expected_revision=ledger.get_revision("run-471"))
    assert coordinator.state("run-471").payload["state"] == "alignment"

    # Without a fresh verification the draft still cannot display.
    draft = StrategyProjection.from_dict(dict(revised.payload))
    with pytest.raises(CoordinatorConflictError, match="independent_verification_required"):
        coordinator.require_independent_alignment_verification("run-471", draft)

    # A fresh independent verification (new artifact id: registrations are
    # append-once per id) bound to the draft's authority content, written
    # through the registrar so its durable principal is the salted binding.
    oracle_ids = [str(oracle["id"]) for oracle in draft.success_oracles]
    CompletionInputRegistrar(ledger).write_alignment_verification(
        round_id="run-471",
        verification_id="alignment-verification-2",
        payload={
            "schema": 1,
            "id": "alignment-verification-2",
            "round_id": "run-471",
            "projection_ref": {"round_id": "run-471", "artifact_id": draft.projection_id, "revision": draft.revision},
            "authority_fingerprint": authority_fingerprint(draft),
            "verifier_identity": SUBAGENT_IDENTITY,
            "session_context": "run-471-main",
            "understood": {
                "outcome": "Independently restated: validate the requester decision.",
                "scope": "Independently restated: research and review only.",
                "authority": "Independently restated: autonomous research within the fixed envelope.",
                "success_oracles": [
                    {"id": oracle_id, "understanding": f"Independently restated oracle {oracle_id}."}
                    for oracle_id in oracle_ids
                ],
            },
            "discrepancies": [],
        },
        expected_revision=ledger.get_revision("run-471"),
    )

    # Promote the draft to a displayed revision (the CLI promote flow bumps the
    # payload revision in lockstep with the appended artifact revision).
    variant = _redisplayed(revised, revision=draft.revision + 1)
    ledger.append_strategy_projection(
        "run-471",
        variant.projection_id,
        variant.to_dict(),
        parent_refs=(
            ArtifactRef("run-471", revised.id, revised.revision),
            variant.decision_frame_ref,
            variant.alignment_handoff_ref,
            variant.target_ref,
        ),
        expected_revision=ledger.get_revision("run-471"),
    )
    coordinator.display_strategy("run-471", variant, expected_revision=ledger.get_revision("run-471"))
    coordinator.confirm_handoff(
        "run-471",
        projection_ref=ArtifactRef("run-471", variant.projection_id, variant.revision),
        confirmation=(
            f"I accept the displayed strategy {variant.display_digest} authority-fingerprint "
            f"{authority_fingerprint(variant)} and authorize research within it."
        ),
        expected_revision=ledger.get_revision("run-471"),
    )
    assert coordinator.state("run-471").payload["state"] == "autonomous_research"
    reconfirmed = latest_confirmed(ledger.load_run("run-471").artifacts)
    assert reconfirmed is not None
    assert (reconfirmed.id, reconfirmed.revision) == (variant.projection_id, variant.revision)
