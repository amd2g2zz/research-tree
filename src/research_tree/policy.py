"""Deterministic adaptive research policy over current decision deficits."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
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
    policy_version: int = 2
    policy_seed: int = 0
    oracle_failure_boost: float = 0.35

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

    def propose_from_deficits(
        self,
        *,
        run_id: str,
        deficits: Sequence[Mapping[str, Any]],
        slot_priorities: Mapping[str, str] | None = None,
        policy_seed: int | None = None,
        policy_version: int | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Translate canonical deficits into bounded, reproducible action proposals.

        This is deliberately a pure projection: it does not mutate the Slot or
        register work. The coordinator owns persistence and lifecycle changes.
        """

        if not str(run_id).strip():
            raise ValueError("run_id is required")
        seed = self.policy_seed if policy_seed is None else int(policy_seed)
        version = self.policy_version if policy_version is None else int(policy_version)
        priorities = slot_priorities or {}
        allowed = {"landscape", "deep_dive", "adversarial", "validation", "method_switch"}
        proposals: list[dict[str, Any]] = []
        for deficit in deficits:
            if not isinstance(deficit, Mapping):
                raise TypeError("deficits must contain mappings")
            slot_id = str(deficit.get("slot_id", "")).strip()
            trigger = str(deficit.get("trigger", deficit.get("reason", ""))).strip()
            trigger_refs = _string_list(deficit.get("source_refs", deficit.get("trigger_refs", ())))
            if not slot_id or not trigger_refs:
                raise ValueError("each deficit requires slot_id and source_refs")
            action_kind = str(deficit.get("action", deficit.get("action_kind", "deep_dive")))
            if action_kind not in allowed:
                action_kind = "deep_dive"
            priority = str(priorities.get(slot_id, deficit.get("priority", "P1")))
            missing = _string_list(deficit.get("required_evidence_classes", deficit.get("missing_evidence", ())))
            oracle = str(deficit.get("closure_oracle", deficit.get("oracle", ""))).strip()
            if not missing or not oracle:
                raise ValueError("each deficit requires missing evidence and closure_oracle")
            method_boundary = deficit.get("method_boundary", _default_method_boundary(action_kind))
            score_components = _deficit_components(deficit, priority, missing)
            mandatory = bool(deficit.get("mandatory", False)) or priority == "P0" or action_kind == "validation" and str(deficit.get("kind", "")) in {"closure_missing", "validation_pending"}
            identity = {
                "run_id": str(run_id), "slot_id": slot_id,
                "deficit_id": str(deficit.get("deficit_id", "")),
                "action_kind": action_kind, "trigger_refs": trigger_refs,
                "seed": seed, "version": version,
            }
            action_id = "action-" + hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:16]
            candidate = {
                "action_id": action_id,
                "run_id": str(run_id),
                "slot_id": slot_id,
                "action_kind": action_kind,
                "objective": trigger or f"Resolve deficit {deficit.get('deficit_id', slot_id)}",
                "trigger_refs": trigger_refs,
                "missing_evidence": missing,
                "method_boundary": method_boundary,
                "closure_oracle": oracle,
                "mandatory": mandatory,
                "priority": priority,
                "policy_version": version,
                "policy_seed": seed,
                "score_components": score_components,
                **score_components,
                "expected_gain": float(deficit.get("expected_gain", self.score(score_components))),
                "estimated_cost": max(float(deficit.get("estimated_cost", 1.0)), self.gain_ratio_epsilon),
                "status": "proposed",
            }
            candidate["selection_value"] = self.score(candidate)
            candidate["gain_ratio"] = round(candidate["expected_gain"] / candidate["estimated_cost"], 6)
            proposals.append(candidate)
        rank = {"P0": 0, "P1": 1, "P2": 2}
        return tuple(sorted(proposals, key=lambda item: (rank.get(str(item["priority"]), 9), -item["selection_value"], item["action_id"])))

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
        growth: list[dict[str, Any]] = []
        for finding in findings:
            slot_id = str(finding.get("decision_slot_id"))
            slot = slots.get(slot_id, {})
            priority = str(slot.get("priority", "P1"))
            finding_id = str(finding.get("id", "unknown-finding"))
            for item in finding.get("research_continuations", ()):
                if not isinstance(item, Mapping):
                    continue
                question = str(item.get("question", "")).strip()
                if not question:
                    continue
                growth.append(
                    self._growth_action(
                        slot_id=slot_id,
                        priority=priority,
                        action_kind=str(item.get("kind", "deep_dive")),
                        question=question,
                        trigger=f"finding:{finding_id}",
                        evidence_needed=str(item.get("evidence_needed", "Decision-relevant evidence with provenance.")),
                        oracle=str(item.get("oracle", "The successor question is answered with anchored evidence.")),
                        estimated_cost=item.get("estimated_cost", 1.0),
                    )
                )
            for uncertainty in finding.get("remaining_uncertainties", ()):
                question = str(uncertainty).strip()
                if not question:
                    continue
                growth.append(
                    self._growth_action(
                        slot_id=slot_id,
                        priority=priority,
                        action_kind="validation",
                        question=question,
                        trigger=f"finding:{finding_id}:uncertainty",
                        evidence_needed="Evidence that resolves the recorded uncertainty.",
                        oracle="The uncertainty is resolved or explicitly bounded.",
                        estimated_cost=1.0,
                    )
                )
            correction = finding.get("correction")
            if isinstance(correction, Mapping):
                question = str(correction.get("question", "")).strip()
                if question:
                    growth.append(
                        self._growth_action(
                            slot_id=slot_id,
                            priority=priority,
                            action_kind=str(correction.get("kind", "adversarial")),
                            question=question,
                            trigger=f"correction:{finding_id}",
                            evidence_needed=str(correction.get("evidence_needed", "Evidence addressing the corrected premise.")),
                            oracle=str(correction.get("oracle", "The corrected premise is independently resolved.")),
                            estimated_cost=correction.get("estimated_cost", 1.0),
                        )
                    )
            oracle_status = str(finding.get("oracle_status", finding.get("oracle_verdict", ""))).lower()
            if oracle_status in {"failed", "inconclusive", "blocked"} or finding.get("oracle_failure"):
                growth.append(
                    self._growth_action(
                        slot_id=slot_id,
                        priority=priority,
                        action_kind="method_switch",
                        question=f"Recover the failed closure oracle for {finding_id} with an independent method.",
                        trigger=f"oracle-failure:{finding_id}",
                        evidence_needed="An independent oracle attempt and its reproducibility evidence.",
                        oracle="The closure oracle passes or the residual risk is explicitly bounded.",
                        estimated_cost=1.0,
                    )
                )
        proposals = list(self.propose(slots=slots, findings=findings)) + growth
        protected_slots = {
            slot_id
            for slot_id, slot in slots.items()
            if str(slot.get("priority", "P1")) == "P0"
        }
        actions = list(self.prune(proposals, protected_slots=protected_slots))
        return {
            "realized_delta": {**delta, "baseline_zero": delta["realized_delta"] == 0.0},
            "baseline": updated.to_dict(),
            "transition_index": transition_index,
            "policy_version": self.policy_version,
            "actions": actions,
            "growth": growth,
            "continuation_count": len(continuations),
            "pruned_count": sum(1 for item in actions if item.get("status") == "pruned"),
        }

    @staticmethod
    def _growth_action(
        *, slot_id: str, priority: str, action_kind: str, question: str,
        trigger: str, evidence_needed: str, oracle: str, estimated_cost: Any,
    ) -> dict[str, Any]:
        normalized_kind = action_kind if action_kind in {"landscape", "deep_dive", "adversarial", "validation", "method_switch"} else "deep_dive"
        digest = hashlib.sha256(
            f"{slot_id}:{normalized_kind}:{question.casefold()}".encode("utf-8")
        ).hexdigest()[:16]
        try:
            cost = float(estimated_cost)
        except (TypeError, ValueError):
            cost = 1.0
        return {
            "action_id": f"action-{slot_id}-{digest}",
            "slot_id": slot_id,
            "priority": priority,
            "action_kind": normalized_kind,
            "question": question,
            "trigger": trigger,
            "evidence_needed": evidence_needed,
            "oracle": oracle,
            "estimated_cost": cost if cost > 0 else 1.0,
            "status": "proposed",
        }

    def prune(self, actions: Sequence[Mapping[str, Any]], *, protected_slots: set[str] | None = None) -> tuple[dict[str, Any], ...]:
        protected = set(protected_slots or ())
        seen: dict[tuple[str, str, str], dict[str, Any]] = {}
        result: list[dict[str, Any]] = []
        for action in actions:
            item = dict(action)
            item.setdefault("status", "proposed")
            item.setdefault("policy_version", self.policy_version)
            item.setdefault("policy_seed", self.policy_seed)
            try:
                cost = max(float(item.get("estimated_cost", 1.0)), self.gain_ratio_epsilon)
            except (TypeError, ValueError):
                cost = 1.0
            expected_gain = max(0.0, float(item.get("expected_gain", item.get("selection_value", 0.0))))
            item["gain_ratio"] = round(expected_gain / cost, 6)
            failed = bool(item.get("oracle_failure", False))
            item["oracle_failure_boost"] = self.oracle_failure_boost if failed else 0.0
            item["recovery_required"] = failed
            key = (
                str(item.get("slot_id")),
                str(item.get("action_kind", "")),
                str(item.get("question", item.get("objective", ""))).strip().casefold(),
            )
            priority = str(item.get("priority", "P1"))
            mandatory = bool(item.get("mandatory", False)) or priority == "P0" or str(item.get("slot_id")) in protected
            item["mandatory"] = mandatory
            if mandatory:
                item.setdefault("exemption_reason", "mandatory_p0_or_closure_obligation")
            prior = seen.get(key)
            if prior is not None and not mandatory:
                item["status"] = "pruned"
                item["prune_reason"] = "duplicate_optional_action" if item.get("gain_ratio", 0.0) >= prior.get("gain_ratio", 0.0) else "dominated_optional_action"
                item["retained_action_id"] = prior.get("action_id")
            else:
                if prior is None or item.get("gain_ratio", 0.0) > prior.get("gain_ratio", 0.0):
                    seen[key] = item
            result.append(item)
        return tuple(result)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence):
        return []
    return [str(item) for item in value if str(item).strip()]


def _default_method_boundary(action_kind: str) -> dict[str, Any]:
    return {"allowed": [action_kind], "fallback": "method_switch" if action_kind != "method_switch" else "bounded_external_search"}


def _deficit_components(deficit: Mapping[str, Any], priority: str, missing: Sequence[str]) -> dict[str, float]:
    defaults = {
        "evidence_class": min(1.0, len(missing) / 3.0),
        "independence": 0.8 if len(missing) > 1 else 0.4,
        "contradiction": 1.0 if str(deficit.get("kind", "")) in {"contradiction", "contested"} else 0.0,
        "oracle": 1.0 if str(deficit.get("kind", "")) in {"validation_pending", "closure_missing", "oracle_failure"} else 0.6,
        "implementation_uncertainty": 1.0 if str(deficit.get("kind", "")) in {"method_unavailable", "implementation_unknown"} else 0.5,
        "decision_closure": 1.0 if priority == "P0" else 0.7,
    }
    return {key: max(0.0, min(1.0, float(deficit.get(key, value)))) for key, value in defaults.items()}
