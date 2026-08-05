"""Deterministic candidate selection for evidence-bearing mutual alignment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Mapping, Sequence

from .contracts import canonical_json_bytes


class AlignmentStrategyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AlignmentStrategyState:
    belief_digest: str
    pending_action_id: str | None
    unresolved_gaps: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    expected_information_gain: float
    cognitive_load: int
    selected_action_reason: str
    turn: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "unresolved_gaps": list(self.unresolved_gaps),
            "evidence_refs": list(self.evidence_refs),
        }


def select_alignment_action(
    *,
    nodes: Sequence[Mapping[str, Any]],
    readiness: Mapping[str, Any],
    turn: int,
    graph_digest: str,
) -> tuple[dict[str, Any], AlignmentStrategyState]:
    """Score reconnaissance, one question, disagreement, and confirmation."""

    unresolved = [node for node in nodes if node.get("status") in {"candidate", "disputed"}]
    gaps = sorted(
        unresolved,
        key=lambda node: (-int(node.get("impact", 1)), int(node.get("ask_count", 0)), str(node.get("id"))),
    )
    evidence_refs = sorted(
        {
            str(node.get("attributes", {}).get("anchor", {}).get("ref"))
            for node in nodes
            if isinstance(node.get("attributes"), Mapping)
            and isinstance(node.get("attributes", {}).get("anchor"), Mapping)
            and node.get("attributes", {}).get("anchor", {}).get("ref")
        }
    )
    belief_digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "graph_digest": graph_digest,
                "readiness": readiness,
                "gaps": [node.get("id") for node in gaps],
            }
        )
    ).hexdigest()

    candidates: list[dict[str, Any]] = []
    infeasible = next(
        (
            node for node in nodes
            if node.get("type") == "feasibility"
            and (
                node.get("status") == "rejected"
                or (
                    isinstance(node.get("attributes"), Mapping)
                    and node.get("attributes", {}).get("feasibility_status") == "infeasible"
                )
            )
        ),
        None,
    )
    if infeasible is not None:
        candidates.append(
            _candidate(
                action="authority_blocked",
                node=infeasible,
                cognitive_load=len(gaps),
                factors=_factors(
                    impact=1.0, human_exclusivity=1.0, researchability=0.0,
                    ambiguity_reduction=1.0, decision_consequence=1.0,
                    cognitive_load=len(gaps), repetition=0.0,
                ),
                reason="the requested outcome is infeasible under the current authority or resources",
            )
        )
    elif readiness.get("ready"):
        candidates.append(
            _candidate(
                action="await_human_confirmation",
                node=None,
                cognitive_load=len(gaps),
                factors={
                    "impact": 1.0,
                    "human_exclusivity": 1.0,
                    "researchability": 0.0,
                    "ambiguity_reduction": 1.0,
                    "decision_consequence": 1.0,
                    "cognitive_load_penalty": 0.0,
                    "repetition_penalty": 0.0,
                },
                reason="all hard alignment fields are resolved",
            )
        )
    else:
        for node in gaps:
            impact = min(1.0, max(0.0, float(node.get("impact", 1)) / 5.0))
            repetitions = min(1.0, max(0.0, float(node.get("ask_count", 0)) / 2.0))
            human_only = bool(node.get("human_only"))
            disputed = node.get("status") == "disputed" or node.get("type") == "disagreement"
            attributes = node.get("attributes") if isinstance(node.get("attributes"), Mapping) else {}
            if disputed and attributes.get("disagreement_disposition") in {
                "supported", "refuted", "not_enough_information",
            }:
                factors = _factors(
                    impact=impact,
                    human_exclusivity=0.6 if human_only else 0.2,
                    researchability=0.8,
                    ambiguity_reduction=0.8,
                    decision_consequence=impact,
                    cognitive_load=len(gaps),
                    repetition=repetitions,
                )
                candidates.append(
                    _candidate(
                        action="constructive_disagreement",
                        node=node,
                        cognitive_load=len(gaps),
                        factors=factors,
                        reason="supported evidence conflicts with a consequential premise",
                        conflict_boost=0.2,
                    )
                )
            elif human_only:
                factors = _factors(
                    impact=impact,
                    human_exclusivity=1.0,
                    researchability=0.0,
                    ambiguity_reduction=0.75,
                    decision_consequence=impact,
                    cognitive_load=len(gaps),
                    repetition=repetitions,
                )
                candidates.append(
                    _candidate(
                        action="ask_one",
                        node=node,
                        cognitive_load=len(gaps),
                        factors=factors,
                        reason="highest-value requester-owned decision gap",
                    )
                )
            else:
                factors = _factors(
                    impact=impact,
                    human_exclusivity=0.0,
                    researchability=0.9,
                    ambiguity_reduction=1.0,
                    decision_consequence=impact,
                    cognitive_load=len(gaps),
                    repetition=repetitions,
                )
                candidates.append(
                    _candidate(
                        action="reconnaissance",
                        node=node,
                        cognitive_load=len(gaps),
                        factors=factors,
                        reason="agent-verifiable ambiguity has higher expected value than asking",
                    )
                )
    if not candidates:
        candidates.append(
            _candidate(
                action="reconnaissance",
                node=None,
                cognitive_load=0,
                factors=_factors(
                    impact=0.0, human_exclusivity=0.0, researchability=0.5,
                    ambiguity_reduction=0.4, decision_consequence=0.2,
                    cognitive_load=0, repetition=0.0,
                ),
                reason="readiness is incomplete but no explicit gap is available",
            )
        )
    candidates.sort(key=lambda item: (-item["score"], item.get("node_id") or "", item["action"]))
    selected = candidates[0]
    action = _action_projection(selected)
    gain = min(1.0, selected["factors"]["ambiguity_reduction"] * selected["factors"]["impact"])
    state = AlignmentStrategyState(
        belief_digest,
        None,
        tuple(str(node["id"]) for node in gaps),
        tuple(evidence_refs),
        gain,
        min(5, max(1, len(gaps))),
        str(selected["reason"]),
        int(turn),
    )
    action["candidate_scores"] = candidates
    action["strategy_state"] = state.to_dict()
    return action, state


def _factors(
    *, impact: float, human_exclusivity: float, researchability: float,
    ambiguity_reduction: float, decision_consequence: float,
    cognitive_load: int, repetition: float,
) -> dict[str, float]:
    return {
        "impact": round(impact, 6),
        "human_exclusivity": round(human_exclusivity, 6),
        "researchability": round(researchability, 6),
        "ambiguity_reduction": round(ambiguity_reduction, 6),
        "decision_consequence": round(decision_consequence, 6),
        "cognitive_load_penalty": round(min(0.25, max(0, cognitive_load - 1) * 0.04), 6),
        "repetition_penalty": round(repetition * 0.25, 6),
    }


def _candidate(
    *, action: str, node: Mapping[str, Any] | None, cognitive_load: int,
    factors: Mapping[str, float], reason: str, conflict_boost: float = 0.0,
) -> dict[str, Any]:
    score = (
        0.35 * factors["impact"]
        + 0.42 * max(factors["human_exclusivity"], factors["researchability"])
        + 0.13 * factors["ambiguity_reduction"]
        + 0.10 * factors["decision_consequence"]
        + conflict_boost
        - factors["cognitive_load_penalty"]
        - factors["repetition_penalty"]
    )
    attributes = node.get("attributes") if node and isinstance(node.get("attributes"), Mapping) else {}
    return {
        "action": action,
        "node_id": str(node.get("id")) if node else None,
        "score": round(score, 6),
        "factors": dict(factors),
        "reason": reason,
        "belief_basis": list(attributes.get("belief_basis", ())),
        "confidence": str(node.get("confidence", "medium")) if node else "high",
        "decision_consequence": str(attributes.get("decision_consequence", node.get("statement", "strategy handoff") if node else "strategy handoff")),
        "cognitive_load": min(5, max(1, cognitive_load)),
    }


def _action_projection(selected: Mapping[str, Any]) -> dict[str, Any]:
    action = str(selected["action"])
    node_id = selected.get("node_id")
    result: dict[str, Any] = {
        "action": action,
        "question": None,
        "reason": selected["reason"],
        "belief_basis": list(selected.get("belief_basis", ())),
        "confidence": selected.get("confidence", "medium"),
        "decision_consequence": selected.get("decision_consequence", ""),
    }
    if node_id:
        result["node_id"] = node_id
        result["gap_id"] = node_id
    if action == "ask_one":
        result["question"] = f"What should I understand about this decision before research proceeds: {selected['decision_consequence']}?"
    elif action == "constructive_disagreement":
        result["question"] = f"The current evidence conflicts with this premise: {selected['decision_consequence']}. What context should change that reading?"
    elif action == "authority_blocked":
        result["question"] = f"The current evidence makes this outcome infeasible: {selected['decision_consequence']}. Which constraint or outcome may change?"
    return result
