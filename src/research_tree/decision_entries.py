"""Canonical alpha2 DecisionLedgerEntry validation."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from .contracts import (
    ContractError,
    canonical_json_bytes,
    validate_exact_artifact_ref,
)


class DecisionEntryContractError(ValueError):
    """Raised when a proposed decision is not traceable to canonical state."""


_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_FIELDS = {
    "decision_id",
    "run_id",
    "blueprint_target_ref",
    "decision_slot_id",
    "finding_pack_refs",
    "insight_digest_ref",
    "status",
    "selected_option",
    "alternatives",
    "evidence_basis",
    "rationale",
    "design_consequence",
    "repository_touchpoints",
    "validation",
    "change_tasks",
    "assumptions",
    "fallback",
    "reversal_condition",
    "revision_reason",
    "previous_decision_ref",
    "producer_version",
    "limitations",
}


def validate_decision_entry_payload(
    value: Mapping[str, Any],
    *,
    run_id: str,
    blueprint_target: Mapping[str, Any],
    finding_packs: Mapping[str, Mapping[str, Any]],
    insight_digest: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize one decision or reject unsupported convergence."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        missing = _FIELDS - set(value) if isinstance(value, Mapping) else _FIELDS
        extra = set(value) - _FIELDS if isinstance(value, Mapping) else set()
        raise DecisionEntryContractError(
            f"DecisionLedgerEntry fields mismatch; missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )
    normalized = dict(value)
    for field in ("decision_id", "run_id", "decision_slot_id"):
        _identifier(normalized[field], field)
    if normalized["run_id"] != run_id:
        raise DecisionEntryContractError("DecisionLedgerEntry belongs to another run")

    normalized["blueprint_target_ref"] = _artifact_ref(
        normalized["blueprint_target_ref"], "blueprint_target_ref", run_id
    )
    normalized["insight_digest_ref"] = _artifact_ref(
        normalized["insight_digest_ref"], "insight_digest_ref", run_id
    )
    previous = normalized["previous_decision_ref"]
    normalized["previous_decision_ref"] = (
        _artifact_ref(previous, "previous_decision_ref", run_id)
        if previous is not None
        else None
    )

    slots = blueprint_target.get("slots")
    if not isinstance(slots, list):
        raise DecisionEntryContractError("Blueprint Target slots are invalid")
    slot = next(
        (
            item
            for item in slots
            if isinstance(item, Mapping)
            and item.get("slot_id", item.get("id")) == normalized["decision_slot_id"]
        ),
        None,
    )
    if slot is None or slot.get("status") in {"closed", "superseded", "removed"}:
        raise DecisionEntryContractError("decision references a non-active Slot")
    options_value = slot.get("options", slot.get("alternatives"))
    if (
        not isinstance(options_value, list)
        or not options_value
        or not all(isinstance(item, str) and item.strip() for item in options_value)
        or len(set(options_value)) != len(options_value)
    ):
        raise DecisionEntryContractError("Decision Slot options are invalid")
    options = set(options_value)

    refs_value = normalized["finding_pack_refs"]
    if not isinstance(refs_value, list):
        raise DecisionEntryContractError("finding_pack_refs must be an array")
    finding_refs = [
        _artifact_ref(item, "finding_pack_ref", run_id) for item in refs_value
    ]
    if len({_ref_key(item) for item in finding_refs}) != len(finding_refs):
        raise DecisionEntryContractError("finding_pack_refs must be unique")
    normalized["finding_pack_refs"] = finding_refs
    resolved_findings: dict[tuple[str, str, int, str], Mapping[str, Any]] = {}
    for reference in finding_refs:
        finding = finding_packs.get(reference["artifact_id"])
        if not isinstance(finding, Mapping):
            raise DecisionEntryContractError("finding_pack_ref does not resolve")
        if finding.get("finding_id", finding.get("id")) != reference["artifact_id"]:
            raise DecisionEntryContractError("finding_pack_ref identity is inconsistent")
        if finding.get("decision_slot_id") != normalized["decision_slot_id"]:
            raise DecisionEntryContractError("Finding Pack belongs to another Slot")
        resolved_findings[_ref_key(reference)] = finding

    slot_refs = insight_digest.get("slot_refs")
    if (
        not isinstance(slot_refs, list)
        or normalized["decision_slot_id"] not in slot_refs
    ):
        raise DecisionEntryContractError("InsightDigest does not cover the Decision Slot")

    status = normalized["status"]
    if status not in {"selected", "conditional", "deferred", "blocked"}:
        raise DecisionEntryContractError("decision status is unsupported")
    selected = normalized["selected_option"]
    if status in {"selected", "conditional"}:
        if not isinstance(selected, str) or selected not in options:
            raise DecisionEntryContractError("selected option is absent from the Slot")
        if not finding_refs:
            raise DecisionEntryContractError("selected decision requires Finding Packs")
    elif selected is not None:
        raise DecisionEntryContractError(
            "deferred or blocked decision cannot select an option"
        )

    alternatives = _mapping_array(normalized["alternatives"], "alternatives")
    alternative_options: set[str] = set()
    parsed_alternatives: list[dict[str, Any]] = []
    for item in alternatives:
        if set(item) != {"option", "disposition", "reason"}:
            raise DecisionEntryContractError("alternative fields mismatch")
        option = _text(item["option"], "alternative option")
        if option not in options or option in alternative_options:
            raise DecisionEntryContractError("alternative option is invalid or duplicated")
        if item["disposition"] not in {"rejected", "deferred", "unresolved"}:
            raise DecisionEntryContractError("alternative disposition is unsupported")
        parsed_alternatives.append(
            {
                "option": option,
                "disposition": item["disposition"],
                "reason": _text(item["reason"], "alternative reason"),
            }
        )
        alternative_options.add(option)
    expected_alternatives = options - ({selected} if isinstance(selected, str) else set())
    if alternative_options != expected_alternatives:
        raise DecisionEntryContractError(
            "alternatives must dispose every non-selected option"
        )
    normalized["alternatives"] = parsed_alternatives

    basis = _mapping_array(normalized["evidence_basis"], "evidence_basis")
    basis_observations: dict[tuple[str, str, int, str], set[str]] = {}
    parsed_basis: list[dict[str, Any]] = []
    for item in basis:
        if set(item) != {"finding_pack_ref", "observation_ids"}:
            raise DecisionEntryContractError("evidence basis fields mismatch")
        reference = _artifact_ref(
            item["finding_pack_ref"], "evidence basis finding_pack_ref", run_id
        )
        key = _ref_key(reference)
        finding = resolved_findings.get(key)
        if finding is None:
            raise DecisionEntryContractError(
                "evidence basis references an unlisted Finding Pack"
            )
        observation_ids = _identifier_array(
            item["observation_ids"], "evidence basis observation_ids"
        )
        available = {
            observation.get("observation_id")
            for observation in finding.get("observations", [])
            if isinstance(observation, Mapping)
        }
        if not set(observation_ids) <= available:
            raise DecisionEntryContractError(
                "evidence basis references an unknown observation"
            )
        basis_observations.setdefault(key, set()).update(observation_ids)
        parsed_basis.append(
            {"finding_pack_ref": reference, "observation_ids": observation_ids}
        )
    normalized["evidence_basis"] = parsed_basis
    if status in {"selected", "conditional"} and not basis:
        raise DecisionEntryContractError("selected decision requires evidence basis")

    if isinstance(selected, str):
        supporting_observations: set[tuple[tuple[str, str, int, str], str]] = set()
        for key, finding in resolved_findings.items():
            for effect in finding.get("option_effects", []):
                if (
                    isinstance(effect, Mapping)
                    and effect.get("option") == selected
                    and effect.get("effect") == "supports"
                ):
                    for observation_id in effect.get("observation_ids", []):
                        supporting_observations.add((key, str(observation_id)))
        if not any(
            (key, observation_id) in supporting_observations
            for key, observation_ids in basis_observations.items()
            for observation_id in observation_ids
        ):
            raise DecisionEntryContractError(
                "selected option has no supporting observation"
            )

    for field in (
        "rationale",
        "design_consequence",
        "fallback",
        "reversal_condition",
        "revision_reason",
        "producer_version",
    ):
        normalized[field] = _text(normalized[field], field)
    normalized["assumptions"] = _text_array(
        normalized["assumptions"], "assumptions"
    )
    normalized["limitations"] = _text_array(
        normalized["limitations"], "limitations"
    )
    normalized["repository_touchpoints"] = _touchpoints(
        normalized["repository_touchpoints"]
    )
    normalized["validation"] = _validation(normalized["validation"])
    normalized["change_tasks"] = _change_tasks(normalized["change_tasks"])
    return json.loads(canonical_json_bytes(normalized).decode("utf-8"))


def _artifact_ref(value: Any, label: str, run_id: str) -> dict[str, Any]:
    try:
        return validate_exact_artifact_ref(value, label=label, run_id=run_id)
    except (ContractError, TypeError, ValueError) as error:
        raise DecisionEntryContractError(str(error)) from error


def _ref_key(reference: Mapping[str, Any]) -> tuple[str, str, int, str]:
    return (
        str(reference["run_id"]),
        str(reference["artifact_id"]),
        int(reference["revision"]),
        str(reference["content_hash"]),
    )


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise DecisionEntryContractError(f"{label} is not a canonical identifier")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionEntryContractError(f"{label} is required")
    return value


def _mapping_array(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise DecisionEntryContractError(f"{label} must be an object array")
    return list(value)


def _identifier_array(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise DecisionEntryContractError(f"{label} must be a nonempty array")
    result = [_identifier(item, label) for item in value]
    if len(set(result)) != len(result):
        raise DecisionEntryContractError(f"{label} must be unique")
    return result


def _text_array(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise DecisionEntryContractError(f"{label} must be an array")
    return [_text(item, label) for item in value]


def _touchpoints(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _mapping_array(value, "repository_touchpoints"):
        if set(item) != {"path", "symbols", "change_kind"}:
            raise DecisionEntryContractError("repository touchpoint fields mismatch")
        if item["change_kind"] not in {"add", "modify", "delete", "inspect"}:
            raise DecisionEntryContractError("repository touchpoint change kind is invalid")
        symbols = _text_array(item["symbols"], "repository touchpoint symbols")
        if len(set(symbols)) != len(symbols):
            raise DecisionEntryContractError("repository touchpoint symbols must be unique")
        result.append(
            {
                "path": _text(item["path"], "repository touchpoint path"),
                "symbols": symbols,
                "change_kind": item["change_kind"],
            }
        )
    return result


def _validation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "oracle_run_refs",
        "status",
        "limitations",
    }:
        raise DecisionEntryContractError("validation fields mismatch")
    if value["status"] not in {
        "pending",
        "passed",
        "failed",
        "inconclusive",
        "not_applicable",
    }:
        raise DecisionEntryContractError("validation status is unsupported")
    refs = _mapping_array(value["oracle_run_refs"], "validation oracle_run_refs")
    parsed_refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in refs:
        if set(item) != {"oracle_run_id", "payload_digest"}:
            raise DecisionEntryContractError("OracleRun reference fields mismatch")
        oracle_id = _identifier(item["oracle_run_id"], "OracleRun id")
        digest = item["payload_digest"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise DecisionEntryContractError("OracleRun payload digest is invalid")
        if (oracle_id, digest) in seen:
            raise DecisionEntryContractError("OracleRun references must be unique")
        seen.add((oracle_id, digest))
        parsed_refs.append({"oracle_run_id": oracle_id, "payload_digest": digest})
    if value["status"] == "passed" and not parsed_refs:
        raise DecisionEntryContractError("passed validation requires an OracleRun")
    return {
        "oracle_run_refs": parsed_refs,
        "status": value["status"],
        "limitations": _text_array(value["limitations"], "validation limitations"),
    }


def _change_tasks(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _mapping_array(value, "change_tasks"):
        if set(item) != {"task_id", "objective", "affected_paths", "success_oracle"}:
            raise DecisionEntryContractError("change task fields mismatch")
        task_id = _identifier(item["task_id"], "change task id")
        if task_id in seen:
            raise DecisionEntryContractError("change task ids must be unique")
        seen.add(task_id)
        paths = _text_array(item["affected_paths"], "change task affected_paths")
        if len(set(paths)) != len(paths):
            raise DecisionEntryContractError("change task affected_paths must be unique")
        result.append(
            {
                "task_id": task_id,
                "objective": _text(item["objective"], "change task objective"),
                "affected_paths": paths,
                "success_oracle": _text(
                    item["success_oracle"], "change task success_oracle"
                ),
            }
        )
    return result
