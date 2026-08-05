"""Semantic acceptance bound to exact co-primary delivery revisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


class AcceptanceError(ValueError):
    pass


TECHNICAL_SECTIONS = frozenset({
    "scope", "intent_basis", "baseline", "research_strategy", "findings",
    "architecture", "interfaces", "state_flows", "permissions", "decisions",
    "alternatives", "implementation_order", "repository_touchpoints", "validation",
    "observability", "migration", "rollout", "rollback", "unknowns", "risks",
    "traceability",
})
HUMAN_SECTIONS = frozenset({
    "problem_understood", "evidence_reasoning", "direction", "alternatives",
    "tradeoffs", "expected_capability", "applicability", "risks", "uncertainties",
    "implementation_meaning", "material_changes", "traceability",
})


def _meaningful(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value) and any(_meaningful(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return bool(value) and any(_meaningful(child) for child in value)
    return value is not None


def validate_semantic_deliveries(technical: Mapping[str, Any], human: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the co-primary reports by semantic coverage, not formatting proxies."""
    if not isinstance(technical, Mapping) or not isinstance(human, Mapping):
        raise AcceptanceError("technical and human deliveries must be objects")
    technical_kind = technical.get("kind")
    human_kind = human.get("kind")
    if technical_kind is not None and technical_kind != "technical-research-package":
        raise AcceptanceError("technical delivery has a non-canonical kind")
    if human_kind == "human-brief":
        raise AcceptanceError("human-brief is a legacy input, not an alpha2 acceptance output")
    if human_kind is not None and human_kind != "human-research-report":
        raise AcceptanceError("human delivery has a non-canonical kind")
    technical_document = technical.get("document", technical)
    human_document = human.get("document", human)
    if not isinstance(technical_document, Mapping) or not isinstance(human_document, Mapping):
        raise AcceptanceError("deliveries require structured documents")
    missing_technical = sorted(name for name in TECHNICAL_SECTIONS if not _meaningful(technical_document.get(name)))
    missing_human = sorted(name for name in HUMAN_SECTIONS if not _meaningful(human_document.get(name)))
    claims = technical_document.get("findings", [])
    if isinstance(claims, list):
        orphan_claims = [index for index, claim in enumerate(claims) if isinstance(claim, Mapping) and not claim.get("evidence_refs") and not claim.get("oracle_refs")]
    else:
        orphan_claims = []
    if missing_technical or missing_human or orphan_claims:
        raise AcceptanceError(f"semantic delivery incomplete: technical={missing_technical}, human={missing_human}, orphan_claims={orphan_claims}")
    return {"status": "semantically_ready", "technical_sections": sorted(TECHNICAL_SECTIONS), "human_sections": sorted(HUMAN_SECTIONS), "orphan_claims": []}


@dataclass(frozen=True, slots=True)
class DeliveryAcceptance:
    acceptance_id: str
    run_id: str
    technical_revision: str
    human_revision: str
    displayed_digest: str
    decision: str
    feedback: str
    created_at: str

    @classmethod
    def create(cls, acceptance_id: str, run_id: str, technical_revision: str, human_revision: str, displayed_digest: str, feedback: str, *, decision: str = "accepted") -> "DeliveryAcceptance":
        if decision not in {"accepted", "rejected", "needs_deeper_research"}:
            raise AcceptanceError("unsupported acceptance decision")
        if feedback.casefold().strip() in {"ok", "okay", "yes", "continue", "go ahead"}:
            raise AcceptanceError("generic acknowledgement cannot accept a delivery")
        if not all(isinstance(item, str) and item.strip() for item in (acceptance_id, run_id, technical_revision, human_revision, displayed_digest, feedback)):
            raise AcceptanceError("acceptance fields must be nonempty")
        return cls(acceptance_id, run_id, technical_revision, human_revision, displayed_digest, decision, feedback, datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {"acceptance_id": self.acceptance_id, "run_id": self.run_id, "technical_revision": self.technical_revision, "human_revision": self.human_revision, "displayed_digest": self.displayed_digest, "decision": self.decision, "feedback": self.feedback, "created_at": self.created_at}
