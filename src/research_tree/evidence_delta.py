"""Measure evidence-ledger changes across persisted research transitions."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class EvidenceBaseline:
    """Deduplicated evidence known before a tree transition."""

    finding_ids: tuple[str, ...] = ()
    claim_fingerprints: tuple[str, ...] = ()
    anchor_fingerprints: tuple[str, ...] = ()
    effect_fingerprints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "finding_ids": list(self.finding_ids),
            "claim_fingerprints": list(self.claim_fingerprints),
            "anchor_fingerprints": list(self.anchor_fingerprints),
            "effect_fingerprints": list(self.effect_fingerprints),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceBaseline":
        return cls(
            finding_ids=_strings(value.get("finding_ids", ())),
            claim_fingerprints=_strings(value.get("claim_fingerprints", ())),
            anchor_fingerprints=_strings(value.get("anchor_fingerprints", ())),
            effect_fingerprints=_strings(value.get("effect_fingerprints", ())),
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
        claim_fingerprints=tuple(
            sorted(set(baseline.claim_fingerprints) | evidence["claim_fingerprints"])
        ),
        anchor_fingerprints=tuple(
            sorted(set(baseline.anchor_fingerprints) | evidence["anchor_fingerprints"])
        ),
        effect_fingerprints=tuple(
            sorted(set(baseline.effect_fingerprints) | evidence["effect_fingerprints"])
        ),
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
    provenance_groups: set[str] = set()
    oracle_ref_count = 0
    implementation_uncertainty_count = 0
    closure_effect_count = 0
    for finding in finding_packs:
        evidence = _fingerprints(finding)
        new_finding_ids.update(set(evidence["finding_ids"]) - set(incoming.finding_ids))
        new_claims.update(set(evidence["claim_fingerprints"]) - set(incoming.claim_fingerprints))
        new_anchors.update(set(evidence["anchor_fingerprints"]) - set(incoming.anchor_fingerprints))
        new_effects.update(set(evidence["effect_fingerprints"]) - set(incoming.effect_fingerprints))
        payload = _payload(finding)
        for observation in payload.get("observations", ()):
            if isinstance(observation, Mapping):
                group = str(observation.get("provenance_group", "")).strip()
                if group:
                    provenance_groups.add(group)
        oracle_ref_count += len(payload.get("oracle_run_refs", ()))
        implementation_uncertainty_count += len(payload.get("implementation_uncertainties", ()))
        implementation_uncertainty_count += len(payload.get("remaining_uncertainties", ()))
        closure_effect_count += sum(
            1 for effect in payload.get("option_effects", ())
            if isinstance(effect, Mapping) and effect.get("effect") in {"supports", "rejects", "contradicts"}
        )
        contradiction_count += sum(
            1
            for effect in payload.get("option_effects", ())
            if isinstance(effect, Mapping) and effect.get("effect") == "contradicts"
        )
        continuation_count += len(payload.get("research_continuations", ()))
        continuation_count += len(payload.get("remaining_uncertainties", ()))
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
    closure_components = {
        "evidence_class": round(min(1.0, len(new_anchors) / 3), 6),
        "independence": round(min(1.0, len(provenance_groups) / 2), 6),
        "contradiction": round(min(1.0, contradiction_count / 2), 6),
        "oracle": round(min(1.0, oracle_ref_count / 1), 6),
        "implementation_uncertainty": round(min(1.0, implementation_uncertainty_count / 2), 6),
        "decision_closure": round(min(1.0, closure_effect_count / 2), 6),
    }
    return (
        {
            "transition_index": transition_index,
            "realized_delta": round(score, 6),
            "new_finding_count": len(new_finding_ids),
            "new_claim_count": len(new_claims),
            "new_anchor_count": len(new_anchors),
            "new_effect_count": len(new_effects),
            "contradiction_count": contradiction_count,
            "new_continuation_count": continuation_count,
            "baseline_finding_count": len(baseline.finding_ids),
            "duplicate_only": score == 0.0 and bool(finding_packs),
            "closure_components": closure_components,
        },
        incoming,
    )


def _fingerprints(finding: Any) -> dict[str, set[str]]:
    payload = _payload(finding)
    claims: set[str] = set()
    anchors: set[str] = set()
    effects: set[str] = set()
    for observation in payload.get("observations", ()):
        if not isinstance(observation, Mapping):
            continue
        claim = str(observation.get("claim", "")).strip()
        if claim:
            claims.add(_digest(_normalize(claim)))
        anchor = observation.get("anchor")
        if isinstance(anchor, Mapping):
            anchors.add(_digest(f"{anchor.get('kind')}:{anchor.get('ref')}"))
    for effect in payload.get("option_effects", ()):
        if isinstance(effect, Mapping):
            effects.add(_digest(f"{effect.get('option')}:{effect.get('effect')}"))
    finding_id = str(payload.get("id", getattr(finding, "id", ""))).strip()
    return {
        "finding_ids": {finding_id} if finding_id else set(),
        "claim_fingerprints": claims,
        "anchor_fingerprints": anchors,
        "effect_fingerprints": effects,
    }


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
