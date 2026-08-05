"""Semantic acceptance bound to exact co-primary delivery revisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class AcceptanceError(ValueError):
    pass


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
