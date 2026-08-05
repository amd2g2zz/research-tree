"""Canonical alpha2 ConvergenceRecord validation."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from .contracts import (
    ContractError,
    canonical_json_bytes,
    validate_exact_artifact_ref,
)


class ConvergenceRecordContractError(ValueError):
    """Raised when a convergence outcome cannot trigger canonical work."""


_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "convergence_id",
    "run_id",
    "blueprint_target_ref",
    "insight_digest_ref",
    "decision_refs",
    "p0_closure_aggregate_ref",
    "outcome",
    "deficits",
    "producer_version",
}
_DEFICIT_KINDS = {
    "uncovered",
    "contradiction",
    "insight_gap",
    "closure_missing",
    "closure_stale",
    "validation_pending",
}
_ACTIONS = {
    "landscape",
    "deep_dive",
    "adversarial",
    "validation",
    "method_switch",
}


def validate_convergence_record_payload(
    value: Mapping[str, Any], *, run_id: str
) -> dict[str, Any]:
    """Return canonical convergence data or reject it before persistence."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        missing = _FIELDS - set(value) if isinstance(value, Mapping) else _FIELDS
        extra = set(value) - _FIELDS if isinstance(value, Mapping) else set()
        raise ConvergenceRecordContractError(
            f"ConvergenceRecord fields mismatch; missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )
    normalized = dict(value)
    _identifier(normalized["convergence_id"], "convergence_id")
    _identifier(normalized["run_id"], "run_id")
    if normalized["run_id"] != run_id:
        raise ConvergenceRecordContractError(
            "ConvergenceRecord belongs to another run"
        )
    normalized["blueprint_target_ref"] = _artifact_ref(
        normalized["blueprint_target_ref"], "blueprint_target_ref", run_id
    )
    normalized["insight_digest_ref"] = _artifact_ref(
        normalized["insight_digest_ref"], "insight_digest_ref", run_id
    )
    decision_values = normalized["decision_refs"]
    if not isinstance(decision_values, list):
        raise ConvergenceRecordContractError("decision_refs must be an array")
    decisions = [
        _artifact_ref(item, "decision_ref", run_id) for item in decision_values
    ]
    if len({_ref_key(item) for item in decisions}) != len(decisions):
        raise ConvergenceRecordContractError("decision_refs must be unique")
    normalized["decision_refs"] = decisions

    aggregate = normalized["p0_closure_aggregate_ref"]
    if not isinstance(aggregate, Mapping) or set(aggregate) != {
        "run_id",
        "aggregate_revision",
        "aggregate_digest",
    }:
        raise ConvergenceRecordContractError(
            "p0_closure_aggregate_ref fields mismatch"
        )
    if aggregate["run_id"] != run_id:
        raise ConvergenceRecordContractError(
            "P0 closure aggregate belongs to another run"
        )
    revision = aggregate["aggregate_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ConvergenceRecordContractError(
            "P0 closure aggregate revision must be positive"
        )
    digest = aggregate["aggregate_digest"]
    if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
        raise ConvergenceRecordContractError(
            "P0 closure aggregate digest must be lowercase SHA-256"
        )
    normalized["p0_closure_aggregate_ref"] = dict(aggregate)

    outcome = normalized["outcome"]
    if outcome not in {"closure_deficit", "all_slots_closed"}:
        raise ConvergenceRecordContractError("convergence outcome is unsupported")
    deficit_values = normalized["deficits"]
    if not isinstance(deficit_values, list):
        raise ConvergenceRecordContractError("deficits must be an array")
    if outcome == "all_slots_closed" and deficit_values:
        raise ConvergenceRecordContractError(
            "all_slots_closed cannot contain deficits"
        )
    if outcome == "closure_deficit" and not deficit_values:
        raise ConvergenceRecordContractError(
            "closure_deficit requires an actionable deficit"
        )
    deficits: list[dict[str, Any]] = []
    deficit_ids: set[str] = set()
    for item in deficit_values:
        if not isinstance(item, Mapping) or set(item) != {
            "deficit_id",
            "slot_id",
            "kind",
            "trigger",
            "action",
            "source_refs",
        }:
            raise ConvergenceRecordContractError("deficit fields mismatch")
        deficit_id = _identifier(item["deficit_id"], "deficit_id")
        if deficit_id in deficit_ids:
            raise ConvergenceRecordContractError("deficit ids must be unique")
        deficit_ids.add(deficit_id)
        slot_id = _identifier(item["slot_id"], "deficit slot_id")
        if item["kind"] not in _DEFICIT_KINDS:
            raise ConvergenceRecordContractError("deficit kind is unsupported")
        if item["action"] not in _ACTIONS:
            raise ConvergenceRecordContractError("deficit action is unsupported")
        trigger = _text(item["trigger"], "deficit trigger")
        source_values = item["source_refs"]
        if not isinstance(source_values, list) or not source_values:
            raise ConvergenceRecordContractError(
                "deficit source_refs must be a nonempty array"
            )
        source_refs = [
            _text(source, "deficit source_ref") for source in source_values
        ]
        if len(set(source_refs)) != len(source_refs):
            raise ConvergenceRecordContractError(
                "deficit source_refs must be unique"
            )
        deficits.append(
            {
                "deficit_id": deficit_id,
                "slot_id": slot_id,
                "kind": item["kind"],
                "trigger": trigger,
                "action": item["action"],
                "source_refs": source_refs,
            }
        )
    normalized["deficits"] = deficits
    normalized["producer_version"] = _text(
        normalized["producer_version"], "producer_version"
    )
    return json.loads(canonical_json_bytes(normalized).decode("utf-8"))


def _artifact_ref(value: Any, label: str, run_id: str) -> dict[str, Any]:
    try:
        return validate_exact_artifact_ref(value, label=label, run_id=run_id)
    except (ContractError, TypeError, ValueError) as error:
        raise ConvergenceRecordContractError(str(error)) from error


def _ref_key(reference: Mapping[str, Any]) -> tuple[str, str, int, str]:
    return (
        str(reference["run_id"]),
        str(reference["artifact_id"]),
        int(reference["revision"]),
        str(reference["content_hash"]),
    )


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ConvergenceRecordContractError(
            f"{label} is not a canonical identifier"
        )
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConvergenceRecordContractError(f"{label} is required")
    return value
