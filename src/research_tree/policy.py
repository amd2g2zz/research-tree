"""Deterministic, host-neutral research policy projections.

The policy only reads normalized inputs and returns value objects. It never
dispatches work or persists a lifecycle transition; those operations belong to
the run coordinator.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields, is_dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

POLICY_PROPOSAL_KINDS = (
    "landscape",
    "deep_dive",
    "adversarial",
    "validation",
    "method_switch",
)
POLICY_DISPOSITIONS = ("selected", "deferred", "rejected")
_PRIORITY_WEIGHT = {"P0": 1.0, "P1": 0.75, "P2": 0.5, "P3": 0.25}


@dataclass(frozen=True, slots=True)
class PolicyConfiguration:
    version: str = "policy-v1"
    max_frontier: int = 8
    weights: Mapping[str, float] = field(
        default_factory=lambda: MappingProxyType(
            {
                "criticality": 0.30,
                "expected_delta": 0.30,
                "method_fit": 0.20,
                "depth_penalty": 0.05,
                "duplicate_penalty": 0.05,
                "stagnation_penalty": 0.10,
            }
        )
    )
    gain_ratio_epsilon: float = 0.05

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("policy version must be a non-empty string")
        if isinstance(self.max_frontier, bool) or self.max_frontier < 1:
            raise ValueError("max_frontier must be positive")
        normalized = {str(key): float(value) for key, value in dict(self.weights).items() if str(key).strip()}
        if any(value < 0 for value in normalized.values()):
            raise ValueError("policy weights must be non-negative")
        if not normalized:
            raise ValueError("policy weights must not be empty")
        object.__setattr__(self, "weights", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class DecisionSlotDeficit:
    slot_id: str
    question: str
    priority: str = "P1"
    missing_dimensions: tuple[str, ...] = ()
    closure_oracle: str = ""
    evidence_refs: tuple[str, ...] = ()
    required_validation: bool = False
    counterevidence_required: bool = False
    contradiction_present: bool = False
    depth: int = 0

    def __post_init__(self) -> None:
        if not self.slot_id.strip():
            raise ValueError("slot_id must be non-empty")
        if not self.question.strip():
            raise ValueError("question must be non-empty")
        if self.priority not in _PRIORITY_WEIGHT:
            raise ValueError("priority must be one of P0, P1, P2, P3")
        if not self.closure_oracle.strip():
            raise ValueError("closure_oracle must be non-empty")
        if self.depth < 0:
            raise ValueError("depth must be non-negative")
        object.__setattr__(self, "missing_dimensions", _strings(self.missing_dimensions))
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs))

    @classmethod
    def from_value(cls, value: "DecisionSlotDeficit | Mapping[str, Any]") -> "DecisionSlotDeficit":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("Decision Slot deficit must be a mapping")
        if not value.get("closure_oracle"):
            raise ValueError("closure_oracle is required for a Decision Slot deficit")
        return cls(
            slot_id=str(value.get("slot_id", "")),
            question=str(value.get("question", "")),
            priority=str(value.get("priority", "P1")),
            missing_dimensions=tuple(value.get("missing_dimensions", ())),
            closure_oracle=str(value.get("closure_oracle", "")),
            evidence_refs=tuple(value.get("evidence_refs", ())),
            required_validation=bool(value.get("required_validation", False)),
            counterevidence_required=bool(value.get("counterevidence_required", False)),
            contradiction_present=bool(value.get("contradiction_present", False)),
            depth=int(value.get("depth", 0)),
        )


@dataclass(frozen=True, slots=True)
class VerifiedEvidence:
    evidence_id: str
    slot_id: str
    evidence_classes: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    verified: bool = True
    contradiction: bool = False
    oracle_status: str = ""
    uncertainty_refs: tuple[str, ...] = ()
    closure_status: str = ""
    method_boundary: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.slot_id.strip():
            raise ValueError("verified evidence requires evidence_id and slot_id")
        object.__setattr__(self, "evidence_classes", _strings(self.evidence_classes))
        object.__setattr__(self, "provenance_refs", _strings(self.provenance_refs))
        object.__setattr__(self, "uncertainty_refs", _strings(self.uncertainty_refs))

    @classmethod
    def from_value(cls, value: "VerifiedEvidence | Mapping[str, Any]") -> "VerifiedEvidence":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("verified evidence must be a mapping")
        return cls(
            evidence_id=str(value.get("evidence_id", value.get("id", ""))),
            slot_id=str(value.get("slot_id", value.get("decision_slot_id", ""))),
            evidence_classes=tuple(value.get("evidence_classes", value.get("classes", ()))),
            provenance_refs=tuple(value.get("provenance_refs", value.get("provenance", ()))),
            verified=bool(value.get("verified", True)),
            contradiction=bool(value.get("contradiction", False)),
            oracle_status=str(value.get("oracle_status", "")),
            uncertainty_refs=tuple(value.get("uncertainty_refs", ())),
            closure_status=str(value.get("closure_status", "")),
            method_boundary=str(value.get("method_boundary", "")),
        )


@dataclass(frozen=True, slots=True)
class InsightSignal:
    slot_id: str
    signal: str
    source_refs: tuple[str, ...] = ()
    gap_refs: tuple[str, ...] = ()
    mandatory: bool = False
    contradiction: bool = False
    failed_oracle: bool = False
    method_limitation: bool = False
    invalid_premise: bool = False

    def __post_init__(self) -> None:
        if not self.slot_id.strip() or not self.signal.strip():
            raise ValueError("Insight Signal requires slot_id and signal")
        object.__setattr__(self, "source_refs", _strings(self.source_refs))
        object.__setattr__(self, "gap_refs", _strings(self.gap_refs))

    @classmethod
    def from_value(cls, value: "InsightSignal | Mapping[str, Any]") -> "InsightSignal":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("Insight Signal must be a mapping")
        return cls(
            slot_id=str(value.get("slot_id", value.get("decision_slot_id", ""))),
            signal=str(value.get("signal", "")),
            source_refs=tuple(value.get("source_refs", value.get("evidence_refs", ()))),
            gap_refs=tuple(value.get("gap_refs", value.get("gaps", ()))),
            mandatory=bool(value.get("mandatory", False)),
            contradiction=bool(value.get("contradiction", value.get("signal") == "contested")),
            failed_oracle=bool(value.get("failed_oracle", False)),
            method_limitation=bool(value.get("method_limitation", False)),
            invalid_premise=bool(value.get("invalid_premise", False)),
        )


@dataclass(frozen=True, slots=True)
class PolicyProposal:
    action_id: str
    kind: str
    slot_id: str
    question: str
    trigger_refs: tuple[str, ...]
    missing_dimensions: tuple[str, ...]
    method_boundary: str
    closure_oracle: str
    score_components: Mapping[str, float]
    score: float
    tie_break: str
    causal_refs: tuple[str, ...]
    mandatory: bool = False
    parent_action_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in POLICY_PROPOSAL_KINDS:
            raise ValueError(f"unsupported policy proposal kind: {self.kind}")
        if not self.trigger_refs or not self.causal_refs:
            raise ValueError("policy proposal must retain trigger and causal references")
        object.__setattr__(self, "trigger_refs", _strings(self.trigger_refs))
        object.__setattr__(self, "missing_dimensions", _strings(self.missing_dimensions))
        object.__setattr__(self, "causal_refs", _strings(self.causal_refs))
        object.__setattr__(self, "score_components", MappingProxyType(dict(self.score_components)))


@dataclass(frozen=True, slots=True)
class PolicyDisposition:
    action_id: str
    disposition: str
    reason: str
    causal_refs: tuple[str, ...] = ()
    retained_action_id: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in POLICY_DISPOSITIONS:
            raise ValueError(f"unsupported policy disposition: {self.disposition}")
        object.__setattr__(self, "causal_refs", _strings(self.causal_refs))


@dataclass(frozen=True, slots=True)
class PolicyTrace:
    policy_version: str
    seed: int
    canonical_input_digest: str
    normalized_inputs: Mapping[str, Any]
    tie_break_order: tuple[str, ...]
    selected_ids: tuple[str, ...]
    deferred_ids: tuple[str, ...]

    @property
    def authority(self) -> str:
        return "coordinator_only"


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    proposals: tuple[PolicyProposal, ...]
    dispositions: tuple[PolicyDisposition, ...]
    trace: PolicyTrace


class AdaptiveResearchPolicy:
    """Pure deterministic selection over verified research deficits."""

    def __init__(
        self,
        configuration: PolicyConfiguration | None = None,
        *,
        seed: int = 0,
    ) -> None:
        self.configuration = configuration or PolicyConfiguration()
        if isinstance(seed, bool):
            raise ValueError("policy seed must be an integer")
        self.seed = int(seed)

    def evaluate(
        self,
        *,
        slots: Sequence[DecisionSlotDeficit | Mapping[str, Any]],
        evidence: Sequence[VerifiedEvidence | Mapping[str, Any]] = (),
        signals: Sequence[InsightSignal | Mapping[str, Any]] = (),
        prior_outcomes: Sequence[Mapping[str, Any]] = (),
        worker_suggestions: Sequence[Mapping[str, Any]] = (),
    ) -> PolicyEvaluation:
        normalized_slots = tuple(
            sorted((DecisionSlotDeficit.from_value(value) for value in slots), key=lambda item: item.slot_id)
        )
        slot_ids = {item.slot_id for item in normalized_slots}
        normalized_evidence = tuple(
            sorted(
                (VerifiedEvidence.from_value(value) for value in evidence),
                key=lambda item: (item.slot_id, item.evidence_id),
            )
        )
        normalized_signals = tuple(
            sorted(
                (InsightSignal.from_value(value) for value in signals),
                key=lambda item: (item.slot_id, item.signal, item.source_refs),
            )
        )
        normalized_outcomes = tuple(sorted(_canonical(item) for item in prior_outcomes))
        normalized_inputs = {
            "slots": [item.to_dict() for item in normalized_slots],
            "evidence": [item.to_dict() for item in normalized_evidence],
            "signals": [item.to_dict() for item in normalized_signals],
            "prior_outcomes": list(normalized_outcomes),
        }
        input_digest = _digest(normalized_inputs)
        verified_refs = {item.evidence_id for item in normalized_evidence if item.verified} | {
            ref for item in normalized_evidence if item.verified for ref in item.provenance_refs
        }
        signal_by_slot: dict[str, list[InsightSignal]] = {}
        for signal in normalized_signals:
            signal_by_slot.setdefault(signal.slot_id, []).append(signal)
        proposals: list[PolicyProposal] = []
        dispositions: list[PolicyDisposition] = []
        blocked_slots: set[str] = set()
        for suggestion in worker_suggestions:
            slot_id = str(suggestion.get("slot_id", ""))
            trigger_refs = _strings(suggestion.get("trigger_refs", suggestion.get("evidence_refs", ())))
            if slot_id not in slot_ids or not trigger_refs or not set(trigger_refs) & verified_refs:
                blocked_slots.add(slot_id)
        for slot_deficit in normalized_slots:
            if slot_deficit.slot_id in blocked_slots:
                continue
            slot_evidence = tuple(
                item for item in normalized_evidence if item.slot_id == slot_deficit.slot_id and item.verified
            )
            slot_signals = tuple(signal_by_slot.get(slot_deficit.slot_id, ()))
            proposal = self._proposal_for_slot(
                slot_deficit,
                slot_evidence,
                slot_signals,
                input_digest,
            )
            if proposal is not None:
                proposals.append(proposal)
        for suggestion in worker_suggestions:
            action_id = str(suggestion.get("action_id", "worker-suggestion"))
            slot_id = str(suggestion.get("slot_id", ""))
            trigger_refs = _strings(suggestion.get("trigger_refs", suggestion.get("evidence_refs", ())))
            if slot_id not in slot_ids or not trigger_refs or not set(trigger_refs) & verified_refs:
                dispositions.append(
                    PolicyDisposition(
                        action_id=action_id,
                        disposition="rejected",
                        reason="missing_verified_trigger",
                        causal_refs=trigger_refs or ((f"slot:{slot_id}",) if slot_id else ()),
                    )
                )
        ranked = sorted(
            proposals,
            key=lambda item: (-int(item.mandatory), -item.score, item.tie_break, item.action_id),
        )
        selected: list[PolicyProposal] = []
        deferred: list[PolicyDisposition] = []
        retained_keys: dict[tuple[str, str, str, str], PolicyProposal] = {}
        for proposal in ranked:
            key = (proposal.slot_id, proposal.question, proposal.kind, proposal.closure_oracle)
            retained = retained_keys.get(key)
            if retained is not None:
                deferred.append(
                    PolicyDisposition(
                        action_id=proposal.action_id,
                        disposition="deferred",
                        reason="duplicate_or_dominated",
                        causal_refs=proposal.causal_refs,
                        retained_action_id=retained.action_id,
                    )
                )
                continue
            if len(selected) >= self.configuration.max_frontier and not proposal.mandatory:
                deferred.append(
                    PolicyDisposition(
                        action_id=proposal.action_id,
                        disposition="deferred",
                        reason="frontier_capacity",
                        causal_refs=proposal.causal_refs,
                    )
                )
                continue
            retained_keys[key] = proposal
            selected.append(proposal)
        dispositions.extend(
            PolicyDisposition(
                action_id=item.action_id,
                disposition="selected",
                reason="retained_by_policy",
                causal_refs=item.causal_refs,
            )
            for item in selected
        )
        dispositions.extend(deferred)
        dispositions.sort(key=lambda item: (item.action_id, item.disposition, item.reason))
        trace = PolicyTrace(
            policy_version=self.configuration.version,
            seed=self.seed,
            canonical_input_digest=input_digest,
            normalized_inputs=MappingProxyType(normalized_inputs),
            tie_break_order=tuple(item.action_id for item in ranked),
            selected_ids=tuple(item.action_id for item in selected),
            deferred_ids=tuple(item.action_id for item in deferred),
        )
        return PolicyEvaluation(tuple(selected), tuple(dispositions), trace)

    def _proposal_for_slot(
        self,
        slot: DecisionSlotDeficit,
        evidence: Sequence[VerifiedEvidence],
        signals: Sequence[InsightSignal],
        input_digest: str,
    ) -> PolicyProposal | None:
        signal_names = {item.signal for item in signals}
        missing = set(slot.missing_dimensions)
        if slot.required_validation or "qualified" in signal_names or any(item.failed_oracle for item in signals):
            kind = "validation"
            method_boundary = "execute the registered closure oracle in an isolated validation method"
        elif (
            slot.counterevidence_required
            or slot.contradiction_present
            or "contested" in signal_names
            or any(item.contradiction for item in signals)
        ):
            kind = "adversarial"
            method_boundary = "acquire independent counterevidence from a distinct provenance group"
        elif any(item.method_limitation for item in signals) or "method_switch" in missing:
            kind = "method_switch"
            method_boundary = "switch acquisition or verification method without changing the Slot question"
        elif not evidence or "evidence_class_coverage" in missing or "uncovered" in signal_names:
            kind = "landscape"
            method_boundary = "map the open Slot across the required evidence classes"
        else:
            kind = "deep_dive"
            method_boundary = "deepen the highest-impact unresolved dimension"
        trigger_refs = tuple(
            sorted(
                set(slot.evidence_refs)
                | {f"deficit:{slot.slot_id}"}
                | {ref for signal in signals for ref in signal.source_refs}
            )
        )
        causal_refs = tuple(
            sorted(set(trigger_refs) | {f"signal:{slot.slot_id}:{signal.signal}" for signal in signals})
        )
        mandatory = (
            slot.priority == "P0"
            or slot.required_validation
            or slot.counterevidence_required
            or slot.contradiction_present
            or any(item.mandatory for item in signals)
        )
        criticality = _PRIORITY_WEIGHT[slot.priority]
        expected_delta = min(1.0, max(0.2, len(missing) / 3))
        method_fit = 1.0 if evidence else 0.75
        depth_penalty = min(1.0, slot.depth / 4)
        stagnation_penalty = (
            1.0 if any(signal.signal in {"thin", "uncovered"} for signal in signals) and evidence else 0.0
        )
        weights = self.configuration.weights
        score_components = {
            "criticality": criticality,
            "expected_delta": expected_delta,
            "method_fit": method_fit,
            "depth_penalty": depth_penalty,
            "duplicate_penalty": 0.0,
            "stagnation_penalty": stagnation_penalty,
        }
        score = max(
            0.0,
            round(
                sum(float(weights.get(name, 0.0)) * value for name, value in score_components.items()),
                6,
            ),
        )
        action_seed = {
            "policy_version": self.configuration.version,
            "input_digest": input_digest,
            "seed": self.seed,
            "slot": slot.to_dict(),
            "kind": kind,
            "trigger_refs": trigger_refs,
        }
        action_id = f"action-{_digest(action_seed)[:16]}"
        tie_break = _digest({**action_seed, "tie": True})[:16]
        return PolicyProposal(
            action_id=action_id,
            kind=kind,
            slot_id=slot.slot_id,
            question=slot.question,
            trigger_refs=trigger_refs,
            missing_dimensions=tuple(sorted(missing)),
            method_boundary=method_boundary,
            closure_oracle=slot.closure_oracle,
            score_components=score_components,
            score=score,
            tie_break=tie_break,
            causal_refs=causal_refs,
            mandatory=mandatory,
        )

    def select(self, **kwargs: Any) -> PolicyEvaluation:
        return self.evaluate(**kwargs)

    def calibrate(self, **changes: Any) -> "AdaptiveResearchPolicy":
        config_data = self.configuration.to_dict()
        config_data.update(changes)
        if "version" not in changes:
            config_data["version"] = f"{self.configuration.version}-calibrated"
        return AdaptiveResearchPolicy(PolicyConfiguration(**config_data), seed=self.seed)


AdaptivePolicy = AdaptiveResearchPolicy
ResearchActionProposal = PolicyProposal


def _model_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {item.name: _model_dict(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _model_dict(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_model_dict(item) for item in value]
    return value


def _trace_dict(value: PolicyTrace) -> dict[str, Any]:
    return {**_model_dict(value), "authority": value.authority}


for _model in (
    PolicyConfiguration,
    DecisionSlotDeficit,
    VerifiedEvidence,
    InsightSignal,
    PolicyProposal,
    PolicyDisposition,
    PolicyEvaluation,
):
    _model.to_dict = _model_dict
PolicyTrace.to_dict = _trace_dict


def _strings(value: Sequence[Any]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("value must be a sequence of strings")
    return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_canonical(item) for item in sorted(value, key=lambda item: repr(item))]
    if hasattr(value, "to_dict"):
        return _canonical(value.to_dict())
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(_canonical(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "AdaptivePolicy",
    "AdaptiveResearchPolicy",
    "DecisionSlotDeficit",
    "InsightSignal",
    "POLICY_DISPOSITIONS",
    "POLICY_PROPOSAL_KINDS",
    "PolicyConfiguration",
    "PolicyDisposition",
    "PolicyEvaluation",
    "PolicyProposal",
    "PolicyTrace",
    "ResearchActionProposal",
    "VerifiedEvidence",
]
