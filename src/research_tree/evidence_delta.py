"""Measure evidence-ledger changes across persisted research transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence


DELTA_COMPONENTS = (
    "evidence_class_coverage",
    "provenance_independence",
    "contradiction_state",
    "oracle_state",
    "implementation_uncertainty",
    "slot_closure_change",
)


@dataclass(frozen=True, slots=True)
class RealizedDelta:
    evidence_class_coverage: float = 0.0
    provenance_independence: float = 0.0
    contradiction_state: float = 0.0
    oracle_state: float = 0.0
    implementation_uncertainty: float = 0.0
    slot_closure_change: float = 0.0
    references: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    no_change: bool = False

    @property
    def vector(self) -> tuple[float, ...]:
        return tuple(float(getattr(self, name)) for name in DELTA_COMPONENTS)

    @property
    def realized_delta(self) -> float:
        return round(sum(self.vector) / len(self.vector), 6)

    def to_dict(self) -> dict[str, Any]:
        components = {
            name: {
                "value": value,
                "references": list(self.references.get(name, ())),
                "contribution": value,
            }
            for name, value in zip(DELTA_COMPONENTS, self.vector)
        }
        return {
            "components": components,
            "delta_vector": list(self.vector),
            "realized_delta": self.realized_delta,
            "references": {key: list(value) for key, value in self.references.items()},
            "no_change": self.no_change,
            "penalty": "no_progress" if self.no_change else None,
        }


@dataclass(frozen=True, slots=True)
class EvidenceBaseline:
    finding_ids: tuple[str, ...] = ()
    claim_fingerprints: tuple[str, ...] = ()
    anchor_fingerprints: tuple[str, ...] = ()
    effect_fingerprints: tuple[str, ...] = ()
    evidence_class_fingerprints: tuple[str, ...] = ()
    provenance_fingerprints: tuple[str, ...] = ()
    contradiction_fingerprints: tuple[str, ...] = ()
    oracle_fingerprints: tuple[str, ...] = ()
    uncertainty_fingerprints: tuple[str, ...] = ()
    closure_fingerprints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "finding_ids": list(self.finding_ids),
            "claim_fingerprints": list(self.claim_fingerprints),
            "anchor_fingerprints": list(self.anchor_fingerprints),
            "effect_fingerprints": list(self.effect_fingerprints),
            "evidence_class_fingerprints": list(self.evidence_class_fingerprints),
            "provenance_fingerprints": list(self.provenance_fingerprints),
            "contradiction_fingerprints": list(self.contradiction_fingerprints),
            "oracle_fingerprints": list(self.oracle_fingerprints),
            "uncertainty_fingerprints": list(self.uncertainty_fingerprints),
            "closure_fingerprints": list(self.closure_fingerprints),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceBaseline":
        return cls(
            finding_ids=_strings(value.get("finding_ids", ())),
            claim_fingerprints=_strings(value.get("claim_fingerprints", ())),
            anchor_fingerprints=_strings(value.get("anchor_fingerprints", ())),
            effect_fingerprints=_strings(value.get("effect_fingerprints", ())),
            evidence_class_fingerprints=_strings(value.get("evidence_class_fingerprints", ())),
            provenance_fingerprints=_strings(value.get("provenance_fingerprints", ())),
            contradiction_fingerprints=_strings(value.get("contradiction_fingerprints", ())),
            oracle_fingerprints=_strings(value.get("oracle_fingerprints", ())),
            uncertainty_fingerprints=_strings(value.get("uncertainty_fingerprints", ())),
            closure_fingerprints=_strings(value.get("closure_fingerprints", ())),
        )


def baseline_from_finding_packs(finding_packs: Sequence[Any]) -> EvidenceBaseline:
    """Load historical material as baseline, not as a gain event."""

    result = EvidenceBaseline()
    for finding in finding_packs:
        result = merge_baseline(result, finding)
    return result


def merge_baseline(baseline: EvidenceBaseline, finding: Any) -> EvidenceBaseline:
    evidence = _fingerprints(finding)
    return EvidenceBaseline(
        finding_ids=tuple(sorted(set(baseline.finding_ids) | evidence["finding_ids"])),
        claim_fingerprints=tuple(sorted(set(baseline.claim_fingerprints) | evidence["claim_fingerprints"])),
        anchor_fingerprints=tuple(sorted(set(baseline.anchor_fingerprints) | evidence["anchor_fingerprints"])),
        effect_fingerprints=tuple(sorted(set(baseline.effect_fingerprints) | evidence["effect_fingerprints"])),
        evidence_class_fingerprints=tuple(
            sorted(set(baseline.evidence_class_fingerprints) | evidence["evidence_class_coverage"])
        ),
        provenance_fingerprints=tuple(
            sorted(set(baseline.provenance_fingerprints) | evidence["provenance_independence"])
        ),
        contradiction_fingerprints=tuple(
            sorted(set(baseline.contradiction_fingerprints) | evidence["contradiction_state"])
        ),
        oracle_fingerprints=tuple(sorted(set(baseline.oracle_fingerprints) | evidence["oracle_state"])),
        uncertainty_fingerprints=tuple(
            sorted(set(baseline.uncertainty_fingerprints) | evidence["implementation_uncertainty"])
        ),
        closure_fingerprints=tuple(sorted(set(baseline.closure_fingerprints) | evidence["slot_closure_change"])),
    )


def measure_realized_delta(
    baseline: EvidenceBaseline,
    finding_packs: Sequence[Any],
    *,
    transition_index: int,
) -> tuple[dict[str, Any], EvidenceBaseline]:
    """Return an auditable state delta and the updated evidence baseline."""

    if transition_index < 1:
        raise ValueError("transition_index must be positive for a measured transition")
    incoming = baseline
    new_finding_ids: set[str] = set()
    new_claims: set[str] = set()
    new_anchors: set[str] = set()
    new_effects: set[str] = set()
    contradiction_count = 0
    continuation_count = 0
    new_components: dict[str, set[str]] = {name: set() for name in DELTA_COMPONENTS}
    references: dict[str, set[str]] = {name: set() for name in DELTA_COMPONENTS}
    for finding in finding_packs:
        evidence = _fingerprints(finding)
        new_finding_ids.update(set(evidence["finding_ids"]) - set(incoming.finding_ids))
        new_claims.update(set(evidence["claim_fingerprints"]) - set(incoming.claim_fingerprints))
        new_anchors.update(set(evidence["anchor_fingerprints"]) - set(incoming.anchor_fingerprints))
        new_effects.update(set(evidence["effect_fingerprints"]) - set(incoming.effect_fingerprints))
        payload = _payload(finding)
        contradiction_count += len(evidence["contradiction_state"])
        continuation_count += len(payload.get("research_continuations", ()))
        continuation_count += len(payload.get("remaining_uncertainties", ()))
        for name, values in evidence.items():
            if name not in new_components:
                continue
            prior = set(getattr(incoming, _baseline_field(name)))
            new_values = values - prior
            new_components[name].update(new_values)
            references[name].update(new_values)
        incoming = merge_baseline(incoming, finding)

    # This bounded value is a scheduling heuristic, not a probability or a
    # worker quality score.  Raw component counts remain authoritative.
    score = min(
        1.0,
        0.35 * min(1.0, len(new_anchors) / 3)
        + 0.30 * min(1.0, len(new_claims) / 3)
        + 0.20 * min(1.0, len(new_effects) / 2)
        + 0.10 * min(1.0, contradiction_count / 2)
        + 0.05 * min(1.0, continuation_count / 2),
    )
    component_values = {
        name: min(1.0, len(values) / (2 if name in {"contradiction_state", "oracle_state"} else 3))
        for name, values in new_components.items()
    }
    if new_finding_ids:
        fallback_refs = tuple(sorted(new_finding_ids))
        for name in DELTA_COMPONENTS:
            references[name].update(fallback_refs)
    vector = RealizedDelta(
        **component_values,
        references={name: tuple(sorted(values)) for name, values in references.items()},
        no_change=all(value == 0.0 for value in component_values.values()),
    )
    components = {
        name: {
            "value": value,
            "references": list(vector.references.get(name, ())),
            "contribution": value,
        }
        for name, value in component_values.items()
    }
    baseline_digest = _digest(_normalize(str(baseline.to_dict())))
    current_digest = _digest(_normalize(str(incoming.to_dict())))
    return (
        {
            "schema_version": 2,
            "transition_index": transition_index,
            "baseline_digest": baseline_digest,
            "current_digest": current_digest,
            "realized_delta": round(score, 6),
            "new_finding_count": len(new_finding_ids),
            "new_claim_count": len(new_claims),
            "new_anchor_count": len(new_anchors),
            "new_effect_count": len(new_effects),
            "contradiction_count": contradiction_count,
            "new_continuation_count": continuation_count,
            "baseline_finding_count": len(baseline.finding_ids),
            "duplicate_only": score == 0.0 and bool(finding_packs),
            "components": components,
            "delta_vector": list(vector.vector),
            "realized_delta_vector": vector.to_dict(),
            "no_change": vector.no_change,
            "penalty": "no_progress" if vector.no_change else None,
        },
        incoming,
    )


def _fingerprints(finding: Any) -> dict[str, set[str]]:
    payload = _payload(finding)
    claims: set[str] = set()
    anchors: set[str] = set()
    effects: set[str] = set()
    evidence_classes: set[str] = set()
    provenance: set[str] = set()
    contradictions: set[str] = set()
    oracles: set[str] = set()
    uncertainties: set[str] = set()
    closures: set[str] = set()
    for observation in payload.get("observations", ()):
        if not isinstance(observation, Mapping):
            continue
        claim = str(observation.get("claim", "")).strip()
        if claim:
            claims.add(_digest(_normalize(claim)))
            evidence_classes.add(str(observation.get("evidence_class", observation.get("kind", "claim"))))
        provenance_group = observation.get("provenance_group", payload.get("provenance_group"))
        if provenance_group:
            provenance.add(_digest(str(provenance_group)))
        anchor = observation.get("anchor")
        if isinstance(anchor, Mapping):
            anchors.add(_digest(f"{anchor.get('kind')}:{anchor.get('ref')}"))
            anchor_group = anchor.get("provenance_group")
            if anchor_group:
                provenance.add(_digest(str(anchor_group)))
    for effect in payload.get("option_effects", ()):
        if isinstance(effect, Mapping):
            effects.add(_digest(f"{effect.get('option')}:{effect.get('effect')}"))
    for item in payload.get("contradictions", ()):
        contradictions.add(_digest(_normalize(str(item))))
    if payload.get("contradiction_id") and payload.get("status") in {"contested", "unresolved"}:
        contradictions.add(
            _digest(
                _normalize(
                    ":".join(
                        str(payload.get(name, ""))
                        for name in ("contradiction_id", "status", "claim_ids", "conflict_reason")
                    )
                )
            )
        )
    validation = payload.get("validation_result")
    if isinstance(validation, Mapping):
        oracles.add(_digest(_normalize(str(validation.get("status", "unknown")))))
    elif validation is not None:
        oracles.add(_digest(_normalize(str(validation))))
    for item in (
        *payload.get("remaining_uncertainties", ()),
        *payload.get("implementation_uncertainties", ()),
    ):
        if str(item).strip():
            uncertainties.add(_digest(_normalize(str(item))))
    closure = payload.get("slot_closure", payload.get("closure_status", payload.get("status")))
    if closure is not None:
        closures.add(_digest(_normalize(str(closure))))
    finding_id = str(payload.get("id", getattr(finding, "id", ""))).strip()
    return {
        "finding_ids": {finding_id} if finding_id else set(),
        "claim_fingerprints": claims,
        "anchor_fingerprints": anchors,
        "effect_fingerprints": effects,
        "evidence_class_coverage": evidence_classes,
        "provenance_independence": provenance,
        "contradiction_state": contradictions,
        "oracle_state": oracles,
        "implementation_uncertainty": uncertainties,
        "slot_closure_change": closures,
    }


def _baseline_field(component: str) -> str:
    return {
        "evidence_class_coverage": "evidence_class_fingerprints",
        "provenance_independence": "provenance_fingerprints",
        "contradiction_state": "contradiction_fingerprints",
        "oracle_state": "oracle_fingerprints",
        "implementation_uncertainty": "uncertainty_fingerprints",
        "slot_closure_change": "closure_fingerprints",
    }[component]


def _payload(value: Any) -> Mapping[str, Any]:
    payload = value.payload if hasattr(value, "payload") else value
    return payload if isinstance(payload, Mapping) else {}


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("baseline fields must be sequences")
    return tuple(sorted({str(item) for item in value if str(item)}))


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
