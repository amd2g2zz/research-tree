"""Semantic validation and typed acceptance for co-primary deliveries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .domain import canonical_json_bytes, thaw_json


class AcceptanceError(ValueError):
    """Raised when a delivery pair or acceptance decision is not authoritative."""


CANONICAL_TECHNICAL_KIND = "technical-research-package"
CANONICAL_HUMAN_KIND = "human-research-report"
CLAIM_CLASSES = frozenset({"fact", "inference", "recommendation", "unknown", "limitation"})
DEPTH_DIMENSIONS = (
    "problem_fidelity",
    "evidence_quality",
    "counterevidence",
    "alternatives_tradeoffs",
    "implementation_boundary",
    "risks_failure_modes",
    "validation_path",
    "uncertainties",
    "operational_meaning",
)
ACCEPTANCE_DECISIONS = frozenset(
    {
        "accepted",
        "rejected",
        "needs_deeper_research",
        "needs_intent_correction",
        "partially_accepted",
    }
)
FEEDBACK_CLASSES = frozenset(
    {
        "evidence",
        "method",
        "depth",
        "applicability",
        "presentation",
        "objective",
        "target",
        "scope",
        "authority",
        "intended_use",
        "success_criteria",
        "withdrawal",
    }
)
SUCCESSOR_FEEDBACK_CLASSES = frozenset(
    {"objective", "target", "scope", "authority", "intended_use", "success_criteria"}
)
GENERIC_ACKNOWLEDGEMENTS = frozenset({"ok", "okay", "yes", "continue", "go ahead", "fine", "looks good", "approved"})
_HASH = re.compile(r"^[0-9a-f]{64}$")


def delivery_pair_digest(run_id: str, technical_revision: str, human_revision: str) -> str:
    """Bind the exact co-primary pair using the public canonical digest rule."""

    return sha256(
        canonical_json_bytes(
            {
                "run_id": _nonempty(run_id, "run_id"),
                "technical_revision": _nonempty(technical_revision, "technical_revision"),
                "human_revision": _nonempty(human_revision, "human_revision"),
            }
        )
    ).hexdigest()


def validate_semantic_deliveries(technical: Mapping[str, Any], human: Mapping[str, Any]) -> dict[str, Any]:
    """Validate semantic closure and lineage without prose-length proxies."""

    technical = _mapping(technical, "technical delivery")
    human = _mapping(human, "human delivery")
    if technical.get("kind") != CANONICAL_TECHNICAL_KIND:
        raise AcceptanceError("technical delivery has a non-canonical kind")
    if human.get("kind") != CANONICAL_HUMAN_KIND:
        raise AcceptanceError("human delivery has a non-canonical kind")

    technical_manifest = _mapping(technical.get("manifest"), "technical manifest")
    human_manifest = _mapping(human.get("manifest"), "human manifest")
    if canonical_json_bytes(thaw_json(technical_manifest)) != canonical_json_bytes(thaw_json(human_manifest)):
        raise AcceptanceError("delivery manifest mismatch: both surfaces must bind one pair")
    manifest = _validate_manifest(technical_manifest)
    _verify_rendered_output(technical, manifest, "technical")
    _verify_rendered_output(human, manifest, "human")

    technical_document = _mapping(technical.get("document"), "technical document")
    human_document = _mapping(human.get("document"), "human document")
    claim_index = _sequence(manifest["claim_index"], "manifest claim_index")
    claims_by_text = _validate_claim_index(claim_index)

    orphan_claims: list[str] = []
    for finding in _sequence(technical_document.get("research_findings", []), "research_findings"):
        finding_record = _mapping(finding, "research finding")
        for observation in _sequence(finding_record.get("observations", []), "finding observations"):
            observation_record = _mapping(observation, "finding observation")
            text = _nonempty(observation_record.get("claim"), "finding claim")
            if _normalize_text(text) not in claims_by_text:
                orphan_claims.append(text)
    if orphan_claims:
        raise AcceptanceError(
            "orphan_claim: consequential findings lack claim-index lineage: " + "; ".join(orphan_claims)
        )

    unresolved_p0 = [
        str(item.get("decision_slot_id", "unknown"))
        for item in (
            _mapping(value, "blueprint closure")
            for value in _sequence(technical_document.get("blueprint_closure", []), "blueprint_closure")
        )
        if item.get("priority") == "P0" and item.get("status") != "selected"
    ]
    if unresolved_p0:
        raise AcceptanceError(
            "unresolved_p0: final delivery cannot close conditional or open P0 slots: " + ", ".join(unresolved_p0)
        )

    missing_boundaries: list[str] = []
    for index, value in enumerate(_sequence(technical_document.get("implementation_plan", []), "implementation_plan")):
        item = _mapping(value, f"implementation_plan[{index}]")
        touchpoints = _sequence(
            item.get("repository_touchpoints", []),
            f"implementation_plan[{index}].repository_touchpoints",
        )
        greenfield = item.get("greenfield_validation_boundary")
        if not touchpoints and not (isinstance(greenfield, str) and greenfield.strip()):
            missing_boundaries.append(str(item.get("description", index)))
    if missing_boundaries:
        raise AcceptanceError(
            "implementation_boundary: implementation work lacks repository touchpoints "
            "or an explicit greenfield validation boundary: " + "; ".join(missing_boundaries)
        )

    _validate_human_reasoning(human_document)
    assessments = _validate_depth_assessments(manifest["depth_assessments"])
    failed = [item["dimension"] for item in assessments if item["status"] != "pass"]
    if failed:
        raise AcceptanceError("depth_assessment: mandatory dimensions are not ready: " + ", ".join(failed))
    return {
        "status": "semantically_ready",
        "technical_revision": manifest["technical_revision"],
        "human_revision": manifest["human_revision"],
        "source_ledger_digest": manifest["source_ledger_digest"],
        "claim_count": len(claim_index),
        "depth_assessments": assessments,
        "diagnostics": [],
    }


def _validate_manifest(value: Mapping[str, Any]) -> Mapping[str, Any]:
    required = {
        "technical_revision",
        "human_revision",
        "source_ledger_digest",
        "compiler_version",
        "template_version",
        "encoding",
        "output_paths",
        "generated_at",
        "claim_index",
        "depth_assessments",
    }
    missing = sorted(required - set(value))
    if missing:
        raise AcceptanceError("delivery manifest is incomplete: " + ", ".join(missing))
    for field in ("technical_revision", "human_revision", "compiler_version", "template_version", "generated_at"):
        _nonempty(value[field], f"manifest {field}")
    _hash(value["source_ledger_digest"], "manifest source_ledger_digest")
    if value["encoding"] != "UTF-8":
        raise AcceptanceError("delivery manifest encoding must be UTF-8")
    outputs = _mapping(value["output_paths"], "manifest output_paths")
    for surface in ("technical", "human"):
        output = _mapping(outputs.get(surface), f"manifest output_paths.{surface}")
        _nonempty(output.get("locator"), f"manifest {surface} locator")
        _hash(output.get("sha256"), f"manifest {surface} sha256")
    return value


def _verify_rendered_output(delivery: Mapping[str, Any], manifest: Mapping[str, Any], surface: str) -> None:
    markdown = delivery.get("markdown")
    if markdown is None:
        return
    markdown = _nonempty(markdown, f"{surface} markdown")
    expected = _mapping(manifest["output_paths"], "output paths")[surface]["sha256"]
    actual = sha256(markdown.encode("utf-8")).hexdigest()
    if actual != expected:
        raise AcceptanceError(f"stale_delivery: {surface} output digest does not match manifest")


def _validate_claim_index(values: Sequence[Any]) -> dict[str, list[Mapping[str, Any]]]:
    if not values:
        raise AcceptanceError("claim_index must contain consequential claims")
    seen_ids: set[str] = set()
    by_text: dict[str, list[Mapping[str, Any]]] = {}
    for index, value in enumerate(values):
        claim = _mapping(value, f"claim_index[{index}]")
        claim_id = _nonempty(claim.get("claim_id"), f"claim_index[{index}].claim_id")
        if claim_id in seen_ids:
            raise AcceptanceError(f"claim_index repeats claim_id {claim_id}")
        seen_ids.add(claim_id)
        claim_class = claim.get("class")
        if claim_class not in CLAIM_CLASSES:
            raise AcceptanceError(f"claim_index[{index}] has unsupported class")
        text = _nonempty(claim.get("text"), f"claim_index[{index}].text")
        surfaces = _string_list(claim.get("surfaces"), f"claim_index[{index}].surfaces")
        selectors = _string_list(claim.get("selectors"), f"claim_index[{index}].selectors")
        if not surfaces or not selectors:
            raise AcceptanceError(f"claim_index[{index}] requires surfaces and selectors")
        decision_refs = _string_list(claim.get("decision_refs", []), f"claim_index[{index}].decision_refs")
        finding_refs = _string_list(claim.get("finding_refs", []), f"claim_index[{index}].finding_refs")
        evidence_refs = _string_list(claim.get("evidence_refs", []), f"claim_index[{index}].evidence_refs")
        oracle_refs = _string_list(claim.get("oracle_refs", []), f"claim_index[{index}].oracle_refs")
        if claim_class == "fact" and not (evidence_refs or oracle_refs):
            raise AcceptanceError(f"orphan_claim: fact {claim_id} lacks evidence or oracle lineage")
        if claim_class == "inference" and not ((evidence_refs or oracle_refs) and (decision_refs or finding_refs)):
            raise AcceptanceError(f"orphan_claim: inference {claim_id} lacks its reasoning basis")
        if claim_class == "recommendation":
            if not decision_refs:
                raise AcceptanceError(f"orphan_claim: recommendation {claim_id} lacks a decision")
            if not _meaningful_optional(claim.get("boundary_ref")):
                raise AcceptanceError(f"implementation_boundary: recommendation {claim_id} lacks a boundary")
        if claim_class in {"unknown", "limitation"} and not (
            _meaningful_optional(claim.get("next_validation")) or evidence_refs or oracle_refs
        ):
            raise AcceptanceError(f"orphan_claim: {claim_class} {claim_id} lacks evidence or next validation")
        by_text.setdefault(_normalize_text(text), []).append(claim)
    return by_text


def _validate_human_reasoning(document: Mapping[str, Any]) -> None:
    required = (
        "what_was_understood",
        "evidence_and_reasoning",
        "recommended_direction",
        "alternatives_and_tradeoffs",
        "expected_capability",
        "applicability",
        "implementation_meaning",
        "risks_and_uncertainty",
    )
    missing = [field for field in required if not _meaningful(document.get(field))]
    if missing:
        raise AcceptanceError("shallow_human_reasoning: missing professional reasoning surfaces: " + ", ".join(missing))
    evidence = _sequence(document["evidence_and_reasoning"], "human evidence_and_reasoning")
    for index, value in enumerate(evidence):
        item = _mapping(value, f"human evidence_and_reasoning[{index}]")
        for field in ("claim", "reasoning", "limitation"):
            _nonempty(item.get(field), f"human evidence_and_reasoning[{index}].{field}")
        if not _string_list(
            item.get("evidence_refs", []),
            f"human evidence_and_reasoning[{index}].evidence_refs",
        ):
            raise AcceptanceError("shallow_human_reasoning: evidence-backed reasoning lacks evidence refs")
    meaning = _mapping(document["implementation_meaning"], "human implementation_meaning")
    for field in ("first_slice", "touchpoints", "validation", "blockers"):
        if not _meaningful(meaning.get(field)):
            raise AcceptanceError(f"shallow_human_reasoning: implementation_meaning.{field} is missing")


def _validate_depth_assessments(value: Any) -> list[dict[str, Any]]:
    records = _sequence(value, "depth_assessments")
    by_dimension: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(records):
        item = _mapping(value, f"depth_assessments[{index}]")
        dimension = item.get("dimension")
        if dimension not in DEPTH_DIMENSIONS or dimension in by_dimension:
            raise AcceptanceError("depth_assessment contains an unknown or repeated dimension")
        status = item.get("status")
        if status not in {"pass", "fail", "unknown"}:
            raise AcceptanceError(f"depth_assessment {dimension} has invalid status")
        evidence_refs = _string_list(item.get("evidence_refs", []), f"depth_assessment {dimension}.evidence_refs")
        diagnostic = _nonempty(item.get("diagnostic"), f"depth_assessment {dimension}.diagnostic")
        follow_up = item.get("follow_up")
        if status == "pass" and not evidence_refs:
            raise AcceptanceError(f"depth_assessment {dimension} pass lacks evidence refs")
        if status != "pass" and not _meaningful_optional(follow_up):
            raise AcceptanceError(f"depth_assessment {dimension} requires targeted follow-up")
        by_dimension[dimension] = {
            "dimension": dimension,
            "status": status,
            "evidence_refs": evidence_refs,
            "diagnostic": diagnostic,
            "follow_up": follow_up,
        }
    missing = [dimension for dimension in DEPTH_DIMENSIONS if dimension not in by_dimension]
    if missing:
        raise AcceptanceError("depth_assessment is incomplete: " + ", ".join(missing))
    return [by_dimension[dimension] for dimension in DEPTH_DIMENSIONS]


@dataclass(frozen=True, slots=True)
class DeliveryAcceptance:
    acceptance_id: str
    run_id: str
    technical_revision: str
    human_revision: str
    displayed_digest: str
    manifest_digest: str
    decision: str
    actor: str
    feedback: tuple[Mapping[str, Any], ...]
    lifecycle_action: str
    created_at: str

    @classmethod
    def create(
        cls,
        acceptance_id: str,
        run_id: str,
        technical_revision: str,
        human_revision: str,
        displayed_digest: str,
        manifest_digest: str,
        feedback: Sequence[Mapping[str, Any]],
        *,
        decision: str = "accepted",
        actor: str = "human",
    ) -> "DeliveryAcceptance":
        for label, value in (
            ("acceptance_id", acceptance_id),
            ("run_id", run_id),
            ("technical_revision", technical_revision),
            ("human_revision", human_revision),
            ("actor", actor),
        ):
            _nonempty(value, label)
        _hash(manifest_digest, "manifest_digest")
        if decision not in ACCEPTANCE_DECISIONS:
            raise AcceptanceError("unsupported acceptance decision")
        expected = delivery_pair_digest(run_id, technical_revision, human_revision)
        if displayed_digest != expected:
            raise AcceptanceError("stale acceptance digest does not bind the exact delivery pair")
        normalized_feedback = _validate_feedback(feedback)
        statements = {_normalize_text(item["statement"]) for item in normalized_feedback}
        if any(statement in GENERIC_ACKNOWLEDGEMENTS for statement in statements):
            raise AcceptanceError("generic acknowledgement cannot accept a delivery")
        classifications = {item["classification"] for item in normalized_feedback}
        if decision == "accepted":
            if classifications & (
                SUCCESSOR_FEEDBACK_CLASSES | {"withdrawal", "depth", "evidence", "method", "applicability"}
            ):
                raise AcceptanceError("accepted decision conflicts with corrective feedback")
            lifecycle_action = "complete"
        elif decision == "needs_intent_correction":
            if not classifications & SUCCESSOR_FEEDBACK_CLASSES:
                raise AcceptanceError("intent correction requires target, scope, or intent feedback")
            lifecycle_action = "successor_round"
        elif classifications & SUCCESSOR_FEEDBACK_CLASSES:
            lifecycle_action = "successor_round"
        elif decision == "partially_accepted" and classifications <= {"presentation"}:
            lifecycle_action = "awaiting_acceptance"
        else:
            lifecycle_action = "same_round_research"
        return cls(
            acceptance_id=acceptance_id,
            run_id=run_id,
            technical_revision=technical_revision,
            human_revision=human_revision,
            displayed_digest=displayed_digest,
            manifest_digest=manifest_digest,
            decision=decision,
            actor=actor,
            feedback=tuple(normalized_feedback),
            lifecycle_action=lifecycle_action,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "acceptance_id": self.acceptance_id,
            "run_id": self.run_id,
            "technical_revision": self.technical_revision,
            "human_revision": self.human_revision,
            "displayed_digest": self.displayed_digest,
            "manifest_digest": self.manifest_digest,
            "decision": self.decision,
            "actor": self.actor,
            "feedback": [dict(item) for item in self.feedback],
            "lifecycle_action": self.lifecycle_action,
            "created_at": self.created_at,
        }


def _validate_feedback(value: Any) -> list[dict[str, Any]]:
    records = _sequence(value, "feedback")
    if not records:
        raise AcceptanceError("acceptance requires contextual feedback")
    result: list[dict[str, Any]] = []
    for index, value in enumerate(records):
        item = _mapping(value, f"feedback[{index}]")
        feedback_id = _nonempty(item.get("feedback_id"), f"feedback[{index}].feedback_id")
        classification = item.get("classification")
        if classification not in FEEDBACK_CLASSES:
            raise AcceptanceError(f"feedback[{index}] has unsupported classification")
        statement = _nonempty(item.get("statement"), f"feedback[{index}].statement")
        target_refs = _string_list(item.get("target_refs", []), f"feedback[{index}].target_refs")
        result.append(
            {
                "feedback_id": feedback_id,
                "classification": classification,
                "statement": statement,
                "target_refs": target_refs,
            }
        )
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AcceptanceError(f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AcceptanceError(f"{label} must be an array")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    items = _sequence(value, label)
    result: list[str] = []
    for index, item in enumerate(items):
        result.append(_nonempty(item, f"{label}[{index}]"))
    return result


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AcceptanceError(f"{label} must be nonempty")
    return value.strip()


def _hash(value: Any, label: str) -> str:
    value = _nonempty(value, label)
    if not _HASH.fullmatch(value):
        raise AcceptanceError(f"{label} must be a SHA-256 digest")
    return value


def _meaningful(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value) and any(_meaningful(child) for child in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return bool(value) and any(_meaningful(child) for child in value)
    return value is not None


def _meaningful_optional(value: Any) -> bool:
    return value is not None and _meaningful(value)


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())
