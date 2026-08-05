"""Decision Slot closure checks independent of worker prose."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import hashlib
import json
from typing import Any, Mapping, Sequence


class ClosureError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class P0ClosureAggregate:
    """Deterministic run-level closure over the active P0 Slot set."""

    run_id: str
    aggregate_revision: int
    blueprint_target_ref: Mapping[str, Any]
    slots: tuple[Mapping[str, Any], ...]
    status: str
    assessor_version: str
    issued_at: str
    aggregate_digest: str

    @classmethod
    def build(
        cls,
        *,
        run_id: str,
        aggregate_revision: int,
        blueprint_target_ref: Mapping[str, Any],
        active_slots: Sequence[Mapping[str, Any]],
        latest_assessments: Mapping[str, Mapping[str, Any]],
        assessor_version: str,
        issued_at: str,
    ) -> "P0ClosureAggregate":
        if aggregate_revision < 1:
            raise ClosureError("aggregate_revision must be positive")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ClosureError("aggregate run_id is required")
        if not isinstance(assessor_version, str) or not assessor_version.strip():
            raise ClosureError("aggregate assessor_version is required")
        target_ref = _decision_ref(blueprint_target_ref)
        normalized_slots: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in active_slots:
            slot_id = item.get("id", item.get("slot_id"))
            if not isinstance(slot_id, str) or not slot_id.strip():
                raise ClosureError("active P0 Slot id is required")
            if slot_id in seen:
                raise ClosureError("active P0 Slot ids must be unique")
            seen.add(slot_id)
            assessment = latest_assessments.get(slot_id)
            if assessment is None:
                normalized_slots.append(
                    {
                        "slot_id": slot_id,
                        "status": "missing",
                        "assessment_revision": None,
                        "decision_ref": None,
                        "token_digest": None,
                    }
                )
                continue
            token = assessment.get("token_digest")
            status = str(assessment.get("status", "open"))
            if status == "passed" and (not isinstance(token, str) or len(token) != 64):
                status = "stale"
                token = None
            normalized_slots.append(
                {
                    "slot_id": slot_id,
                    "status": status,
                    "assessment_revision": assessment.get("assessment_revision"),
                    "decision_ref": (
                        dict(assessment["decision_ref"])
                        if isinstance(assessment.get("decision_ref"), Mapping)
                        else None
                    ),
                    "token_digest": token if status == "passed" else None,
                }
            )
        normalized_slots.sort(key=lambda item: item["slot_id"])
        status = "passed" if all(item["status"] == "passed" for item in normalized_slots) else "open"
        semantic = {
            "run_id": run_id,
            "aggregate_revision": aggregate_revision,
            "blueprint_target_ref": target_ref,
            "slots": normalized_slots,
            "status": status,
            "assessor_version": assessor_version,
        }
        digest = hashlib.sha256(
            json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            run_id=run_id,
            aggregate_revision=aggregate_revision,
            blueprint_target_ref=target_ref,
            slots=tuple(normalized_slots),
            status=status,
            assessor_version=assessor_version,
            issued_at=issued_at,
            aggregate_digest=digest,
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "aggregate_revision": self.aggregate_revision,
            "blueprint_target_ref": dict(self.blueprint_target_ref),
            "slots": [dict(item) for item in self.slots],
            "status": self.status,
            "assessor_version": self.assessor_version,
            "issued_at": self.issued_at,
            "aggregate_digest": self.aggregate_digest,
        }


@dataclass(frozen=True, slots=True)
class SlotClosureAssessment:
    slot_id: str
    status: str
    checks: Mapping[str, Any]
    token_digest: str | None
    assessment_revision: int = 1
    decision_ref: Mapping[str, Any] | None = None
    decision_status: str = "deferred"
    required_evidence_results: tuple[Mapping[str, Any], ...] = ()
    independence_groups: tuple[str, ...] = ()
    counterevidence_search: Mapping[str, Any] | None = None
    contradiction_disposition: Mapping[str, Any] | None = None
    oracle_refs: tuple[str, ...] = ()
    fallback: str = "legacy fallback"
    reversal_condition: str = "legacy reversal condition"
    assessor_version: str = "legacy-assessor"

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

    @classmethod
    def assess_alpha2(
        cls,
        *,
        slot_id: str,
        assessment_revision: int,
        decision_ref: Mapping[str, Any],
        decision_status: str,
        evidence: Sequence[Mapping[str, Any]],
        oracle_runs: Sequence[Mapping[str, Any]],
        contradictions: Sequence[Mapping[str, Any]],
        required_classes: Sequence[str],
        counterevidence_search: Mapping[str, Any],
        fallback: str,
        reversal_condition: str,
        assessor_version: str,
    ) -> "SlotClosureAssessment":
        if assessment_revision < 1:
            raise ClosureError("assessment_revision must be positive")
        normalized_decision_ref = _decision_ref(decision_ref)
        if decision_status not in {"selected", "conditional", "deferred", "blocked"}:
            raise ClosureError("unsupported decision status")
        if not all(isinstance(item, str) and item.strip() for item in (slot_id, fallback, reversal_condition, assessor_version)):
            raise ClosureError("alpha2 closure identity, fallback, reversal, and assessor are required")
        groups = tuple(sorted({str(item["provenance_group"]) for item in evidence if item.get("provenance_group")}))
        evidence_results = tuple(
            {
                "evidence_class": evidence_class,
                "passed": any(evidence_class in item.get("classes", ()) for item in evidence),
                "evidence_refs": sorted(str(item.get("evidence_id")) for item in evidence if evidence_class in item.get("classes", ())),
            }
            for evidence_class in required_classes
        )
        unresolved = [
            dict(item) for item in contradictions
            if item.get("status", item.get("disposition")) not in {"resolved", "rejected", "superseded"}
        ]
        normalized_oracles = [dict(item) for item in oracle_runs]
        oracle_passed = bool(normalized_oracles) and all(
            item.get("verdict") in {"pass", "passed"}
            and item.get("reproducibility_status", "reproducible") == "reproducible"
            for item in normalized_oracles
        )
        checks = {
            "required_evidence_classes": all(item["passed"] for item in evidence_results),
            "independent_provenance": len(groups) >= 2,
            "counterevidence_completed": bool(counterevidence_search.get("completed")),
            "oracle_passed": oracle_passed,
            "contradictions_disposed": not unresolved,
            "fallback_present": True,
            "reversal_condition_present": True,
            "decision_selected_or_conditional": decision_status in {"selected", "conditional"},
        }
        status = "passed" if all(checks.values()) else "open"
        oracle_refs = tuple(sorted(str(item.get("oracle_run_id")) for item in normalized_oracles if item.get("oracle_run_id")))
        contradiction_disposition = {"unresolved": unresolved, "total": len(contradictions)}
        token = None
        if status == "passed":
            body = {
                "slot_id": slot_id,
                "assessment_revision": assessment_revision,
                "decision_ref": normalized_decision_ref,
                "decision_status": decision_status,
                "required_evidence_results": evidence_results,
                "independence_groups": groups,
                "counterevidence_search": dict(counterevidence_search),
                "contradiction_disposition": contradiction_disposition,
                "oracle_refs": oracle_refs,
                "fallback": fallback,
                "reversal_condition": reversal_condition,
                "assessor_version": assessor_version,
            }
            token = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return cls(
            slot_id, status, checks, token, assessment_revision, normalized_decision_ref, decision_status, evidence_results, groups,
            dict(counterevidence_search), contradiction_disposition, oracle_refs, fallback,
            reversal_condition, assessor_version,
        )

    def revoke(self, *, reason: str) -> "SlotClosureAssessment":
        if not isinstance(reason, str) or not reason.strip():
            raise ClosureError("closure revocation reason is required")
        return replace(self, status="revoked", checks={**self.checks, "revoked": reason}, token_digest=None)

    def to_dict(self) -> dict[str, Any]:
        return {"slot_id": self.slot_id, "status": self.status, "checks": dict(self.checks), "token_digest": self.token_digest}

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "assessment_revision": self.assessment_revision,
            "decision_ref": dict(self.decision_ref or {}),
            "decision_status": self.decision_status,
            "required_evidence_results": [dict(item) for item in self.required_evidence_results],
            "independence_groups": list(self.independence_groups),
            "counterevidence_search": dict(self.counterevidence_search or {}),
            "contradiction_disposition": dict(self.contradiction_disposition or {}),
            "oracle_refs": list(self.oracle_refs),
            "fallback": self.fallback,
            "reversal_condition": self.reversal_condition,
            "assessor_version": self.assessor_version,
            "status": "passed" if self.status == "closed" else self.status,
            "token_digest": self.token_digest,
        }


def oracle_successor_actions(oracle_runs: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Translate nonpassing oracle outcomes into explicit successor work."""

    actions: list[dict[str, str]] = []
    for run in oracle_runs:
        verdict = run.get("verdict")
        if verdict in {"pass", "passed", "not_applicable"}:
            continue
        action = "method_switch" if verdict in {"fail", "failed"} else "validation"
        actions.append({
            "action": action,
            "oracle_run_id": str(run.get("oracle_run_id", "unknown")),
            "reason": f"oracle verdict is {verdict}",
        })
    return actions


def _decision_ref(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"run_id", "artifact_id", "revision", "content_hash"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ClosureError("decision_ref fields mismatch")
    if not all(isinstance(value[field], str) and value[field].strip() for field in ("run_id", "artifact_id")):
        raise ClosureError("decision_ref identity is required")
    if isinstance(value["revision"], bool) or not isinstance(value["revision"], int) or value["revision"] < 1:
        raise ClosureError("decision_ref revision must be positive")
    if not isinstance(value["content_hash"], str) or len(value["content_hash"]) != 64:
        raise ClosureError("decision_ref content_hash must be SHA-256")
    return dict(value)
