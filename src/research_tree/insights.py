"""Cross-worker insight extraction without replacing provenance or decisions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence


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
        anchors: set[tuple[str, str]] = set()
        uncertainties: list[str] = []
        finding_ids: list[str] = []
        for finding in findings:
            payload = finding.payload if hasattr(finding, "payload") else finding
            finding_id = str(payload.get("id", getattr(finding, "id", "unknown")))
            finding_ids.append(finding_id)
            for observation in payload.get("observations", ()):
                if not isinstance(observation, Mapping):
                    continue
                claim = str(observation.get("claim", "")).strip()
                if claim:
                    claims[claim].append(finding_id)
                anchor = observation.get("anchor")
                if isinstance(anchor, Mapping):
                    kind, ref = anchor.get("kind"), anchor.get("ref")
                    if isinstance(kind, str) and isinstance(ref, str):
                        anchors.add((kind, ref))
            for effect in payload.get("option_effects", ()):
                if isinstance(effect, Mapping):
                    option, value = effect.get("option"), effect.get("effect")
                    if isinstance(option, str) and isinstance(value, str):
                        effects[option].add(value)
            uncertainties.extend(
                str(item) for item in payload.get("remaining_uncertainties", ()) if str(item).strip()
            )

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
