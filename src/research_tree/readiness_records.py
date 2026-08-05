"""Canonical alpha2 readiness evaluation over exact runtime lineage."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .contracts import ContractError, canonical_json_bytes, validate_exact_artifact_ref


class ReadinessRecordContractError(ValueError):
    """Raised when canonical lineage cannot support a readiness result."""


_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CHECK_IDS = (
    "target_lineage",
    "convergence_closure",
    "decision_closure",
    "insight_clear",
    "evaluation_complete",
    "risk_disposition",
)
_CHECK_STATES = {"pass", "fail", "unknown", "not_applicable"}
_STATUSES = {"ready", "not_ready", "blocked", "stale"}
_RISK_TIERS = {"low", "standard", "high", "critical"}
_DEFICIT_KINDS = {
    "lineage_stale",
    "closure_incomplete",
    "decision_invalid",
    "insight_blocked",
    "evaluation_missing",
    "risk_blocked",
}
_ACTIONS = {"landscape", "deep_dive", "adversarial", "validation", "method_switch"}
_FIELDS = {
    "readiness_id",
    "run_id",
    "blueprint_target_ref",
    "convergence_record_ref",
    "insight_digest_ref",
    "decision_refs",
    "p0_closure_aggregate_ref",
    "evaluation_obligation",
    "risk_tier",
    "checks",
    "status",
    "deficits",
    "source_digest",
    "producer_version",
}


def evaluate_canonical_readiness(
    *,
    readiness_id: str,
    run_id: str,
    blueprint_target_ref: Mapping[str, Any],
    convergence_record_ref: Mapping[str, Any],
    convergence_record: Mapping[str, Any],
    insight_digest_ref: Mapping[str, Any],
    insight_digest: Mapping[str, Any],
    decision_refs: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
    p0_closure_aggregate_ref: Mapping[str, Any],
    p0_closure_aggregate: Mapping[str, Any],
    evaluation_obligation: Mapping[str, Any],
    risk_tier: str,
    producer_version: str,
) -> dict[str, Any]:
    """Evaluate canonical readiness without reading storage or mutating a run."""

    _identifier(readiness_id, "readiness_id")
    _identifier(run_id, "run_id")
    target_ref = _artifact_ref(blueprint_target_ref, "blueprint_target_ref", run_id)
    convergence_ref = _artifact_ref(
        convergence_record_ref, "convergence_record_ref", run_id
    )
    insight_ref = _artifact_ref(insight_digest_ref, "insight_digest_ref", run_id)
    normalized_decision_refs = [
        _artifact_ref(item, "decision_ref", run_id) for item in decision_refs
    ]
    if len({_ref_key(item) for item in normalized_decision_refs}) != len(
        normalized_decision_refs
    ):
        raise ReadinessRecordContractError("decision_refs must be unique")
    aggregate_ref = _aggregate_ref(p0_closure_aggregate_ref, run_id)
    obligation = _evaluation_obligation(evaluation_obligation)
    if risk_tier not in _RISK_TIERS:
        raise ReadinessRecordContractError("risk_tier is unsupported")
    producer = _text(producer_version, "producer_version")

    if not isinstance(convergence_record, Mapping):
        raise ReadinessRecordContractError("convergence_record must be an object")
    if convergence_record.get("blueprint_target_ref") != target_ref:
        raise ReadinessRecordContractError("convergence target lineage is inconsistent")
    if convergence_record.get("insight_digest_ref") != insight_ref:
        raise ReadinessRecordContractError("convergence insight lineage is inconsistent")
    if convergence_record.get("decision_refs") != normalized_decision_refs:
        raise ReadinessRecordContractError("convergence decision lineage is inconsistent")
    if convergence_record.get("p0_closure_aggregate_ref") != aggregate_ref:
        raise ReadinessRecordContractError("convergence aggregate lineage is inconsistent")

    if not isinstance(p0_closure_aggregate, Mapping):
        raise ReadinessRecordContractError("p0_closure_aggregate must be an object")
    if p0_closure_aggregate.get("run_id") != run_id:
        raise ReadinessRecordContractError("P0 aggregate belongs to another run")
    if p0_closure_aggregate.get("blueprint_target_ref") != target_ref:
        raise ReadinessRecordContractError("P0 aggregate target lineage is inconsistent")
    if (
        p0_closure_aggregate.get("aggregate_revision") != aggregate_ref["aggregate_revision"]
        or p0_closure_aggregate.get("aggregate_digest") != aggregate_ref["aggregate_digest"]
    ):
        raise ReadinessRecordContractError("P0 aggregate reference is inconsistent")
    if not isinstance(insight_digest, Mapping):
        raise ReadinessRecordContractError("insight_digest must be an object")
    if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes)):
        raise ReadinessRecordContractError("decisions must be an array")
    decisions_by_id = {
        item.get("decision_id"): item
        for item in decisions
        if isinstance(item, Mapping) and isinstance(item.get("decision_id"), str)
    }
    if set(decisions_by_id) != {item["artifact_id"] for item in normalized_decision_refs}:
        raise ReadinessRecordContractError("decision payloads do not match decision_refs")

    checks: list[dict[str, Any]] = []
    deficits: list[dict[str, Any]] = []

    checks.append(_check("target_lineage", "pass", "The current Blueprint Target lineage is exact.", [target_ref]))

    convergence_closed = (
        convergence_record.get("outcome") == "all_slots_closed"
        and convergence_record.get("deficits") == []
    )
    checks.append(
        _check(
            "convergence_closure",
            "pass" if convergence_closed else "fail",
            "Convergence closed all active slots."
            if convergence_closed
            else "Convergence still contains an actionable closure deficit.",
            [convergence_ref],
        )
    )
    if not convergence_closed:
        deficits.append(
            _deficit(
                "convergence_closure",
                "closure_incomplete",
                "Canonical convergence has not closed all active slots.",
                "validation",
                [convergence_ref],
            )
        )

    decisions_closed = all(
        decisions_by_id[reference["artifact_id"]].get("status")
        in {"selected", "conditional"}
        for reference in normalized_decision_refs
    )
    checks.append(
        _check(
            "decision_closure",
            "pass" if decisions_closed else "fail",
            "Every current decision has a selected or conditional disposition."
            if decisions_closed
            else "At least one current decision remains blocked or deferred.",
            normalized_decision_refs,
        )
    )
    if not decisions_closed:
        deficits.append(
            _deficit(
                "decision_closure",
                "decision_invalid",
                "A current decision is not selected or conditional.",
                "deep_dive",
                normalized_decision_refs or [convergence_ref],
            )
        )

    insight_clear = not any(
        insight_digest.get(field) for field in ("gaps", "contradictions", "recommended_actions")
    )
    checks.append(
        _check(
            "insight_clear",
            "pass" if insight_clear else "fail",
            "The current InsightDigest has no blocking gap or contradiction."
            if insight_clear
            else "The current InsightDigest contains unresolved work.",
            [insight_ref],
        )
    )
    if not insight_clear:
        deficits.append(
            _deficit(
                "insight_clear",
                "insight_blocked",
                "The current InsightDigest contains a gap, contradiction, or recommended action.",
                "adversarial" if insight_digest.get("contradictions") else "deep_dive",
                [insight_ref],
            )
        )

    evaluation_complete = bool(obligation["satisfied"] and obligation["evidence_ref"])
    checks.append(
        _check(
            "evaluation_complete",
            "pass" if evaluation_complete else "unknown",
            "Required evaluation evidence is recorded."
            if evaluation_complete
            else "Required evaluation evidence has not been recorded.",
            [obligation],
        )
    )
    if not evaluation_complete:
        deficits.append(
            _deficit(
                "evaluation_complete",
                "evaluation_missing",
                "Required evaluation evidence has not been recorded.",
                "validation",
                [obligation],
            )
        )

    aggregate_passed = p0_closure_aggregate.get("status") == "passed"
    limitations = [
        limitation
        for item in decisions_by_id.values()
        for limitation in item.get("limitations", [])
        if isinstance(limitation, str) and limitation.strip()
    ] + [
        limitation
        for limitation in insight_digest.get("limitations", [])
        if isinstance(limitation, str) and limitation.strip()
    ]
    risk_clear = aggregate_passed and not (
        risk_tier in {"high", "critical"} and limitations
    )
    checks.append(
        _check(
            "risk_disposition",
            "pass" if risk_clear else "fail",
            "No unresolved risk blocks delivery."
            if risk_clear
            else "The risk tier leaves unresolved limitations or P0 closure.",
            [aggregate_ref],
        )
    )
    if not risk_clear:
        deficits.append(
            _deficit(
                "risk_disposition",
                "risk_blocked",
                "The selected risk tier has unresolved limitations or P0 closure.",
                "validation",
                [aggregate_ref],
            )
        )

    lineage = {
        "blueprint_target_ref": target_ref,
        "convergence_record_ref": convergence_ref,
        "insight_digest_ref": insight_ref,
        "decision_refs": normalized_decision_refs,
        "p0_closure_aggregate_ref": aggregate_ref,
        "evaluation_obligation": obligation,
        "risk_tier": risk_tier,
    }
    record = {
        "readiness_id": readiness_id,
        "run_id": run_id,
        **lineage,
        "checks": checks,
        "status": "blocked"
        if any(item["kind"] == "risk_blocked" for item in deficits)
        else ("not_ready" if deficits else "ready"),
        "deficits": deficits,
        "source_digest": hashlib.sha256(canonical_json_bytes(lineage)).hexdigest(),
        "producer_version": producer,
    }
    return validate_canonical_readiness_record(record, run_id=run_id)


def validate_canonical_readiness_record(
    value: Mapping[str, Any], *, run_id: str
) -> dict[str, Any]:
    """Validate a persisted canonical ReadinessRecord recursively."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        missing = _FIELDS - set(value) if isinstance(value, Mapping) else _FIELDS
        extra = set(value) - _FIELDS if isinstance(value, Mapping) else set()
        raise ReadinessRecordContractError(
            f"ReadinessRecord fields mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    record = dict(value)
    _identifier(record["readiness_id"], "readiness_id")
    if record["run_id"] != run_id:
        raise ReadinessRecordContractError("ReadinessRecord belongs to another run")
    _identifier(record["run_id"], "run_id")
    record["blueprint_target_ref"] = _artifact_ref(record["blueprint_target_ref"], "blueprint_target_ref", run_id)
    record["convergence_record_ref"] = _artifact_ref(record["convergence_record_ref"], "convergence_record_ref", run_id)
    record["insight_digest_ref"] = _artifact_ref(record["insight_digest_ref"], "insight_digest_ref", run_id)
    if not isinstance(record["decision_refs"], list):
        raise ReadinessRecordContractError("decision_refs must be an array")
    record["decision_refs"] = [_artifact_ref(item, "decision_ref", run_id) for item in record["decision_refs"]]
    if len({_ref_key(item) for item in record["decision_refs"]}) != len(record["decision_refs"]):
        raise ReadinessRecordContractError("decision_refs must be unique")
    record["p0_closure_aggregate_ref"] = _aggregate_ref(record["p0_closure_aggregate_ref"], run_id)
    record["evaluation_obligation"] = _evaluation_obligation(record["evaluation_obligation"])
    if record["risk_tier"] not in _RISK_TIERS:
        raise ReadinessRecordContractError("risk_tier is unsupported")
    if record["status"] not in _STATUSES:
        raise ReadinessRecordContractError("readiness status is unsupported")

    if not isinstance(record["checks"], list):
        raise ReadinessRecordContractError("checks must be an array")
    checks = [_validate_check(item, run_id) for item in record["checks"]]
    if [item["check_id"] for item in checks] != list(_CHECK_IDS):
        raise ReadinessRecordContractError("checks must contain each canonical gate exactly once in order")
    record["checks"] = checks

    if not isinstance(record["deficits"], list):
        raise ReadinessRecordContractError("deficits must be an array")
    deficits = [_validate_deficit(item, run_id) for item in record["deficits"]]
    if len({item["deficit_id"] for item in deficits}) != len(deficits):
        raise ReadinessRecordContractError("deficit ids must be unique")
    record["deficits"] = deficits
    if record["status"] == "ready":
        if deficits or any(item["status"] != "pass" for item in checks):
            raise ReadinessRecordContractError("ready requires passing checks and zero deficits")
    elif not deficits:
        raise ReadinessRecordContractError("non-ready status requires an actionable deficit")

    lineage = {
        key: record[key]
        for key in (
            "blueprint_target_ref",
            "convergence_record_ref",
            "insight_digest_ref",
            "decision_refs",
            "p0_closure_aggregate_ref",
            "evaluation_obligation",
            "risk_tier",
        )
    }
    expected_digest = hashlib.sha256(canonical_json_bytes(lineage)).hexdigest()
    if record["source_digest"] != expected_digest:
        raise ReadinessRecordContractError("source_digest does not match exact readiness lineage")
    record["producer_version"] = _text(record["producer_version"], "producer_version")
    return json.loads(canonical_json_bytes(record).decode("utf-8"))


def _check(check_id: str, status: str, reason: str, source_refs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"check_id": check_id, "status": status, "reason": reason, "source_refs": source_refs}


def _deficit(check_id: str, kind: str, trigger: str, action: str, source_refs: list[dict[str, Any]]) -> dict[str, Any]:
    semantic = {"check_id": check_id, "kind": kind, "trigger": trigger, "action": action, "source_refs": source_refs}
    return {"deficit_id": "deficit-" + hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()[:16], **semantic}


def _validate_check(value: Any, run_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"check_id", "status", "reason", "source_refs"}:
        raise ReadinessRecordContractError("readiness check fields mismatch")
    if value["check_id"] not in _CHECK_IDS or value["status"] not in _CHECK_STATES:
        raise ReadinessRecordContractError("readiness check value is unsupported")
    return {"check_id": value["check_id"], "status": value["status"], "reason": _text(value["reason"], "check reason"), "source_refs": _source_refs(value["source_refs"], run_id, allow_empty=True)}


def _validate_deficit(value: Any, run_id: str) -> dict[str, Any]:
    fields = {"deficit_id", "check_id", "kind", "trigger", "action", "source_refs"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ReadinessRecordContractError("readiness deficit fields mismatch")
    _identifier(value["deficit_id"], "deficit_id")
    if value["check_id"] not in _CHECK_IDS or value["kind"] not in _DEFICIT_KINDS or value["action"] not in _ACTIONS:
        raise ReadinessRecordContractError("readiness deficit value is unsupported")
    return {"deficit_id": value["deficit_id"], "check_id": value["check_id"], "kind": value["kind"], "trigger": _text(value["trigger"], "deficit trigger"), "action": value["action"], "source_refs": _source_refs(value["source_refs"], run_id, allow_empty=False)}


def _source_refs(value: Any, run_id: str, *, allow_empty: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ReadinessRecordContractError("source_refs must be an array")
    refs = [_source_ref(item, run_id) for item in value]
    if len({canonical_json_bytes(item) for item in refs}) != len(refs):
        raise ReadinessRecordContractError("source_refs must be unique")
    return refs


def _source_ref(value: Any, run_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReadinessRecordContractError("source_ref must be an object")
    if "artifact_id" in value:
        return _artifact_ref(value, "source artifact ref", run_id)
    if "aggregate_revision" in value:
        return _aggregate_ref(value, run_id)
    return _evaluation_obligation(value)


def _artifact_ref(value: Any, label: str, run_id: str) -> dict[str, Any]:
    try:
        return validate_exact_artifact_ref(value, label=label, run_id=run_id)
    except (ContractError, TypeError, ValueError) as error:
        raise ReadinessRecordContractError(str(error)) from error


def _aggregate_ref(value: Any, run_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"run_id", "aggregate_revision", "aggregate_digest"}:
        raise ReadinessRecordContractError("P0 aggregate reference fields mismatch")
    if value["run_id"] != run_id:
        raise ReadinessRecordContractError("P0 aggregate reference belongs to another run")
    revision = value["aggregate_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ReadinessRecordContractError("P0 aggregate revision must be positive")
    if not isinstance(value["aggregate_digest"], str) or _DIGEST_RE.fullmatch(value["aggregate_digest"]) is None:
        raise ReadinessRecordContractError("P0 aggregate digest must be lowercase SHA-256")
    return dict(value)


def _evaluation_obligation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"obligation", "satisfied", "evidence_ref"}:
        raise ReadinessRecordContractError("evaluation obligation fields mismatch")
    if value["obligation"] != "evaluation" or not isinstance(value["satisfied"], bool):
        raise ReadinessRecordContractError("evaluation obligation value is invalid")
    evidence_ref = value["evidence_ref"]
    if evidence_ref is not None and (not isinstance(evidence_ref, str) or not evidence_ref.strip()):
        raise ReadinessRecordContractError("evaluation evidence_ref is invalid")
    if value["satisfied"] and evidence_ref is None:
        raise ReadinessRecordContractError("satisfied evaluation requires evidence_ref")
    return dict(value)


def _ref_key(reference: Mapping[str, Any]) -> tuple[str, str, int, str]:
    return (str(reference["run_id"]), str(reference["artifact_id"]), int(reference["revision"]), str(reference["content_hash"]))


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ReadinessRecordContractError(f"{label} is not a canonical identifier")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadinessRecordContractError(f"{label} is required")
    return value
