"""Dispute governance — keep disagreement evidence-governed and pressure-resistant.

Issue #317.  Sits ABOVE :mod:`research_tree.contradictions` without modifying
its 8-state classification.  Five influences are tracked separately as the
sole path to a disposition flip:

* ``repeat_assertion`` — requester reasserts without new evidence
* ``social_pressure`` — emotional / authority-based pressure
* ``evidence_quality_change`` — new evidence with explicit quality rating
* ``assumption_change`` — requester updates a stated assumption
* ``independent_validation`` — external / provider validation result

Precedence (high→low): ``independent_validation`` > ``evidence_quality_change``
> ``assumption_change`` > ``social_pressure`` > ``repeat_assertion``.

A disposition only flips when the highest-precedence influence present beats
the current evidence basis.  Low-quality pressure (no new evidence) NEVER
flips; high-quality counter-evidence DOES.  Every flip writes an audit entry
with a reason, the influences that flipped it, and the previous disposition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Iterable, Mapping, Sequence

from .contradictions import (
    ContradictionPacket,
    ContradictionStatus,
    claim_from_mapping,
    detect_contradictions,
)

DISPUTE_PACKET_KIND: Final[str] = "dispute-ledger"
PROVIDER_VALIDATION_KIND: Final[str] = "provider-validation"

INDEPENDENT_VALIDATION_STATES: Final[frozenset[str]] = frozenset(
    {"none", "requested", "passed", "failed", "inconclusive"}
)


class PressureSignal(StrEnum):
    """Influences on a dispute, ranked from low to high authority."""

    REPEAT_ASSERTION = "repeat_assertion"
    SOCIAL_PRESSURE = "social_pressure"
    EVIDENCE_QUALITY_CHANGE = "evidence_quality_change"
    ASSUMPTION_CHANGE = "assumption_change"
    INDEPENDENT_VALIDATION = "independent_validation"


# Precedence from strongest to weakest.
DISPOSITION_PRECEDENCE: Final[tuple[PressureSignal, ...]] = (
    PressureSignal.INDEPENDENT_VALIDATION,
    PressureSignal.EVIDENCE_QUALITY_CHANGE,
    PressureSignal.ASSUMPTION_CHANGE,
    PressureSignal.SOCIAL_PRESSURE,
    PressureSignal.REPEAT_ASSERTION,
)

QUALITY_RANK: Final[Mapping[str, int]] = {"low": 0, "medium": 1, "high": 2}

EVIDENCE_QUALITIES: Final[frozenset[str]] = frozenset(QUALITY_RANK)


class DisputeDisposition(StrEnum):
    """Terminal posture of the Agent in response to a dispute."""

    AGENT_HOLDS = "agent_holds"
    REQUESTER_RESOLVES = "requester_resolves"
    ESCALATE = "escalate"
    DEFER = "defer"


@dataclass(frozen=True, slots=True)
class PressureEntry:
    """One recorded pressure signal with timestamp, source, and quality rating."""

    signal: PressureSignal
    timestamp: str
    source: str
    quality: str

    def __post_init__(self) -> None:
        if self.signal not in PressureSignal:
            raise DisputeDispositionError(f"unknown pressure signal: {self.signal!r}")
        if not isinstance(self.timestamp, str) or not self.timestamp.strip():
            raise DisputeDispositionError("pressure entry timestamp is required")
        if not isinstance(self.source, str) or not self.source.strip():
            raise DisputeDispositionError("pressure entry source is required")
        if self.quality not in EVIDENCE_QUALITIES:
            raise DisputeDispositionError(
                f"pressure entry quality must be one of {sorted(EVIDENCE_QUALITIES)}; got {self.quality!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal.value,
            "timestamp": self.timestamp,
            "source": self.source,
            "quality": self.quality,
        }


PressureLedger = tuple[PressureEntry, ...]


@dataclass(frozen=True, slots=True)
class DisputeAuditEntry:
    """One recorded flip with reason, influences, previous disposition, and timestamp."""

    disposition: DisputeDisposition
    influences: tuple[PressureSignal, ...]
    reason: str
    timestamp: str
    previous_disposition: DisputeDisposition

    def __post_init__(self) -> None:
        if self.disposition not in DisputeDisposition:
            raise DisputeDispositionError(f"unknown disposition: {self.disposition!r}")
        if not isinstance(self.influences, tuple):
            raise DisputeDispositionError("audit entry influences must be a tuple")
        for signal in self.influences:
            if signal not in PressureSignal:
                raise DisputeDispositionError(f"audit entry influence unknown: {signal!r}")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise DisputeDispositionError("audit entry reason is required")
        if not isinstance(self.timestamp, str) or not self.timestamp.strip():
            raise DisputeDispositionError("audit entry timestamp is required")
        if self.previous_disposition not in DisputeDisposition:
            raise DisputeDispositionError(f"unknown previous_disposition: {self.previous_disposition!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "influences": [signal.value for signal in self.influences],
            "reason": self.reason,
            "timestamp": self.timestamp,
            "previous_disposition": self.previous_disposition.value,
        }


@dataclass(frozen=True, slots=True)
class DisputeAuditTrail:
    """Immutable history of every disposition flip."""

    entries: tuple[DisputeAuditEntry, ...] = ()

    def to_dict(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.entries]


@dataclass(frozen=True, slots=True)
class DisputePacket:
    """A recorded dispute with audit trail and recommended verification path."""

    dispute_id: str
    disputed_claim_id: str
    requester_position: str
    agent_position: str
    evidence_basis: Mapping[str, Any]
    pressure_signals: tuple[PressureSignal, ...]
    independent_validation_state: str
    recommended_verification_path: tuple[str, ...]
    audit_trail: DisputeAuditTrail = DisputeAuditTrail()
    contradiction_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dispute_id, str) or not self.dispute_id.strip():
            raise DisputeDispositionError("dispute_id is required")
        if not isinstance(self.disputed_claim_id, str):
            raise DisputeDispositionError("disputed_claim_id must be a string")
        if not isinstance(self.requester_position, str):
            raise DisputeDispositionError("requester_position must be a string")
        if not isinstance(self.agent_position, str):
            raise DisputeDispositionError("agent_position must be a string")
        if not isinstance(self.evidence_basis, Mapping):
            raise DisputeDispositionError("evidence_basis must be a mapping")
        if not isinstance(self.pressure_signals, tuple):
            raise DisputeDispositionError("pressure_signals must be a tuple")
        if not isinstance(self.recommended_verification_path, tuple):
            raise DisputeDispositionError("recommended_verification_path must be a tuple")
        if self.independent_validation_state not in INDEPENDENT_VALIDATION_STATES:
            raise DisputeDispositionError(
                f"independent_validation_state must be one of {sorted(INDEPENDENT_VALIDATION_STATES)}; "
                f"got {self.independent_validation_state!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispute_id": self.dispute_id,
            "disputed_claim_id": self.disputed_claim_id,
            "requester_position": self.requester_position,
            "agent_position": self.agent_position,
            "evidence_basis": dict(self.evidence_basis),
            "pressure_signals": [signal.value for signal in self.pressure_signals],
            "independent_validation_state": self.independent_validation_state,
            "recommended_verification_path": list(self.recommended_verification_path),
            "audit_trail": self.audit_trail.to_dict(),
            "contradiction_id": self.contradiction_id,
        }

    @property
    def disposition(self) -> DisputeDisposition:
        """Current disposition: the latest flip, or agent_holds when no flip recorded."""

        if self.audit_trail.entries:
            return self.audit_trail.entries[-1].disposition
        if self.independent_validation_state == "passed":
            return DisputeDisposition.AGENT_HOLDS
        if self.independent_validation_state == "failed":
            return DisputeDisposition.REQUESTER_RESOLVES
        if self.independent_validation_state == "inconclusive":
            return DisputeDisposition.DEFER
        return DisputeDisposition.AGENT_HOLDS


class DisputeDispositionError(ValueError):
    """Raised for unrecoverable state-machine errors in the dispute layer."""


def append_signal(
    ledger: PressureLedger,
    *,
    signal: PressureSignal,
    timestamp: str,
    source: str,
    quality: str = "low",
) -> PressureLedger:
    """Append one pressure entry, returning a new immutable ledger tuple."""

    entry = PressureEntry(signal=signal, timestamp=timestamp, source=source, quality=quality)
    return (*ledger, entry)


def record_audit(
    influences: Sequence[PressureSignal],
    reason: str,
    *,
    disposition: DisputeDisposition = DisputeDisposition.AGENT_HOLDS,
    timestamp: str = "1970-01-01T00:00:00+00:00",
    previous_disposition: DisputeDisposition = DisputeDisposition.AGENT_HOLDS,
) -> DisputeAuditEntry:
    """Construct one audit entry — used by tests and by :func:`evaluate_dispute`."""

    return DisputeAuditEntry(
        disposition=disposition,
        influences=tuple(influences),
        reason=reason.strip(),
        timestamp=timestamp,
        previous_disposition=previous_disposition,
    )


def recorded_audit_trail(packet: DisputePacket) -> tuple[DisputeAuditEntry, ...]:
    """Return the immutable audit history from a packet."""

    return packet.audit_trail.entries


def record_provider_validation(
    *,
    timestamp: str,
    validation_state: str,
    source: str = "provider",
    quality: str = "high",
) -> PressureEntry:
    """Helper for callers that record a provider_validation event as a pressure signal."""

    return PressureEntry(
        signal=PressureSignal.INDEPENDENT_VALIDATION,
        timestamp=timestamp,
        source=source,
        quality=quality,
    )


def _evidence_quality(basis: Mapping[str, Any]) -> int:
    quality = basis.get("quality", "low")
    if quality not in QUALITY_RANK:
        return QUALITY_RANK["low"]
    return QUALITY_RANK[quality]


def _baseline_disposition(claim_state: Mapping[str, Any]) -> DisputeDisposition:
    """Initial disposition derived from evidence basis alone."""

    basis = claim_state.get("supported_by")
    if not isinstance(basis, Mapping):
        return DisputeDisposition.AGENT_HOLDS
    if basis.get("disputed") is True:
        return DisputeDisposition.DEFER
    return DisputeDisposition.AGENT_HOLDS


def _independent_validation_disposition(state: str) -> DisputeDisposition | None:
    if state == "passed":
        return DisputeDisposition.AGENT_HOLDS
    if state == "failed":
        return DisputeDisposition.REQUESTER_RESOLVES
    if state == "inconclusive":
        return DisputeDisposition.DEFER
    if state in {"none", "requested"}:
        return None
    raise DisputeDispositionError(f"unknown independent_validation state: {state!r}")


def _dominant_pressure_signal(
    pressure_signals: Sequence[PressureSignal],
    *,
    evidence_quality_change: str | None,
) -> PressureSignal | None:
    """Return the highest-precedence pressure signal present in the input."""

    if evidence_quality_change is not None:
        return PressureSignal.EVIDENCE_QUALITY_CHANGE
    if not pressure_signals:
        return None
    ordered = sorted(set(pressure_signals), key=lambda signal: DISPOSITION_PRECEDENCE.index(signal))
    return ordered[0]


def evaluate_dispute(
    claim_state: Mapping[str, Any],
    pressure_signals: Sequence[PressureSignal],
    evidence_updates: Sequence[Mapping[str, Any]],
    audit_trail: DisputeAuditTrail,
    *,
    independent_validation: str = "none",
    evidence_quality_change: str | None = None,
    timestamp: str = "1970-01-01T00:00:00+00:00",
) -> DisputePacket:
    """Pure-function disposition evaluator for one claim under one pressure batch.

    Precedence: independent_validation > evidence_quality_change >
    assumption_change > social_pressure > repeat_assertion.  Low-quality
    pressure alone does not flip; high-quality counter-evidence DOES.
    """

    if independent_validation not in INDEPENDENT_VALIDATION_STATES:
        raise DisputeDispositionError(
            f"independent_validation must be one of {sorted(INDEPENDENT_VALIDATION_STATES)}; "
            f"got {independent_validation!r}"
        )
    if evidence_quality_change is not None and evidence_quality_change not in EVIDENCE_QUALITIES:
        raise DisputeDispositionError(
            f"evidence_quality_change must be one of {sorted(EVIDENCE_QUALITIES)}; got {evidence_quality_change!r}"
        )

    basis = claim_state.get("supported_by", {})
    baseline = _baseline_disposition(claim_state)
    basis_quality = _evidence_quality(basis if isinstance(basis, Mapping) else {})

    # Precedence ladder: each rung can only override when its input is "stronger" than the current basis.
    new_disposition = baseline
    influences: tuple[PressureSignal, ...] = ()
    reason = "evidence_basis_holds"

    validation_disposition = _independent_validation_disposition(independent_validation)
    if validation_disposition is not None and validation_disposition != baseline:
        influences = (PressureSignal.INDEPENDENT_VALIDATION,)
        if validation_disposition is DisputeDisposition.REQUESTER_RESOLVES:
            reason = "independent_validation_failed"
        elif validation_disposition is DisputeDisposition.DEFER:
            reason = "independent_validation_inconclusive"
        else:
            reason = "independent_validation_passed"
        new_disposition = validation_disposition

    if new_disposition is baseline and evidence_quality_change is not None:
        new_rank = QUALITY_RANK[evidence_quality_change]
        if new_rank > basis_quality:
            influences = (PressureSignal.EVIDENCE_QUALITY_CHANGE,)
            reason = "high_quality_counter_evidence" if evidence_quality_change == "high" else "evidence_quality_change"
            new_disposition = DisputeDisposition.REQUESTER_RESOLVES

    # Update baseline from evidence_updates (high-quality counter-evidence flips).
    if new_disposition is baseline:
        for update in evidence_updates:
            if not isinstance(update, Mapping):
                continue
            if update.get("kind") != "counter_evidence":
                continue
            quality = update.get("quality", "low")
            if quality not in EVIDENCE_QUALITIES:
                continue
            if QUALITY_RANK[quality] >= QUALITY_RANK["high"]:
                influences = (PressureSignal.EVIDENCE_QUALITY_CHANGE,)
                reason = "high_quality_counter_evidence"
                new_disposition = DisputeDisposition.REQUESTER_RESOLVES
                break

    # Assumption change alone escalates (not flips) when no better evidence is available.
    if new_disposition is baseline and PressureSignal.ASSUMPTION_CHANGE in pressure_signals and not evidence_updates:
        influences = (PressureSignal.ASSUMPTION_CHANGE,)
        reason = "assumption_change_requires_revalidation"
        new_disposition = DisputeDisposition.ESCALATE

    # Low-quality pressure signals (social_pressure / repeat_assertion) NEVER flip.
    # They are recorded but cannot move the disposition off baseline.
    if new_disposition is baseline and any(
        signal in {PressureSignal.SOCIAL_PRESSURE, PressureSignal.REPEAT_ASSERTION} for signal in pressure_signals
    ):
        influences = tuple(
            dict.fromkeys(
                pressure_signals
                + (
                    PressureSignal.SOCIAL_PRESSURE,
                    PressureSignal.REPEAT_ASSERTION,
                )
            )
        )
        # Strip noise: the recorded influence for the no-op is the dominant one only.
        dominant = _dominant_pressure_signal(pressure_signals, evidence_quality_change=None)
        if dominant is not None:
            influences = (dominant,)
        reason = "pressure_without_new_evidence"

    # Append audit entry when the disposition flipped, OR when pressure signals
    # were received without producing a flip (recorded for audit completeness).
    new_entries = audit_trail.entries
    if new_disposition is not baseline:
        entry = DisputeAuditEntry(
            disposition=new_disposition,
            influences=influences,
            reason=reason,
            timestamp=timestamp,
            previous_disposition=baseline,
        )
        new_entries = (*new_entries, entry)
    elif pressure_signals:
        recorded = tuple(
            dict.fromkeys(pressure_signals + (PressureSignal.SOCIAL_PRESSURE, PressureSignal.REPEAT_ASSERTION))
        )
        dominant = _dominant_pressure_signal(pressure_signals, evidence_quality_change=None)
        if dominant is not None:
            recorded = (dominant,)
        no_flip_entry = DisputeAuditEntry(
            disposition=baseline,
            influences=recorded,
            reason=reason,
            timestamp=timestamp,
            previous_disposition=baseline,
        )
        new_entries = (*new_entries, no_flip_entry)

    recommended_path = _recommended_verification_path(new_disposition, evidence_updates)
    disputed_claim_id = str(claim_state.get("disputed_claim_id", "")) or "unknown"
    dispute_id = "dispute-" + disputed_claim_id
    requester_position = str(claim_state.get("requester_position", ""))
    agent_position = str(claim_state.get("agent_position", "agent holds claim by evidence"))
    return DisputePacket(
        dispute_id=dispute_id,
        disputed_claim_id=disputed_claim_id,
        requester_position=requester_position,
        agent_position=agent_position,
        evidence_basis=basis if isinstance(basis, Mapping) else {},
        pressure_signals=tuple(pressure_signals),
        independent_validation_state=independent_validation,
        recommended_verification_path=recommended_path,
        audit_trail=DisputeAuditTrail(entries=new_entries),
        contradiction_id=claim_state.get("contradiction_id") if isinstance(claim_state, Mapping) else None,
    )


def _recommended_verification_path(
    disposition: DisputeDisposition, evidence_updates: Iterable[Mapping[str, Any]]
) -> tuple[str, ...]:
    if disposition is DisputeDisposition.AGENT_HOLDS:
        return ("preserve_current_evidence",)
    if disposition is DisputeDisposition.REQUESTER_RESOLVES:
        return ("accept_requester_position", "preserve_audit_trail")
    if disposition is DisputeDisposition.ESCALATE:
        return ("independent_source", "explicit_method_revision")
    if disposition is DisputeDisposition.DEFER:
        return ("independent_validation", "human_review")
    return ()


def derive_dispute_from_contradiction(
    *,
    contradiction: ContradictionPacket,
    claim_state: Mapping[str, Any],
    pressure_signals: Sequence[PressureSignal] = (),
    evidence_updates: Sequence[Mapping[str, Any]] = (),
    audit_trail: DisputeAuditTrail = DisputeAuditTrail(),
    independent_validation: str = "none",
    evidence_quality_change: str | None = None,
    timestamp: str = "1970-01-01T00:00:00+00:00",
) -> DisputePacket:
    """Build a DisputePacket anchored on a contradiction packet's claim set."""

    if not isinstance(contradiction, ContradictionPacket):
        raise DisputeDispositionError("derive_dispute_from_contradiction requires a ContradictionPacket")
    disputed_claim = claim_state.get("disputed_claim_id")
    if disputed_claim not in contradiction.claim_ids:
        raise DisputeDispositionError("disputed_claim_id must belong to the contradiction packet")
    evaluated = evaluate_dispute(
        claim_state=claim_state,
        pressure_signals=pressure_signals,
        evidence_updates=evidence_updates,
        audit_trail=audit_trail,
        independent_validation=independent_validation,
        evidence_quality_change=evidence_quality_change,
        timestamp=timestamp,
    )
    return DisputePacket(
        dispute_id=evaluated.dispute_id,
        disputed_claim_id=evaluated.disputed_claim_id,
        requester_position=evaluated.requester_position or "requester disputes claim",
        agent_position=evaluated.agent_position
        or f"agent holds claim {evaluated.disputed_claim_id} under contradiction {contradiction.reason}",
        evidence_basis=evaluated.evidence_basis,
        pressure_signals=evaluated.pressure_signals,
        independent_validation_state=evaluated.independent_validation_state,
        recommended_verification_path=evaluated.recommended_verification_path,
        audit_trail=evaluated.audit_trail,
        contradiction_id=str(contradiction.claim_ids),
    )


def claim_ids_in(contradiction: ContradictionPacket) -> tuple[str, ...]:
    """Return the canonical sorted claim identifiers for a contradiction."""

    if not isinstance(contradiction, ContradictionPacket):
        raise DisputeDispositionError("claim_ids_in requires a ContradictionPacket")
    return tuple(contradiction.claim_ids)


# Wire into the contradiction detector without changing its 8-state semantics.
def derive_with_disputes(
    claims: Iterable[Any],
    *,
    pressure_signals_by_claim: Mapping[str, Sequence[PressureSignal]] = {},
    evidence_updates_by_claim: Mapping[str, Sequence[Mapping[str, Any]]] = {},
    independent_validation_by_claim: Mapping[str, str] = {},
    evidence_quality_change_by_claim: Mapping[str, str] = {},
    timestamp: str = "1970-01-01T00:00:00+00:00",
) -> tuple[tuple[ContradictionPacket, ...], dict[str, DisputePacket]]:
    """Run the contradiction detector AND derive dispute packets per claim.

    Returns the unchanged contradiction packets (8-state classification
    untouched) alongside a mapping of claim_id → DisputePacket.  This is the
    only sanctioned entrypoint that exposes pressure evidence to the existing
    contradiction classification.
    """

    typed = tuple(claims)
    packets = detect_contradictions(typed)
    disputes: dict[str, DisputePacket] = {}
    contested_claims = {
        claim_id
        for packet in packets
        if packet.status in {ContradictionStatus.UNRESOLVED, ContradictionStatus.CONTESTED}
        for claim_id in packet.claim_ids
    }
    for claim_id in sorted(contested_claims):
        try:
            typed_claim = next(item for item in typed if getattr(item, "claim_id", None) == claim_id)
        except StopIteration as error:
            raise DisputeDispositionError(f"claim {claim_id} not present in supplied claims") from error
        basis = {"quality": "medium", "basis_refs": list(getattr(typed_claim, "basis_refs", ()))}
        claim_state = {
            "disputed_claim_id": claim_id,
            "supported_by": basis,
            "disputed": True,
            "requester_position": "requester disputes claim",
            "agent_position": f"agent holds claim {claim_id}",
        }
        evaluated = evaluate_dispute(
            claim_state=claim_state,
            pressure_signals=tuple(pressure_signals_by_claim.get(claim_id, ())),
            evidence_updates=tuple(evidence_updates_by_claim.get(claim_id, ())),
            audit_trail=DisputeAuditTrail(),
            independent_validation=independent_validation_by_claim.get(claim_id, "none"),
            evidence_quality_change=evidence_quality_change_by_claim.get(claim_id),
            timestamp=timestamp,
        )
        disputes[claim_id] = evaluated
    return packets, disputes


def dispute_packet_from_payload(payload: Mapping[str, Any]) -> DisputePacket:
    """Decode a stored dispute packet payload."""

    required = {
        "dispute_id",
        "disputed_claim_id",
        "requester_position",
        "agent_position",
        "evidence_basis",
        "pressure_signals",
        "independent_validation_state",
        "recommended_verification_path",
    }
    if set(payload) - required - {"audit_trail", "contradiction_id"} or not required <= set(payload):
        raise DisputeDispositionError("dispute payload has unsupported fields")
    entries_raw = payload.get("audit_trail", ())
    entries: list[DisputeAuditEntry] = []
    if isinstance(entries_raw, Sequence) and not isinstance(entries_raw, (str, bytes)):
        for raw in entries_raw:
            if not isinstance(raw, Mapping):
                raise DisputeDispositionError("audit_trail entry must be a mapping")
            entries.append(
                DisputeAuditEntry(
                    disposition=DisputeDisposition(str(raw.get("disposition"))),
                    influences=tuple(PressureSignal(str(value)) for value in raw.get("influences", ())),
                    reason=str(raw.get("reason", "")),
                    timestamp=str(raw.get("timestamp", "")),
                    previous_disposition=DisputeDisposition(str(raw.get("previous_disposition"))),
                )
            )
    return DisputePacket(
        dispute_id=str(payload["dispute_id"]),
        disputed_claim_id=str(payload["disputed_claim_id"]),
        requester_position=str(payload["requester_position"]),
        agent_position=str(payload["agent_position"]),
        evidence_basis=dict(payload["evidence_basis"]),
        pressure_signals=tuple(PressureSignal(str(value)) for value in payload["pressure_signals"]),
        independent_validation_state=str(payload["independent_validation_state"]),
        recommended_verification_path=tuple(str(value) for value in payload["recommended_verification_path"]),
        audit_trail=DisputeAuditTrail(entries=tuple(entries)),
        contradiction_id=payload.get("contradiction_id"),
    )


# Re-export claim_from_mapping so callers can reuse the canonical decoder alongside dispute wiring.
__all__ = [
    "DISPOSITION_PRECEDENCE",
    "DISPUTE_PACKET_KIND",
    "EVIDENCE_QUALITIES",
    "INDEPENDENT_VALIDATION_STATES",
    "PROVIDER_VALIDATION_KIND",
    "DisputeAuditEntry",
    "DisputeAuditTrail",
    "DisputeDisposition",
    "DisputeDispositionError",
    "DisputePacket",
    "PressureEntry",
    "PressureLedger",
    "PressureSignal",
    "QUALITY_RANK",
    "append_signal",
    "claim_from_mapping",
    "claim_ids_in",
    "derive_dispute_from_contradiction",
    "derive_with_disputes",
    "dispute_packet_from_payload",
    "evaluate_dispute",
    "record_audit",
    "record_provider_validation",
    "recorded_audit_trail",
]
