"""Canonical alpha2 Finding Pack payload validation."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from .contracts import canonical_json_bytes, validate_exact_artifact_ref
from .evidence import EvidenceError, ResolvableEvidenceAnchor
from .worker_contracts import ACTION_KINDS


class FindingPackContractError(ValueError):
    """Raised when a worker result cannot enter canonical ingestion."""


_FIELDS = {
    "finding_id", "run_id", "attempt_id", "work_item_ref",
    "blueprint_target_ref", "decision_slot_id", "observations",
    "option_effects", "implementation_implications", "remaining_uncertainties",
    "research_continuations", "oracle_run_refs",
}
_OBSERVATION_FIELDS = {
    "observation_id", "class", "claim", "anchors", "assumptions",
    "consequence", "reversal_condition", "unknown_reason",
    "next_acquisition_method", "confidence", "limitations",
}
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def validate_finding_pack_payload(
    value: Mapping[str, Any], *, run_id: str
) -> dict[str, Any]:
    """Return one normalized payload or reject it before persistence."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        missing = _FIELDS - set(value) if isinstance(value, Mapping) else _FIELDS
        extra = set(value) - _FIELDS if isinstance(value, Mapping) else set()
        raise FindingPackContractError(
            f"Finding Pack fields mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    normalized = dict(value)
    for field in ("finding_id", "run_id", "attempt_id", "decision_slot_id"):
        _identifier(normalized[field], field)
    if normalized["run_id"] != run_id:
        raise FindingPackContractError("Finding Pack belongs to another run")
    try:
        normalized["work_item_ref"] = validate_exact_artifact_ref(
            normalized["work_item_ref"], label="Finding Pack work_item_ref", run_id=run_id
        )
        normalized["blueprint_target_ref"] = validate_exact_artifact_ref(
            normalized["blueprint_target_ref"],
            label="Finding Pack blueprint_target_ref",
            run_id=run_id,
        )
    except ValueError as error:
        raise FindingPackContractError(str(error)) from error

    observations = normalized["observations"]
    if not isinstance(observations, list) or not observations:
        raise FindingPackContractError("Finding Pack requires observations")
    observation_ids: set[str] = set()
    parsed_observations: list[dict[str, Any]] = []
    for index, item in enumerate(observations):
        if not isinstance(item, Mapping) or set(item) != _OBSERVATION_FIELDS:
            raise FindingPackContractError(f"observation {index} fields mismatch")
        observation = dict(item)
        observation_id = observation["observation_id"]
        _identifier(observation_id, f"observation {index} id")
        if observation_id in observation_ids:
            raise FindingPackContractError("observation ids must be unique")
        observation_ids.add(observation_id)
        statement_class = observation["class"]
        if statement_class not in {"fact", "inference", "recommendation", "unknown"}:
            raise FindingPackContractError("observation class is unsupported")
        if not isinstance(observation["claim"], str) or not observation["claim"].strip():
            raise FindingPackContractError("observation claim is required")
        anchors = observation["anchors"]
        if not isinstance(anchors, list):
            raise FindingPackContractError("observation anchors must be an array")
        try:
            parsed_anchors = [
                ResolvableEvidenceAnchor.from_mapping(anchor).to_dict()
                for anchor in anchors
            ]
        except (EvidenceError, TypeError) as error:
            raise FindingPackContractError(str(error)) from error
        assumptions = _strings(observation["assumptions"], "observation assumptions")
        limitations = _strings(observation["limitations"], "observation limitations")
        if statement_class in {"fact", "inference"} and not parsed_anchors:
            raise FindingPackContractError(f"{statement_class} requires evidence anchors")
        if statement_class == "inference" and not assumptions:
            raise FindingPackContractError("inference requires assumptions")
        if statement_class == "recommendation" and not all(
            isinstance(observation[field], str) and observation[field].strip()
            for field in ("consequence", "reversal_condition")
        ):
            raise FindingPackContractError(
                "recommendation requires consequence and reversal_condition"
            )
        if statement_class == "unknown" and not all(
            isinstance(observation[field], str) and observation[field].strip()
            for field in ("unknown_reason", "next_acquisition_method")
        ):
            raise FindingPackContractError(
                "unknown requires unknown_reason and next_acquisition_method"
            )
        if observation["confidence"] not in {"low", "medium", "high"}:
            raise FindingPackContractError("observation confidence is unsupported")
        observation["anchors"] = parsed_anchors
        observation["assumptions"] = assumptions
        observation["limitations"] = limitations
        parsed_observations.append(observation)
    normalized["observations"] = parsed_observations

    effects = normalized["option_effects"]
    if not isinstance(effects, list):
        raise FindingPackContractError("option_effects must be an array")
    parsed_effects: list[dict[str, Any]] = []
    for effect in effects:
        if not isinstance(effect, Mapping) or set(effect) != {
            "option", "effect", "observation_ids"
        }:
            raise FindingPackContractError("option effect fields mismatch")
        if not isinstance(effect["option"], str) or not effect["option"].strip():
            raise FindingPackContractError("option effect option is required")
        if effect["effect"] not in {"supports", "contradicts", "neutral"}:
            raise FindingPackContractError("option effect is unsupported")
        refs = _strings(effect["observation_ids"], "option effect observation_ids")
        if not refs or not set(refs) <= observation_ids:
            raise FindingPackContractError("option effect references unknown observations")
        parsed_effects.append({**dict(effect), "observation_ids": refs})
    normalized["option_effects"] = parsed_effects
    normalized["implementation_implications"] = _strings(
        normalized["implementation_implications"], "implementation_implications"
    )

    uncertainties = normalized["remaining_uncertainties"]
    if not isinstance(uncertainties, list):
        raise FindingPackContractError("remaining_uncertainties must be an array")
    for item in uncertainties:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"uncertainty_id", "statement", "next_method"}
            or not all(isinstance(item[field], str) and item[field].strip() for field in item)
        ):
            raise FindingPackContractError("remaining uncertainty is invalid")
        _identifier(item["uncertainty_id"], "remaining uncertainty id")

    continuations = normalized["research_continuations"]
    if not isinstance(continuations, list):
        raise FindingPackContractError("research_continuations must be an array")
    for item in continuations:
        if not isinstance(item, Mapping) or set(item) != {
            "action_kind", "objective", "trigger_ref"
        }:
            raise FindingPackContractError("research continuation fields mismatch")
        if item["action_kind"] not in ACTION_KINDS or not all(
            isinstance(item[field], str) and item[field].strip()
            for field in ("objective", "trigger_ref")
        ):
            raise FindingPackContractError("research continuation is invalid")

    oracle_refs = normalized["oracle_run_refs"]
    if not isinstance(oracle_refs, list):
        raise FindingPackContractError("oracle_run_refs must be an array")
    for item in oracle_refs:
        if not isinstance(item, Mapping) or set(item) != {
            "oracle_run_id", "payload_digest"
        }:
            raise FindingPackContractError("OracleRun reference fields mismatch")
        _identifier(item["oracle_run_id"], "OracleRun id")
        digest = item["payload_digest"]
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise FindingPackContractError("OracleRun payload digest is invalid")
    return json.loads(canonical_json_bytes(normalized).decode("utf-8"))


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise FindingPackContractError(f"{label} must be a string array")
    return list(value)


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise FindingPackContractError(f"{label} is not a canonical identifier")
    return value
