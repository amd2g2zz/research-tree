"""Dispute governance — make disagreement evidence-governed and pressure-resistant.

Issue #317 acceptance criteria:

* Pressure signals (repeat assertion, social pressure, evidence-quality change,
  assumption change, independent validation) are kept separate as influences
  on a dispute.
* Pressure from the requester does not corrupt technical truth nor devolve into
  unjustified agent stubbornness.
* A recorded DisputePacket records the disputed claim, requester position,
  agent position, evidence basis, pressure signals, independent-validation
  state, and a recommended verification path.
* Repeated low-quality pressure (no new evidence) does not flip the
  disposition; repeated high-quality counter-evidence does.
* Every disposition change is auditable: a recorded reason and the influences
  that flipped it.

Issue #424 merged the dispute module into ``research_tree.contradictions``;
this suite keeps every assertion and now imports from the merged module.
"""

from __future__ import annotations

from typing import Any

import pytest

from research_tree.contradictions import (
    DISPOSITION_PRECEDENCE,
    DISPUTE_PACKET_KIND,
    PROVIDER_VALIDATION_KIND,
    ContradictionPacket,
    ContradictionStatus,
    DisputeAuditTrail,
    DisputeDisposition,
    DisputeDispositionError,
    DisputePacket,
    PressureLedger,
    PressureSignal,
    append_signal,
    evaluate_dispute,
    record_audit,
    recorded_audit_trail,
)
from research_tree.coordinator import (
    CONTRADICTION_PACKET_KIND,
    RESEARCH_RUN_STATE_KIND,
    ResearchRunCoordinator,
)
from research_tree.run_ledger import RunLedger


def _contradiction_packet(
    *, claim_ids: tuple[str, str] = ("claim-a", "claim-b"), status: ContradictionStatus = ContradictionStatus.CONTESTED
) -> ContradictionPacket:
    return ContradictionPacket(
        claim_ids=claim_ids,
        status=status,
        reason="incompatible-applicable-claims",
        conflicting_values=("v-a", "v-b"),
    )


def _evidence_basis(*, quality: str = "low", basis_refs: tuple[str, ...] = ("ref-1",)) -> dict[str, Any]:
    return {"quality": quality, "basis_refs": list(basis_refs)}


# ---------------------------------------------------------------------------
# Acceptance criterion 1: pressure signals are separated from evidence
# ---------------------------------------------------------------------------


def test_pressure_signals_are_separated_from_evidence() -> None:
    packet = DisputePacket(
        dispute_id="dispute-1",
        disputed_claim_id="claim-a",
        requester_position="Requester says claim-a is wrong.",
        agent_position="Agent holds claim-a is supported by evidence.",
        evidence_basis=_evidence_basis(quality="high", basis_refs=("ref-1", "ref-2")),
        pressure_signals=(PressureSignal.REPEAT_ASSERTION,),
        independent_validation_state="none",
        recommended_verification_path=("request independent source",),
        audit_trail=DisputeAuditTrail(
            entries=(
                record_audit(
                    influences=(PressureSignal.REPEAT_ASSERTION,),
                    reason="pressure_without_new_evidence",
                ),
            )
        ),
    )

    # Pressure signals are tracked separately from evidence.
    assert packet.pressure_signals == (PressureSignal.REPEAT_ASSERTION,)
    assert packet.evidence_basis["quality"] == "high"
    assert packet.evidence_basis["basis_refs"] == ["ref-1", "ref-2"]
    # The five canonical influences exist and are distinct.
    assert len(PressureSignal) == 5
    assert {signal.value for signal in PressureSignal} == {
        "repeat_assertion",
        "social_pressure",
        "evidence_quality_change",
        "assumption_change",
        "independent_validation",
    }


def test_pressure_ledger_appends_signal_with_timestamp_and_source() -> None:
    ledger: PressureLedger = ()
    ledger = append_signal(
        ledger,
        signal=PressureSignal.REPEAT_ASSERTION,
        timestamp="2026-08-30T10:00:00+00:00",
        source="requester",
        quality="low",
    )
    ledger = append_signal(
        ledger,
        signal=PressureSignal.EVIDENCE_QUALITY_CHANGE,
        timestamp="2026-08-30T10:05:00+00:00",
        source="agent",
        quality="high",
    )

    assert len(ledger) == 2
    first, second = ledger
    assert first.signal is PressureSignal.REPEAT_ASSERTION
    assert first.quality == "low"
    assert first.source == "requester"
    assert second.signal is PressureSignal.EVIDENCE_QUALITY_CHANGE
    assert second.quality == "high"


# ---------------------------------------------------------------------------
# Acceptance criterion 2: low-quality pressure alone does not flip
# ---------------------------------------------------------------------------


def test_pressure_without_new_evidence_does_not_flip_disposition() -> None:
    basis = _evidence_basis(quality="high")
    # Initial disposition is agent_holds based on evidence.
    first = evaluate_dispute(
        claim_state={"supported_by": basis, "disputed": False},
        pressure_signals=(),
        evidence_updates=(),
        audit_trail=DisputeAuditTrail(entries=()),
    )
    assert first.disposition is DisputeDisposition.AGENT_HOLDS

    # A single repeat assertion without new evidence does not flip.
    second = evaluate_dispute(
        claim_state={"supported_by": basis, "disputed": False},
        pressure_signals=(PressureSignal.REPEAT_ASSERTION,),
        evidence_updates=(),
        audit_trail=DisputeAuditTrail(entries=()),
    )
    assert second.disposition is DisputeDisposition.AGENT_HOLDS


# ---------------------------------------------------------------------------
# Acceptance criterion 3: high-quality counter-evidence flips
# ---------------------------------------------------------------------------


def test_high_quality_counter_evidence_does_flip_disposition() -> None:
    basis = _evidence_basis(quality="high")
    # Reverse: high-quality counter-evidence transitions to requester_resolves.
    flipped = evaluate_dispute(
        claim_state={"supported_by": basis, "disputed": False},
        pressure_signals=(),
        evidence_updates=(
            {
                "kind": "counter_evidence",
                "quality": "high",
                "basis_refs": ["independent-source-A", "independent-source-B"],
            },
        ),
        audit_trail=DisputeAuditTrail(entries=()),
    )
    assert flipped.disposition is DisputeDisposition.REQUESTER_RESOLVES
    assert any("high_quality_counter_evidence" in entry.reason for entry in flipped.audit_trail.entries), (
        "the flip must record the influence that caused it"
    )


# ---------------------------------------------------------------------------
# Acceptance criterion 4: 10 repeats of low-quality pressure never flips
# ---------------------------------------------------------------------------


def test_audit_trail_completeness_for_repeat_low_quality_pressure() -> None:
    basis = _evidence_basis(quality="high")
    state = {"supported_by": basis, "disputed": False}
    audit_trail = DisputeAuditTrail(entries=())
    last_disposition = DisputeDisposition.AGENT_HOLDS
    for _ in range(10):
        result = evaluate_dispute(
            claim_state=state,
            pressure_signals=(PressureSignal.REPEAT_ASSERTION, PressureSignal.SOCIAL_PRESSURE),
            evidence_updates=(),
            audit_trail=audit_trail,
        )
        last_disposition = result.disposition
        audit_trail = result.audit_trail
    # 10 repeats of low-quality pressure never flip the agent_holds disposition.
    assert last_disposition is DisputeDisposition.AGENT_HOLDS
    # The audit trail grew with each evaluation, but no flip reason appears.
    assert len(audit_trail.entries) >= 10
    flip_reasons = [
        entry.reason for entry in audit_trail.entries if entry.disposition is not DisputeDisposition.AGENT_HOLDS
    ]
    assert list(flip_reasons) == []


# ---------------------------------------------------------------------------
# Acceptance criterion 5: precedence — independent validation beats pressure
# ---------------------------------------------------------------------------


def test_disposition_precedence_independent_validation_beats_pressure() -> None:
    basis = _evidence_basis(quality="high")
    # Independent validation:passed with simultaneous repeat_assertion.
    # Independent validation must beat pressure.
    result = evaluate_dispute(
        claim_state={"supported_by": basis, "disputed": False},
        pressure_signals=(PressureSignal.REPEAT_ASSERTION,),
        evidence_updates=(),
        audit_trail=DisputeAuditTrail(entries=()),
        independent_validation="passed",
    )
    assert result.independent_validation_state == "passed"
    assert result.disposition is DisputeDisposition.AGENT_HOLDS

    # Independent validation:failed with simultaneous repeat_assertion.
    # failed must beat pressure.
    failed = evaluate_dispute(
        claim_state={"supported_by": basis, "disputed": False},
        pressure_signals=(PressureSignal.REPEAT_ASSERTION, PressureSignal.SOCIAL_PRESSURE),
        evidence_updates=(),
        audit_trail=DisputeAuditTrail(entries=()),
        independent_validation="failed",
    )
    assert failed.disposition is DisputeDisposition.REQUESTER_RESOLVES
    assert any(PressureSignal.INDEPENDENT_VALIDATION in entry.influences for entry in failed.audit_trail.entries)

    # Inconclusive validation defers for explicit human review.
    inconclusive = evaluate_dispute(
        claim_state={"supported_by": basis, "disputed": False},
        pressure_signals=(PressureSignal.REPEAT_ASSERTION,),
        evidence_updates=(),
        audit_trail=DisputeAuditTrail(entries=()),
        independent_validation="inconclusive",
    )
    assert inconclusive.disposition is DisputeDisposition.DEFER


def test_evidence_quality_change_beats_social_pressure() -> None:
    """Precedence: evidence_quality_change > social_pressure."""

    basis = _evidence_basis(quality="low")
    result = evaluate_dispute(
        claim_state={"supported_by": basis, "disputed": False},
        pressure_signals=(PressureSignal.SOCIAL_PRESSURE,),
        evidence_updates=(),
        audit_trail=DisputeAuditTrail(entries=()),
        evidence_quality_change="high",
    )
    # High-quality evidence change (counter to low basis) overrides social pressure.
    assert result.disposition is DisputeDisposition.REQUESTER_RESOLVES


def test_disposition_precedence_table_is_documented() -> None:
    """Documented precedence: ind_validation > evidence_quality_change > assumption > social > repeat."""

    assert DISPOSITION_PRECEDENCE == (
        PressureSignal.INDEPENDENT_VALIDATION,
        PressureSignal.EVIDENCE_QUALITY_CHANGE,
        PressureSignal.ASSUMPTION_CHANGE,
        PressureSignal.SOCIAL_PRESSURE,
        PressureSignal.REPEAT_ASSERTION,
    )


# ---------------------------------------------------------------------------
# Acceptance criterion 6: every disposition change has a recorded reason
# ---------------------------------------------------------------------------


def test_dispute_packet_records_audit_trail() -> None:
    basis = _evidence_basis(quality="high")
    audit_trail = DisputeAuditTrail(entries=())
    # Force a flip via high-quality counter evidence.
    result = evaluate_dispute(
        claim_state={"supported_by": basis, "disputed": False},
        pressure_signals=(),
        evidence_updates=({"kind": "counter_evidence", "quality": "high", "basis_refs": ["src-x"]},),
        audit_trail=audit_trail,
    )
    # Every flip from agent_holds is recorded with a reason + influences.
    flip_entries = [
        entry for entry in result.audit_trail.entries if entry.disposition is not DisputeDisposition.AGENT_HOLDS
    ]
    assert flip_entries, "a flip must record an audit entry"
    flip = flip_entries[-1]
    assert flip.reason and flip.influences
    assert flip.timestamp  # an audit timestamp is required
    assert flip.previous_disposition is DisputeDisposition.AGENT_HOLDS


def test_auditable_per_disposition_change() -> None:
    """A sequence of flips accumulates one audit entry per flip."""

    basis_low = _evidence_basis(quality="low")
    audit_trail = DisputeAuditTrail(entries=())
    # Flip 1: high-quality counter evidence → requester_resolves
    result = evaluate_dispute(
        claim_state={"supported_by": basis_low, "disputed": False},
        pressure_signals=(),
        evidence_updates=({"kind": "counter_evidence", "quality": "high", "basis_refs": ["src-1"]},),
        audit_trail=audit_trail,
    )
    assert result.disposition is DisputeDisposition.REQUESTER_RESOLVES
    flip_count_1 = sum(
        1 for entry in result.audit_trail.entries if entry.disposition is DisputeDisposition.REQUESTER_RESOLVES
    )
    assert flip_count_1 == 1

    # Flip 2: independent validation fails → requester_resolves again (with new audit entry)
    result2 = evaluate_dispute(
        claim_state={"supported_by": basis_low, "disputed": False},
        pressure_signals=(),
        evidence_updates=(),
        audit_trail=result.audit_trail,
        independent_validation="failed",
    )
    flip_count_2 = sum(
        1 for entry in result2.audit_trail.entries if entry.disposition is DisputeDisposition.REQUESTER_RESOLVES
    )
    # Each new flip adds an audit entry; previously recorded flips remain.
    assert flip_count_2 >= flip_count_1 + 1


def test_disposition_error_for_unknown_state() -> None:
    """evaluate_dispute raises DisputeDispositionError on impossible state."""

    basis = _evidence_basis(quality="high")
    with pytest.raises(DisputeDispositionError):
        evaluate_dispute(
            claim_state={"supported_by": basis, "disputed": False},
            pressure_signals=(PressureSignal.INDEPENDENT_VALIDATION,),
            evidence_updates=(),
            audit_trail=DisputeAuditTrail(entries=()),
            independent_validation="not-a-real-state",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Acceptance criterion 7: coordinator wiring — pressure does not silently flip
# ---------------------------------------------------------------------------


def _coordinator(tmp_path) -> ResearchRunCoordinator:
    ledger = RunLedger(tmp_path / "ledger.db")
    ledger.create_run("run-317")
    coordinator = ResearchRunCoordinator(ledger, actor_id="coordinator-317")
    # Seed an initial run-state so coordinator ingestion has a valid baseline.
    coordinator.ledger.append_artifact(
        "run-317",
        "run-state-initial",
        RESEARCH_RUN_STATE_KIND,
        {
            "state": "alignment",
            "lifecycle_revision": 0,
            "unmet_obligations": [],
            "legal_next_actions": ["alignment_projection_ready", "authority_impossible", "supersede"],
            "macro_stage": 1,
            "state_digest": "x" * 64,
        },
        parent_refs=(),
        expected_revision=coordinator.ledger.get_revision("run-317"),
    )
    return coordinator


def _record_contradiction_packet(coordinator: ResearchRunCoordinator, *, contradiction_id: str) -> Any:
    """Insert a minimal contradiction packet to anchor a dispute."""

    payload = {
        "contradiction_id": contradiction_id,
        "run_id": "run-317",
        "claim_ids": ["claim-a", "claim-b"],
        "conflicting_values": ["v-a", "v-b"],
        "unresolved_dimensions": ["polarity"],
        "scope_dimensions": [],
        "normalized_claims": [],
        "boundary": "admission",
        "claim_a": {"claim_id": "claim-a"},
        "claim_b": {"claim_id": "claim-b"},
        "claim_a_ref": {"round_id": "run-317", "artifact_id": "fp-a", "revision": 1},
        "claim_b_ref": {"round_id": "run-317", "artifact_id": "fp-b", "revision": 1},
        "source_refs": {},
        "shared_scope": {},
        "conflict_reason": "incompatible-applicable-claims",
        "reason": "test fixture",
        "status": "contested",
        "resolution_path": "independent-experiment-or-scope-separation",
        "safe_fallback": "Retain the reversible fallback until resolution.",
        "invalidated_refs": [],
        "packet_digest": "x" * 64,
    }
    revision = coordinator.ledger.get_revision("run-317")
    return coordinator.ledger.append_artifact(
        "run-317",
        contradiction_id,
        CONTRADICTION_PACKET_KIND,
        payload,
        parent_refs=(),
        expected_revision=revision,
    )


def test_coordinator_pressure_signal_does_not_silently_flip_contradiction(tmp_path) -> None:
    """Appending a pressure signal to a contradiction packet does NOT mutate its status."""

    coordinator = _coordinator(tmp_path)
    _record_contradiction_packet(coordinator, contradiction_id="contradiction-x")
    packet = next(
        item
        for item in coordinator.ledger.load_run("run-317").artifacts
        if item.kind == CONTRADICTION_PACKET_KIND and item.id == "contradiction-x"
    )
    original_status = packet.payload.get("status")

    # Append a repeat-assertion pressure signal — packet status must not change.
    coordinator.ingest_pressure_signal(
        run_id="run-317",
        disputed_claim_id="claim-a",
        signal=PressureSignal.REPEAT_ASSERTION,
        source="requester",
        timestamp="2026-08-30T10:00:00+00:00",
        quality="low",
        contradiction_id="contradiction-x",
    )

    refreshed = next(
        item
        for item in coordinator.ledger.load_run("run-317").artifacts
        if item.kind == CONTRADICTION_PACKET_KIND and item.id == "contradiction-x"
    )
    assert refreshed.payload.get("status") == original_status
    # A pressure-ledger artifact was appended.
    ledger_artifacts = [
        item for item in coordinator.ledger.load_run("run-317").artifacts if item.kind == DISPUTE_PACKET_KIND
    ]
    assert ledger_artifacts, "expected a dispute ledger artifact recording the pressure"


def test_coordinator_provider_validation_records_state_change(tmp_path) -> None:
    """provider_validation event flips independent_validation_state but does not silently flip the contradiction."""

    coordinator = _coordinator(tmp_path)
    _record_contradiction_packet(coordinator, contradiction_id="contradiction-y")

    coordinator.ingest_pressure_signal(
        run_id="run-317",
        disputed_claim_id="claim-a",
        signal=PressureSignal.INDEPENDENT_VALIDATION,
        source="provider",
        timestamp="2026-08-30T11:00:00+00:00",
        quality="high",
        contradiction_id="contradiction-y",
        validation_state="passed",
    )

    refreshed = next(
        item
        for item in coordinator.ledger.load_run("run-317").artifacts
        if item.kind == CONTRADICTION_PACKET_KIND and item.id == "contradiction-y"
    )
    # Contradiction status still contested; independent validation recorded on the dispute.
    assert refreshed.payload.get("status") == "contested"
    dispute_packet = next(
        item for item in coordinator.ledger.load_run("run-317").artifacts if item.kind == DISPUTE_PACKET_KIND
    )
    assert dispute_packet.payload["independent_validation_state"] == "passed"
    # PROVIDER_VALIDATION_KIND artifact is also recorded for audit.
    provider_artifacts = [
        item for item in coordinator.ledger.load_run("run-317").artifacts if item.kind == PROVIDER_VALIDATION_KIND
    ]
    assert provider_artifacts


def test_coordinator_provider_validation_unknown_state_raises(tmp_path) -> None:
    """An invalid validation state raises DisputeDispositionError."""

    coordinator = _coordinator(tmp_path)
    _record_contradiction_packet(coordinator, contradiction_id="contradiction-z")

    with pytest.raises(DisputeDispositionError):
        coordinator.ingest_pressure_signal(
            run_id="run-317",
            disputed_claim_id="claim-a",
            signal=PressureSignal.INDEPENDENT_VALIDATION,
            source="provider",
            timestamp="2026-08-30T11:00:00+00:00",
            quality="high",
            contradiction_id="contradiction-z",
            validation_state="bogus",  # type: ignore[arg-type]
        )


def test_pressure_ledger_is_immutable_tuple() -> None:
    """Pressure ledger is a tuple (immutable history)."""

    ledger: PressureLedger = ()
    ledger = append_signal(
        ledger,
        signal=PressureSignal.REPEAT_ASSERTION,
        timestamp="2026-08-30T10:00:00+00:00",
        source="requester",
        quality="low",
    )
    with pytest.raises((AttributeError, TypeError)):
        ledger.append(  # type: ignore[attr-defined]
            ("extra",)
        )


def test_recorded_audit_trail_returns_full_history() -> None:
    """recorded_audit_trail exposes the immutable history of every flip."""

    basis = _evidence_basis(quality="low")
    audit_trail = DisputeAuditTrail(entries=())
    result = evaluate_dispute(
        claim_state={"supported_by": basis, "disputed": False},
        pressure_signals=(),
        evidence_updates=({"kind": "counter_evidence", "quality": "high", "basis_refs": ["src-1"]},),
        audit_trail=audit_trail,
    )
    history = recorded_audit_trail(result)
    assert history
    assert history[-1].disposition is DisputeDisposition.REQUESTER_RESOLVES


# ---------------------------------------------------------------------------
# Issue #424: the dispute module is merged into contradictions
# ---------------------------------------------------------------------------


def test_dispute_module_is_retired() -> None:
    """``research_tree.dispute`` no longer exists after the merge."""

    with pytest.raises(ModuleNotFoundError):
        import research_tree.dispute  # noqa: F401


def test_abandoned_dispute_entrypoints_retire() -> None:
    """Four dead dispute entrypoints retire with the merge (issue #424).

    ``derive_dispute_from_contradiction``, ``derive_with_disputes``,
    ``claim_ids_in``, and ``record_provider_validation`` had zero consumers in
    production and tests; the merge drops them and this case locks their
    absence in the merged module.
    """

    import research_tree.contradictions as contradictions_module

    for name in (
        "claim_ids_in",
        "derive_dispute_from_contradiction",
        "derive_with_disputes",
        "record_provider_validation",
    ):
        assert not hasattr(contradictions_module, name)
        assert name not in contradictions_module.__all__
