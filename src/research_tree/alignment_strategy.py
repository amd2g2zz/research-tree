"""Internal alignment strategy state and one-prompt selection."""

from __future__ import annotations

from dataclasses import dataclass, asdict
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
        return asdict(self) | {"unresolved_gaps": list(self.unresolved_gaps), "evidence_refs": list(self.evidence_refs)}


def select_alignment_action(*, nodes: Sequence[Mapping[str, Any]], readiness: Mapping[str, Any], turn: int, graph_digest: str) -> tuple[dict[str, Any], AlignmentStrategyState]:
    unresolved = [node for node in nodes if node.get("status") in {"candidate", "disputed"}]
    gaps = sorted(unresolved, key=lambda node: (-int(node.get("impact", 1)), int(node.get("ask_count", 0)), str(node.get("id"))))
    human_gaps = [node for node in gaps if bool(node.get("human_only"))]
    agent_gaps = [node for node in gaps if not bool(node.get("human_only"))]
    evidence_refs = sorted({str(node.get("attributes", {}).get("anchor", {}).get("ref")) for node in nodes if isinstance(node.get("attributes"), Mapping) and isinstance(node.get("attributes", {}).get("anchor"), Mapping) and node.get("attributes", {}).get("anchor", {}).get("ref")})
    belief_digest = hashlib.sha256(canonical_json_bytes({"graph_digest": graph_digest, "readiness": readiness, "gaps": [node.get("id") for node in gaps]})).hexdigest()
    if readiness.get("ready"):
        action = {"action": "await_human_confirmation", "question": None, "reason": "all hard alignment fields are resolved"}
        reason = action["reason"]
        pending = None
        gain = 0.0
    elif human_gaps:
        node = human_gaps[0]
        action = {"action": "ask_one", "node_id": node["id"], "gap_id": node["id"], "question": f"What outcome or constraint should this research satisfy: {node['statement']}?", "reason": "highest-consequence requester-owned gap"}
        reason = action["reason"]
        pending = str(node["id"])
        gain = min(1.0, float(node.get("impact", 1)) / 5.0)
    elif agent_gaps:
        node = agent_gaps[0]
        action = {"action": "reconnaissance", "question": None, "gap_id": node["id"], "reason": "remaining ambiguity is agent-verifiable before asking the requester"}
        reason = action["reason"]
        pending = None
        gain = min(1.0, float(node.get("impact", 1)) / 5.0)
    else:
        action = {"action": "reconnaissance", "question": None, "reason": "readiness is incomplete but no explicit gap is available"}
        reason = action["reason"]
        pending = None
        gain = 0.0
    state = AlignmentStrategyState(belief_digest, pending, tuple(str(node["id"]) for node in gaps), tuple(evidence_refs), gain, min(5, max(1, len(gaps))), reason, int(turn))
    return {**action, "strategy_state": state.to_dict()}, state
