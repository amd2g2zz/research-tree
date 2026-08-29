"""Versioned, lineage-rich Insight Digest synthesis.

An Insight Digest is an input to policy selection. It deliberately cannot
authorize a lifecycle transition or issue a closure token.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping, Sequence

from .domain import ArtifactRef, ArtifactRevision
from .evidence_delta import EvidenceBaseline, measure_realized_delta
from .run_ledger import RunLedger

INSIGHT_SCHEMA_VERSION = 1
INSIGHT_PRODUCER_VERSION = "insight-v1"
_REQUIRED_FIELDS = {
    "schema_version",
    "producer_version",
    "digest_id",
    "source_refs",
    "slot_refs",
    "classified_statements",
    "covered_evidence_classes",
    "confirmed_facts",
    "hypotheses",
    "contradictions",
    "gaps",
    "recommendations",
    "limitations",
    "previous_digest_ref",
    "parent_refs",
    "realized_delta",
    "recommended_actions",
    "evidence_baseline",
    "transition_index",
    "confidence",
    "calibration",
    "changed_beliefs",
    "insights",
    "next_actions",
    "closure",
    "finding_pack_count",
}
_ALLOWED_KEYS = _REQUIRED_FIELDS


def synthesize_insights(
    finding_packs: Sequence[Any],
    *,
    active_slot_ids: Sequence[str],
    previous_digest: Mapping[str, Any] | None = None,
    producer_version: str = INSIGHT_PRODUCER_VERSION,
) -> dict[str, Any]:

    active_slots = tuple(sorted({str(item) for item in active_slot_ids if str(item).strip()}))
    normalized = _validate_and_normalize_finding_packs(finding_packs, active_slots)
    if previous_digest is not None:
        validate_insight_digest(previous_digest)
    by_slot: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for payload in normalized:
        by_slot[str(payload["decision_slot_id"])].append(payload)

    insights: list[dict[str, Any]] = []
    next_actions: list[dict[str, str]] = []
    classified_statements: list[dict[str, Any]] = []
    source_refs: set[str] = set()
    covered_evidence_classes: set[str] = set()
    confirmed_facts: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []
    parent_refs: set[str] = set()

    for payload in normalized:
        finding_id = str(payload["id"])
        parent_refs.add(f"finding:{finding_id}")
        for observation in payload.get("observations", ()):
            claim = str(observation["claim"]).strip()
            anchor = observation["anchor"]
            anchor_ref = str(anchor["ref"])
            source_refs.add(anchor_ref)
            evidence_class = str(observation.get("evidence_class", observation.get("kind", "claim")))
            covered_evidence_classes.add(evidence_class)
            classification = str(
                observation.get(
                    "classification",
                    observation.get("statement_type", "fact" if payload.get("validation_result") else "hypothesis"),
                )
            )
            statement = {
                "finding_pack_id": finding_id,
                "decision_slot_id": payload["decision_slot_id"],
                "classification": classification,
                "claim": claim,
                "source_refs": [anchor_ref],
                "evidence_class": evidence_class,
            }
            classified_statements.append(statement)
            (confirmed_facts if classification == "fact" else hypotheses).append(statement)
        for item in payload.get("remaining_uncertainties", ()):
            text = str(item).strip()
            if text:
                gaps.append(
                    {
                        "decision_slot_id": payload["decision_slot_id"],
                        "finding_pack_id": finding_id,
                        "kind": "implementation_uncertainty",
                        "text": text,
                        "source_refs": [f"finding:{finding_id}"],
                    }
                )
        for effect in payload.get("option_effects", ()):
            if isinstance(effect, Mapping) and effect.get("effect") == "contradicts":
                contradictions.append(
                    {
                        "decision_slot_id": payload["decision_slot_id"],
                        "finding_pack_id": finding_id,
                        "option": str(effect.get("option", "")),
                        "source_refs": [f"finding:{finding_id}"],
                    }
                )
        for item in payload.get("limitations", ()):
            limitations.append(
                {
                    "decision_slot_id": payload["decision_slot_id"],
                    "finding_pack_id": finding_id,
                    "text": str(item),
                }
            )

    for slot_id in active_slots:
        findings = by_slot.get(slot_id, [])
        claims: dict[str, list[str]] = defaultdict(list)
        effects: dict[str, set[str]] = defaultdict(set)
        anchors: set[tuple[str, str]] = set()
        uncertainties: list[str] = []
        finding_ids: list[str] = []
        for payload in findings:
            finding_id = str(payload["id"])
            finding_ids.append(finding_id)
            for observation in payload.get("observations", ()):
                claim = str(observation["claim"]).strip()
                if claim:
                    claims[claim].append(finding_id)
                anchor = observation["anchor"]
                anchors.add((str(anchor["kind"]), str(anchor["ref"])))
            for effect in payload.get("option_effects", ()):
                if isinstance(effect, Mapping):
                    option, value = effect.get("option"), effect.get("effect")
                    if isinstance(option, str) and isinstance(value, str):
                        effects[option].add(value)
            uncertainties.extend(str(item) for item in payload.get("remaining_uncertainties", ()) if str(item).strip())

        repeated_claims = [
            {"claim": claim, "finding_ids": sorted(set(ids)), "independent_count": len(set(ids))}
            for claim, ids in sorted(claims.items())
            if len(set(ids)) > 1
        ]
        conflicts = [
            {"option": option, "effects": sorted(values)}
            for option, values in sorted(effects.items())
            if {"supports", "contradicts"} <= values
        ]
        if not findings:
            signal = "uncovered"
            reason = "No Finding Pack has been ingested for this active Decision Slot."
            next_actions.append({"decision_slot_id": slot_id, "action": "dispatch_landscape"})
        elif conflicts:
            signal = "contested"
            reason = "Independent Finding Packs disagree on at least one option effect."
            next_actions.append({"decision_slot_id": slot_id, "action": "dispatch_adversarial_recheck"})
        elif len(anchors) < 2 or len(findings) < 2:
            signal = "thin"
            reason = "Evidence has not yet triangulated across independent workers or anchor classes."
            next_actions.append({"decision_slot_id": slot_id, "action": "dispatch_independent_depth"})
        elif uncertainties:
            signal = "qualified"
            reason = "Evidence converges but leaves explicit uncertainty requiring validation."
            next_actions.append({"decision_slot_id": slot_id, "action": "dispatch_validation"})
        else:
            signal = "converging"
            reason = "Independent findings currently agree and have multiple evidence anchors."
        insights.append(
            {
                "decision_slot_id": slot_id,
                "signal": signal,
                "reason": reason,
                "finding_ids": sorted(set(finding_ids)),
                "repeated_claims": repeated_claims,
                "conflicts": conflicts,
                "anchor_count": len(anchors),
                "uncertainties": sorted(set(uncertainties)),
            }
        )

    recommended_actions = list(next_actions)
    previous_baseline = EvidenceBaseline()
    previous_ref: str | None = None
    if previous_digest is not None:
        previous_baseline = EvidenceBaseline.from_dict(previous_digest.get("evidence_baseline", {}))
        previous_ref = str(previous_digest.get("digest_id", "")) or _digest(previous_digest)
    realized_delta, next_baseline = measure_realized_delta(
        previous_baseline,
        normalized,
        transition_index=1 if previous_digest is None else int(previous_digest.get("transition_index", 0)) + 1,
    )
    if realized_delta["no_change"] and previous_digest is not None:
        recommended_actions = list(previous_digest.get("recommended_actions", recommended_actions))
    digest_without_id = {
        "schema_version": INSIGHT_SCHEMA_VERSION,
        "producer_version": producer_version,
        "source_refs": sorted(source_refs),
        "slot_refs": list(active_slots),
        "classified_statements": sorted(
            classified_statements,
            key=lambda item: (item["decision_slot_id"], item["finding_pack_id"], item["claim"]),
        ),
        "covered_evidence_classes": sorted(covered_evidence_classes),
        "confirmed_facts": confirmed_facts,
        "hypotheses": hypotheses,
        "contradictions": contradictions,
        "gaps": gaps,
        "recommendations": recommended_actions,
        "limitations": limitations,
        "previous_digest_ref": previous_ref,
        "parent_refs": sorted(parent_refs),
        "realized_delta": realized_delta,
        "recommended_actions": recommended_actions,
        "evidence_baseline": next_baseline.to_dict(),
        "transition_index": realized_delta["transition_index"],
        "confidence": _confidence(insights),
        "calibration": {"method": "deterministic-heuristic-v1"},
        "changed_beliefs": [],
    }
    digest_id = _digest(digest_without_id)
    return {
        **digest_without_id,
        "digest_id": digest_id,
        "insights": insights,
        "next_actions": next_actions,
        "closure": "blocked_by_uncovered_or_contested_slots"
        if any(item["signal"] in {"uncovered", "contested", "thin", "qualified"} for item in insights)
        else "ready_for_decision_ledger_review",
        "finding_pack_count": len(normalized),
    }


def validate_insight_digest(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("insight digest must be a mapping")
    missing = _REQUIRED_FIELDS - set(value)
    if missing:
        raise ValueError(f"insight digest missing keys: {sorted(missing)}")
    extra = set(value) - _ALLOWED_KEYS
    if extra:
        raise ValueError(f"insight digest has unexpected keys: {sorted(extra)}")
    if value.get("closure") not in {
        "blocked_by_uncovered_or_contested_slots",
        "ready_for_decision_ledger_review",
    }:
        raise ValueError("insight digest closure is unsupported")
    if isinstance(value.get("finding_pack_count"), bool) or not isinstance(value.get("finding_pack_count"), int):
        raise ValueError("insight digest finding_pack_count must be an integer")
    if value.get("schema_version") != INSIGHT_SCHEMA_VERSION:
        raise ValueError("unsupported insight digest schema_version")
    if not isinstance(value.get("producer_version"), str) or not value["producer_version"].strip():
        raise ValueError("insight digest producer_version must be non-empty")
    slots = set(value.get("slot_refs", ()))
    if any(not isinstance(item, str) or not item for item in value.get("source_refs", ())):
        raise ValueError("insight digest source_refs must contain non-empty strings")
    seen: set[tuple[str, ...]] = set()
    for statement in value.get("classified_statements", ()):
        if not isinstance(statement, Mapping):
            raise ValueError("classified statements must be mappings")
        finding_id = str(statement.get("finding_pack_id", ""))
        slot_id = str(statement.get("decision_slot_id", ""))
        statement_key = (
            finding_id,
            str(statement.get("claim", "")),
            str(statement.get("source_refs", "")),
        )
        if not finding_id or statement_key in seen:
            raise ValueError("duplicate Finding Pack in insight digest")
        if slot_id not in slots:
            raise ValueError("classified statement references wrong active Decision Slot")
        seen.add(statement_key)
    if not isinstance(value.get("realized_delta"), Mapping):
        raise ValueError("insight digest realized_delta must be a mapping")


class CanonicalInsightWriter:
    """Persist a synthesized Insight Digest through the completion boundary."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise ValueError("canonical insight writer requires a RunLedger")
        self.ledger = ledger

    def write(
        self,
        *,
        round_id: str,
        insight_id: str,
        finding_packs: Sequence[Any],
        active_slot_ids: Sequence[str],
        expected_revision: int,
        previous_digest: Mapping[str, Any] | None = None,
    ) -> ArtifactRevision:
        payload = synthesize_insights(
            finding_packs,
            active_slot_ids=active_slot_ids,
            previous_digest=previous_digest,
        )
        parents = tuple(
            ArtifactRef(item.round_id, item.id, item.revision)
            for item in finding_packs
            if isinstance(item, ArtifactRevision)
        )
        from .completion_inputs import CompletionInputRegistrar

        return CompletionInputRegistrar(self.ledger).write_insight(
            round_id=round_id,
            insight_id=insight_id,
            payload=payload,
            parent_refs=parents,
            expected_revision=expected_revision,
        )


def _validate_and_normalize_finding_packs(
    finding_packs: Sequence[Any],
    active_slots: Sequence[str],
) -> tuple[Mapping[str, Any], ...]:
    normalized: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    active = set(active_slots)
    for finding in finding_packs:
        payload = finding.payload if hasattr(finding, "payload") else finding
        if not isinstance(payload, Mapping):
            raise ValueError("Finding Pack must be a mapping")
        finding_id = str(payload.get("id", getattr(finding, "id", ""))).strip()
        if not finding_id or finding_id in seen:
            raise ValueError("duplicate Finding Pack lineage")
        slot_id = payload.get("decision_slot_id")
        if not isinstance(slot_id, str) or slot_id not in active:
            raise ValueError("Finding Pack references an inactive active Decision Slot")
        observations = payload.get("observations", ())
        if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)) or not observations:
            raise ValueError("Finding Pack observations are required")
        copy = dict(payload)
        copy["id"] = finding_id
        for observation in observations:
            if not isinstance(observation, Mapping) or not str(observation.get("claim", "")).strip():
                raise ValueError("Finding Pack observation claim is required")
            anchor = observation.get("anchor")
            if (
                not isinstance(anchor, Mapping)
                or not str(anchor.get("kind", "")).strip()
                or not str(anchor.get("ref", "")).strip()
            ):
                raise ValueError("Finding Pack observation anchor lineage is required")
        seen.add(finding_id)
        normalized.append(copy)
    return tuple(sorted(normalized, key=lambda item: str(item["id"])))


def _confidence(insights: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not insights:
        return {"level": "unknown", "score": 0.0}
    score = sum(
        {"converging": 1.0, "qualified": 0.65, "thin": 0.35, "contested": 0.2, "uncovered": 0.0}.get(
            str(item["signal"]), 0.0
        )
        for item in insights
    ) / len(insights)
    level = "high" if score >= 0.8 else "medium" if score >= 0.45 else "low"
    return {"level": level, "score": round(score, 6)}


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "INSIGHT_PRODUCER_VERSION",
    "INSIGHT_SCHEMA_VERSION",
    "CanonicalInsightWriter",
    "synthesize_insights",
    "validate_insight_digest",
]
