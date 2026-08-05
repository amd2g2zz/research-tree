"""Cross-worker insight extraction without replacing provenance or decisions."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from typing import Any, Mapping, Sequence

from .contracts import canonical_json_bytes


CANONICAL_STATEMENT_CLASSES = frozenset({"fact", "inference", "recommendation", "unknown"})


class InsightDigestError(ValueError):
    pass


def _finding_payload(finding: Any) -> Mapping[str, Any]:
    payload = finding.payload if hasattr(finding, "payload") else finding
    if not isinstance(payload, Mapping):
        raise InsightDigestError("finding pack payload must be an object")
    return payload


def _evidence_refs(observation: Mapping[str, Any]) -> list[str]:
    refs: set[str] = set()
    anchor = observation.get("anchor")
    if (
        isinstance(anchor, Mapping)
        and isinstance(anchor.get("ref"), str)
        and anchor["ref"].strip()
    ):
        refs.add(anchor["ref"])
    anchors = observation.get("anchors", ())
    if isinstance(anchors, Sequence) and not isinstance(anchors, (str, bytes)):
        for item in anchors:
            if not isinstance(item, Mapping):
                continue
            digest = item.get("artifact_digest")
            revision = item.get("artifact_revision")
            if isinstance(digest, str) and digest and isinstance(revision, int):
                refs.add(f"evidence:{digest}@{revision}")
    return sorted(refs)


def build_insight_digest(
    finding_packs: Sequence[Any], *, digest_id: str, producer_version: str,
    active_slot_ids: Sequence[str], previous_digest_ref: str | None = None,
    change_reason: str = "new_finding_batch",
) -> dict[str, Any]:
    """Build the canonical, deterministic InsightDigest from immutable findings."""
    if not digest_id or not producer_version:
        raise InsightDigestError("digest_id and producer_version are required")
    normalized: list[tuple[str, Mapping[str, Any]]] = []
    for finding in finding_packs:
        payload = _finding_payload(finding)
        identifier = str(
            payload.get(
                "id",
                payload.get("finding_id", getattr(finding, "id", "")),
            )
        ).strip()
        if not identifier:
            raise InsightDigestError("finding pack id is required")
        normalized.append((identifier, payload))
    normalized.sort(key=lambda item: item[0])
    statements: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    source_refs: set[str] = set()
    slot_refs = sorted(set(str(item) for item in active_slot_ids))
    option_effects: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for finding_id, payload in normalized:
        slot_id = str(payload.get("decision_slot_id", ""))
        if slot_id and slot_id not in slot_refs:
            continue
        for observation_index, observation in enumerate(payload.get("observations", ())):
            if not isinstance(observation, Mapping):
                continue
            text = str(observation.get("claim", observation.get("text", ""))).strip()
            if not text:
                continue
            evidence_refs = _evidence_refs(observation)
            source_refs.update(evidence_refs)
            statement_class = str(observation.get("class", "fact" if evidence_refs else "unknown"))
            if statement_class not in CANONICAL_STATEMENT_CLASSES:
                raise InsightDigestError(f"unsupported statement class: {statement_class}")
            if statement_class == "fact" and not evidence_refs:
                raise InsightDigestError("fact requires a resolvable evidence anchor")
            if statement_class == "inference" and (not observation.get("assumptions") or not evidence_refs):
                raise InsightDigestError("inference requires assumptions and supporting evidence")
            if statement_class == "recommendation" and (not observation.get("consequence") or not observation.get("reversal_condition")):
                raise InsightDigestError("recommendation requires consequence and reversal condition")
            unknown_reason = observation.get("reason", observation.get("unknown_reason"))
            if statement_class == "unknown" and (not unknown_reason or not observation.get("next_acquisition_method")):
                raise InsightDigestError("unknown requires reason and next acquisition method")
            statements.append({"id": f"{finding_id}-statement-{observation_index}", "class": statement_class, "text": text, "evidence_refs": sorted(evidence_refs), "confidence": str(observation.get("confidence", "medium"))})
        for effect in payload.get("option_effects", ()):
            if isinstance(effect, Mapping) and isinstance(effect.get("option"), str) and isinstance(effect.get("effect"), str):
                option_effects[(slot_id, effect["option"])][effect["effect"]].add(finding_id)
        for uncertainty in payload.get("remaining_uncertainties", ()):
            if isinstance(uncertainty, Mapping):
                reason = str(uncertainty.get("statement", "")).strip()
                next_method = str(uncertainty.get("next_method", "")).strip()
            else:
                reason = str(uncertainty).strip()
                next_method = "validation"
            if reason:
                gaps.append(
                    {
                        "slot_id": slot_id,
                        "reason": reason,
                        "next_acquisition_method": next_method or "validation",
                    }
                )
    for (slot_id, option), effects in sorted(option_effects.items()):
        if {"supports", "contradicts"} <= set(effects):
            contradictions.append({"slot_id": slot_id, "subject": option, "evidence_refs": sorted({ref for refs in effects.values() for ref in refs}), "resolution_action": "adversarial"})
    recommended_actions = []
    for gap in gaps:
        recommended_actions.append({"slot_id": gap["slot_id"], "action": gap["next_acquisition_method"], "trigger": gap["reason"]})
    for contradiction in contradictions:
        recommended_actions.append({"slot_id": contradiction["slot_id"], "action": contradiction["resolution_action"], "trigger": "contradictory option effects"})
    body = {"digest_id": digest_id, "producer_version": producer_version, "source_refs": sorted(source_refs), "slot_refs": slot_refs, "statements": sorted(statements, key=lambda item: item["id"]), "contradictions": contradictions, "gaps": gaps, "recommended_actions": recommended_actions, "limitations": [], "previous_digest_ref": previous_digest_ref, "changed_fields": sorted({"statements" if statements else "", "contradictions" if contradictions else "", "gaps" if gaps else ""} - {""}), "change_reason": change_reason, "invalidates": []}
    body["digest"] = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    return body


def validate_canonical_insight_digest(value: Mapping[str, Any]) -> None:
    required = {"digest_id", "producer_version", "source_refs", "slot_refs", "statements", "contradictions", "gaps", "recommended_actions", "limitations", "previous_digest_ref"}
    if not required <= set(value):
        raise InsightDigestError(f"canonical InsightDigest is missing {sorted(required - set(value))}")
    if not isinstance(value["statements"], list):
        raise InsightDigestError("statements must be an array")
    for statement in value["statements"]:
        if not isinstance(statement, Mapping) or not {"id", "class", "text", "evidence_refs", "confidence"} <= set(statement):
            raise InsightDigestError("statement fields are incomplete")
        if statement["class"] not in CANONICAL_STATEMENT_CLASSES:
            raise InsightDigestError("unsupported statement class")
        if statement["class"] == "fact" and not statement["evidence_refs"]:
            raise InsightDigestError("fact cannot be evidence-free")


def synthesize_insights(
    finding_packs: Sequence[Any],
    *,
    active_slot_ids: Sequence[str],
) -> dict[str, Any]:
    """Turn independent Finding Packs into gaps, conflicts, and next work.

    This is deliberately a structured synthesis pass.  It does not select an
    option or turn an insight into a decision; the Decision Ledger remains the
    only authority for that transition.
    """

    by_slot: dict[str, list[Any]] = defaultdict(list)
    for finding in finding_packs:
        payload = finding.payload if hasattr(finding, "payload") else finding
        if not isinstance(payload, Mapping):
            continue
        slot_id = payload.get("decision_slot_id")
        if isinstance(slot_id, str) and slot_id in active_slot_ids:
            by_slot[slot_id].append(finding)

    insights: list[dict[str, Any]] = []
    next_actions: list[dict[str, str]] = []
    for slot_id in sorted(active_slot_ids):
        findings = by_slot.get(slot_id, [])
        claims: dict[str, list[str]] = defaultdict(list)
        effects: dict[str, set[str]] = defaultdict(set)
        anchors: set[str] = set()
        uncertainties: list[str] = []
        finding_ids: list[str] = []
        for finding in findings:
            payload = finding.payload if hasattr(finding, "payload") else finding
            finding_id = str(
                payload.get(
                    "id",
                    payload.get("finding_id", getattr(finding, "id", "unknown")),
                )
            )
            finding_ids.append(finding_id)
            for observation in payload.get("observations", ()):
                if not isinstance(observation, Mapping):
                    continue
                claim = str(observation.get("claim", "")).strip()
                if claim:
                    claims[claim].append(finding_id)
                anchors.update(_evidence_refs(observation))
            for effect in payload.get("option_effects", ()):
                if isinstance(effect, Mapping):
                    option, value = effect.get("option"), effect.get("effect")
                    if isinstance(option, str) and isinstance(value, str):
                        effects[option].add(value)
            for item in payload.get("remaining_uncertainties", ()):
                uncertainty = (
                    str(item.get("statement", "")).strip()
                    if isinstance(item, Mapping)
                    else str(item).strip()
                )
                if uncertainty:
                    uncertainties.append(uncertainty)

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

    return {
        "insights": insights,
        "next_actions": next_actions,
        "closure": "blocked_by_uncovered_or_contested_slots"
        if any(item["signal"] in {"uncovered", "contested", "thin", "qualified"} for item in insights)
        else "ready_for_decision_ledger_review",
        "finding_pack_count": len(finding_packs),
    }


def validate_insight_digest(value: Mapping[str, Any]) -> None:
    required = {"insights", "next_actions", "closure", "finding_pack_count"}
    if set(value) != required:
        raise ValueError(
            f"insight digest has unexpected keys; missing={sorted(required - set(value))}, "
            f"extra={sorted(set(value) - required)}"
        )
    if value.get("closure") not in {"blocked_by_uncovered_or_contested_slots", "ready_for_decision_ledger_review"}:
        raise ValueError("insight digest closure is unsupported")
    if isinstance(value.get("finding_pack_count"), bool) or not isinstance(value.get("finding_pack_count"), int):
        raise ValueError("insight digest finding_pack_count must be an integer")
