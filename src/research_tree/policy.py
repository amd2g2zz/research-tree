"""Deterministic adaptive research policy over current decision deficits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .evidence_delta import EvidenceBaseline, measure_realized_delta


DEFAULT_WEIGHTS = {
    "evidence_class": 0.18, "independence": 0.14, "contradiction": 0.18,
    "oracle": 0.20, "implementation_uncertainty": 0.12, "decision_closure": 0.18,
}


@dataclass(frozen=True, slots=True)
class AdaptiveResearchPolicy:
    """Rank actions, grow only from explicit gaps, and prune optional duplicates."""

    weights: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    gain_ratio_epsilon: float = 0.05

    def feature_vector(self, candidate: Mapping[str, Any]) -> dict[str, float]:
        values = {
            key: float(candidate.get(key, 0.0))
            for key in self.weights
        }
        return {key: max(0.0, min(1.0, value)) for key, value in values.items()}

    def score(self, candidate: Mapping[str, Any]) -> float:
        vector = self.feature_vector(candidate)
        return round(sum(self.weights[key] * vector[key] for key in self.weights), 6)

    def propose(
        self, *, slots: Mapping[str, Mapping[str, Any]], findings: Sequence[Mapping[str, Any]],
    ) -> tuple[dict[str, Any], ...]:
        """Create one current action per unresolved slot; no fixed wave count."""

        covered = {str(item.get("decision_slot_id")) for item in findings}
        actions: list[dict[str, Any]] = []
        for slot_id, slot in slots.items():
            if str(slot.get("status", "open")) in {"closed", "superseded"}:
                continue
            priority = str(slot.get("priority", "P1"))
            candidate = {
                "slot_id": slot_id,
                "action_id": f"action-{slot_id}",
                "action_kind": "validation" if priority == "P0" else ("deep_dive" if slot_id in covered else "landscape"),
                "question": str(slot.get("question", slot_id)),
                "priority": priority,
                "evidence_class": 0.9 if slot_id not in covered else 0.4,
                "independence": 0.8 if slot_id not in covered else 0.3,
                "contradiction": float(slot.get("contradiction", 0.0)),
                "oracle": float(slot.get("oracle", 0.8 if priority == "P0" else 0.4)),
                "implementation_uncertainty": float(slot.get("implementation_uncertainty", 0.7)),
                "decision_closure": 1.0 - float(slot.get("closure", 0.0)),
                "status": "proposed",
            }
            candidate["selection_value"] = self.score(candidate)
            actions.append(candidate)
        rank = {"P0": 0, "P1": 1, "P2": 2}
        return tuple(sorted(actions, key=lambda item: (rank.get(str(item["priority"]), 9), -item["selection_value"], item["slot_id"])))

    def apply(
        self,
        slots: Mapping[str, Mapping[str, Any]],
        findings: Sequence[Mapping[str, Any]],
        *,
        baseline: EvidenceBaseline | Mapping[str, Any] | None = None,
        transition_index: int = 1,
    ) -> dict[str, Any]:
        """Measure one policy transition against the persisted evidence baseline."""

        if baseline is None:
            current = EvidenceBaseline()
        elif isinstance(baseline, EvidenceBaseline):
            current = baseline
        elif isinstance(baseline, Mapping):
            current = EvidenceBaseline.from_dict(baseline)
        else:
            raise TypeError("baseline must be EvidenceBaseline, mapping, or None")
        delta, updated = measure_realized_delta(
            current, findings, transition_index=transition_index
        )
        continuations = [
            continuation
            for finding in findings
            for continuation in finding.get("research_continuations", ())
            if isinstance(continuation, Mapping)
        ]
        growth = [
            {"slot_id": str(finding.get("decision_slot_id")), "action_kind": str(item.get("kind", "deep_dive")), "question": str(item.get("question", "")), "status": "proposed"}
            for finding in findings for item in finding.get("research_continuations", ())
            if isinstance(item, Mapping) and str(item.get("question", "")).strip()
        ]
        growth.extend(
            {"slot_id": str(finding.get("decision_slot_id")), "action_kind": "validation", "question": str(uncertainty), "status": "proposed"}
            for finding in findings
            for uncertainty in finding.get("remaining_uncertainties", ())
            if str(uncertainty).strip()
        )
        return {
            "realized_delta": {**delta, "baseline_zero": delta["realized_delta"] == 0.0},
            "baseline": updated.to_dict(),
            "transition_index": transition_index,
            "policy_version": 1,
            "actions": list(self.propose(slots=slots, findings=findings)) + growth,
            "growth": growth,
            "continuation_count": len(continuations),
        }

    def prune(self, actions: Sequence[Mapping[str, Any]], *, protected_slots: set[str] | None = None) -> tuple[dict[str, Any], ...]:
        protected = set(protected_slots or ())
        seen: set[tuple[str, str]] = set()
        result: list[dict[str, Any]] = []
        for action in actions:
            item = dict(action)
            key = (str(item.get("slot_id")), str(item.get("question", "")).strip().casefold())
            priority = str(item.get("priority", "P1"))
            if key in seen and str(item.get("slot_id")) not in protected and priority != "P0":
                item["status"] = "pruned"
                item["prune_reason"] = "duplicate_optional_action"
            else:
                seen.add(key)
            result.append(item)
        return tuple(result)
