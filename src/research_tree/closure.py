"""Decision Slot closure checks independent of worker prose."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence


class ClosureError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SlotClosureAssessment:
    slot_id: str
    status: str
    checks: Mapping[str, Any]
    token_digest: str | None

    @classmethod
    def assess(cls, *, slot_id: str, evidence: Sequence[Mapping[str, Any]], oracle_runs: Sequence[Mapping[str, Any]], contradictions: Sequence[Mapping[str, Any]], required_classes: Sequence[str]) -> "SlotClosureAssessment":
        classes = {str(item) for evidence_item in evidence for item in evidence_item.get("classes", ())}
        groups = {str(item.get("provenance_group")) for item in evidence if item.get("provenance_group")}
        oracles_passed = bool(oracle_runs) and all(item.get("verdict") == "pass" for item in oracle_runs)
        checks = {"required_evidence_classes": set(required_classes) <= classes, "independent_provenance": len(groups) >= 2, "oracle_passed": oracles_passed, "contradictions_disposed": not contradictions}
        status = "closed" if all(checks.values()) else "open"
        token = None
        if status == "closed":
            body = {"slot_id": slot_id, "checks": checks, "evidence": [dict(item) for item in evidence], "oracles": [dict(item) for item in oracle_runs]}
            token = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return cls(slot_id, status, checks, token)

    def to_dict(self) -> dict[str, Any]:
        return {"slot_id": self.slot_id, "status": self.status, "checks": dict(self.checks), "token_digest": self.token_digest}
