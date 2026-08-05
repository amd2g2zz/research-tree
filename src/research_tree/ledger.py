"""Persist atomic research findings and converge them into decision records."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .decision_map import BLUEPRINT_TARGET_KIND
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    validate_identifier,
)
from .storage import RunStore
from .work_items import WORK_ITEM_KIND
from .evidence import EvidenceResolver, ResolvableEvidenceAnchor


FINDING_PACK_KIND = "finding-pack"
DECISION_LEDGER_KIND = "decision-ledger-entry"
ANCHOR_KINDS = {"source", "repository", "input", "experiment", "finding", "evidence"}
OBSERVATION_ANCHOR_KINDS = ANCHOR_KINDS - {"finding"}
CONFIDENCES = {"low", "medium", "high"}
OPTION_EFFECTS = {"supports", "contradicts", "limits"}
DECISION_STATUSES = {"selected", "conditional", "deferred", "blocked"}
ALTERNATIVE_DISPOSITIONS = {"rejected", "deferred", "unresolved"}
VALIDATION_KINDS = {"test", "spike", "metric", "review"}
CONTINUATION_KINDS = {"deep_dive", "adversarial", "validation", "method_switch"}
VALIDATION_RESULTS = {"passed", "failed", "inconclusive"}


class FindingPackError(RuntimeStoreError):
    """Base error for invalid research observations."""


class InvalidFindingPackError(FindingPackError):
    """Raised before an unanchored worker report can be persisted."""


class DecisionLedgerError(RuntimeStoreError):
    """Base error for invalid decision convergence."""


class InvalidDecisionLedgerError(DecisionLedgerError):
    """Raised before an incomplete technical decision can be persisted."""


class FindingPackCompiler:
    """Validate one work result as atomic, option-relevant observations."""

    def __init__(self, store: RunStore, *, evidence_resolver: EvidenceResolver | None = None) -> None:
        self._store = store
        self._evidence_resolver = evidence_resolver or EvidenceResolver()

    def compile(
        self,
        *,
        round_id: str,
        finding_id: str,
        work_item: ArtifactRevision,
        observations: Sequence[Mapping[str, Any]],
        option_effects: Sequence[Mapping[str, Any]],
        implementation_implications: Sequence[str],
        remaining_uncertainties: Sequence[str],
        research_node_id: str | None = None,
        research_continuations: Sequence[Mapping[str, Any]] = (),
        validation_result: Mapping[str, Any] | None = None,
        evidence_artifacts: Sequence[Mapping[str, Any]] = (),
    ) -> ArtifactRevision:
        """Append a Finding Pack only after its claims are bounded and anchored."""

        try:
            snapshot = self._store.load_round(round_id)
            validate_identifier(finding_id, "finding_id")
            _ensure_id_compatibility(snapshot.artifacts, finding_id, FINDING_PACK_KIND, InvalidFindingPackError)
            work = _resolve_exact(
                snapshot.artifacts,
                work_item,
                WORK_ITEM_KIND,
                "work_item",
                InvalidFindingPackError,
            )
            if work.round_id != round_id:
                raise InvalidFindingPackError("work_item must belong to Finding Pack round")
            target = _work_target(snapshot.artifacts, work, InvalidFindingPackError)
            slot = _target_slot(target, work.payload.get("decision_slot_id"), InvalidFindingPackError)
            options = _string_sequence(
                slot.get("alternatives"),
                "slot alternatives",
                error_type=InvalidFindingPackError,
            )
            normalized_observations = _normalize_observations(observations, slot)
            _resolve_strict_evidence(normalized_observations, evidence_artifacts, self._evidence_resolver)
            payload = {
                "id": finding_id,
                "round_id": round_id,
                "work_item_id": work.id,
                "blueprint_target_id": target.id,
                "decision_slot_id": slot["id"],
                "observations": normalized_observations,
                "option_effects": _normalize_option_effects(option_effects, options),
                "implementation_implications": list(
                    _string_sequence(
                        implementation_implications,
                        "implementation_implications",
                        error_type=InvalidFindingPackError,
                    )
                ),
                "remaining_uncertainties": list(
                    _string_sequence(
                        remaining_uncertainties,
                        "remaining_uncertainties",
                        allow_empty=True,
                        error_type=InvalidFindingPackError,
                    )
                ),
                "research_node_id": (
                    None
                    if research_node_id is None
                    else _nonempty_string(
                        research_node_id,
                        "research_node_id",
                        InvalidFindingPackError,
                    )
                ),
                "research_continuations": _normalize_research_continuations(
                    research_continuations
                ),
                "validation_result": _normalize_validation_result(validation_result),
            }
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidFindingPackError(str(error)) from error

        work_ref = ArtifactRef(round_id, work.id, work.revision)
        target_ref = ArtifactRef(round_id, target.id, target.revision)
        return self._store.append_artifact(
            round_id,
            finding_id,
            FINDING_PACK_KIND,
            payload,
            parent_refs=(work_ref, target_ref),
        )


class DecisionLedgerCompiler:
    """Converge exact Finding Packs into immutable, reversible design decisions."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def converge(
        self,
        *,
        round_id: str,
        decision_id: str,
        blueprint_target: ArtifactRevision,
        decision_slot_id: str,
        finding_packs: Sequence[ArtifactRevision],
        status: str,
        selected_option: str | None,
        alternatives: Sequence[Mapping[str, Any]],
        anchors: Sequence[Mapping[str, Any]],
        design_consequence: str,
        repository_touchpoints: Sequence[Mapping[str, Any]],
        validation: Mapping[str, Any],
        change_tasks: Sequence[Mapping[str, Any]],
        assumptions: Sequence[str],
        fallback: str,
        reversal_condition: str,
        revision_reason: str,
    ) -> ArtifactRevision:
        """Persist one bounded decision without collapsing conflicting evidence."""

        try:
            snapshot = self._store.load_round(round_id)
            validate_identifier(decision_id, "decision_id")
            _ensure_id_compatibility(
                snapshot.artifacts,
                decision_id,
                DECISION_LEDGER_KIND,
                InvalidDecisionLedgerError,
            )
            target = _resolve_exact(
                snapshot.artifacts,
                blueprint_target,
                BLUEPRINT_TARGET_KIND,
                "blueprint_target",
                InvalidDecisionLedgerError,
            )
            if target.round_id != round_id:
                raise InvalidDecisionLedgerError("blueprint_target must belong to decision round")
            slot = _target_slot(target, decision_slot_id, InvalidDecisionLedgerError)
            slot_options = _string_sequence(slot.get("alternatives"), "slot alternatives")
            normalized_status = _enum(status, "status", DECISION_STATUSES, InvalidDecisionLedgerError)
            findings = _resolve_findings(
                snapshot.artifacts,
                finding_packs,
                round_id,
                target,
                slot["id"],
            )
            selected = _normalize_selected_option(
                selected_option,
                normalized_status,
                slot_options,
            )
            normalized_alternatives = _normalize_alternatives(
                alternatives,
                slot_options,
                selected,
            )
            normalized_anchors = _normalize_decision_anchors(anchors, findings)
            normalized_touchpoints = _normalize_touchpoints(
                repository_touchpoints,
                slot,
            )
            normalized_validation = _normalize_validation(validation)
            normalized_tasks = _normalize_change_tasks(change_tasks, slot)
            payload = {
                "id": decision_id,
                "round_id": round_id,
                "blueprint_target_id": target.id,
                "decision_slot_id": slot["id"],
                "status": normalized_status,
                "selected_option": selected,
                "alternatives": normalized_alternatives,
                "anchors": normalized_anchors,
                "design_consequence": _nonempty_string(
                    design_consequence,
                    "design_consequence",
                    InvalidDecisionLedgerError,
                ),
                "repository_touchpoints": normalized_touchpoints,
                "validation": normalized_validation,
                "change_tasks": normalized_tasks,
                "assumptions": list(
                    _string_sequence(assumptions, "assumptions", allow_empty=True)
                ),
                "fallback": _nonempty_string(fallback, "fallback", InvalidDecisionLedgerError),
                "reversal_condition": _nonempty_string(
                    reversal_condition,
                    "reversal_condition",
                    InvalidDecisionLedgerError,
                ),
                "revision_reason": _nonempty_string(
                    revision_reason,
                    "revision_reason",
                    InvalidDecisionLedgerError,
                ),
            }
            _validate_decision_trace(
                slot,
                findings,
                payload,
                InvalidDecisionLedgerError,
            )
            previous = _latest_artifact(snapshot.artifacts, decision_id, DECISION_LEDGER_KIND)
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidDecisionLedgerError(str(error)) from error

        target_ref = ArtifactRef(round_id, target.id, target.revision)
        finding_refs = tuple(
            ArtifactRef(round_id, finding.id, finding.revision) for finding in findings
        )
        parent_refs = (
            (ArtifactRef(round_id, previous.id, previous.revision),)
            if previous is not None
            else ()
        ) + (target_ref, *finding_refs)
        return self._store.append_artifact(
            round_id,
            decision_id,
            DECISION_LEDGER_KIND,
            payload,
            parent_refs=parent_refs,
        )


def _ensure_id_compatibility(
    artifacts: Sequence[ArtifactRevision],
    artifact_id: str,
    expected_kind: str,
    error_type: type[RuntimeStoreError],
) -> None:
    foreign = {
        artifact.kind
        for artifact in artifacts
        if artifact.id == artifact_id and artifact.kind != expected_kind
    }
    if foreign:
        raise error_type(
            f"artifact id {artifact_id!r} is already used by kinds: {sorted(foreign)}"
        )


def _resolve_exact(
    artifacts: Sequence[ArtifactRevision],
    artifact: ArtifactRevision,
    expected_kind: str,
    label: str,
    error_type: type[RuntimeStoreError],
) -> ArtifactRevision:
    if not isinstance(artifact, ArtifactRevision):
        raise error_type(f"{label} must be an ArtifactRevision")
    for stored in artifacts:
        if stored.id == artifact.id and stored.revision == artifact.revision:
            if stored != artifact:
                raise error_type(f"{label} does not match its stored revision")
            if stored.kind != expected_kind:
                raise error_type(f"{label} must be a {expected_kind} artifact")
            return stored
    raise error_type(f"{label} has not been persisted in this RunStore")


def _work_target(
    artifacts: Sequence[ArtifactRevision],
    work: ArtifactRevision,
    error_type: type[RuntimeStoreError],
) -> ArtifactRevision:
    expected_id = work.payload.get("blueprint_target_id")
    if not isinstance(expected_id, str):
        raise error_type("work_item has no blueprint_target_id")
    by_ref = {(artifact.id, artifact.revision): artifact for artifact in artifacts}
    for reference in work.parent_refs:
        if reference.artifact_id != expected_id:
            continue
        target = by_ref.get((reference.artifact_id, reference.revision))
        if target is not None and target.kind == BLUEPRINT_TARGET_KIND:
            return target
    raise error_type("work_item has no exact Blueprint Target parent reference")


def _target_slot(
    target: ArtifactRevision,
    slot_id_value: Any,
    error_type: type[RuntimeStoreError],
) -> Mapping[str, Any]:
    slot_id = _identifier(slot_id_value, "decision_slot_id", error_type)
    slots = _mapping_sequence(target.payload.get("slots"), "blueprint_target slots", error_type)
    for slot in slots:
        if slot.get("id") == slot_id:
            return slot
    raise error_type(f"Decision Slot is absent from Blueprint Target: {slot_id}")


def _normalize_observations(
    value: Any,
    slot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    observations = _mapping_sequence(value, "observations", InvalidFindingPackError)
    if not observations:
        raise InvalidFindingPackError("Finding Pack requires at least one atomic observation")
    normalized: list[dict[str, Any]] = []
    for index, observation in enumerate(observations):
        label = f"observations[{index}]"
        _require_exact_keys(
            observation,
            {"claim", "anchor", "applicability", "confidence", "limitation"},
            label,
            InvalidFindingPackError,
        )
        anchor = _normalize_anchor(
            observation["anchor"],
            label,
            OBSERVATION_ANCHOR_KINDS,
            InvalidFindingPackError,
        )
        if anchor["kind"] == "repository":
            _validate_repository_anchor(anchor["ref"], slot, InvalidFindingPackError)
        normalized.append(
            {
                "claim": _nonempty_string(observation["claim"], f"{label}.claim", InvalidFindingPackError),
                "anchor": anchor,
                "applicability": _nonempty_string(
                    observation["applicability"],
                    f"{label}.applicability",
                    InvalidFindingPackError,
                ),
                "confidence": _enum(
                    observation["confidence"],
                    f"{label}.confidence",
                    CONFIDENCES,
                    InvalidFindingPackError,
                ),
                "limitation": _nonempty_string(
                    observation["limitation"],
                    f"{label}.limitation",
                    InvalidFindingPackError,
                ),
            }
        )
    return normalized


def _normalize_option_effects(value: Any, options: tuple[str, ...]) -> list[dict[str, str]]:
    effects = _mapping_sequence(value, "option_effects", InvalidFindingPackError)
    if not effects:
        raise InvalidFindingPackError("Finding Pack requires at least one option effect")
    normalized: list[dict[str, str]] = []
    for index, effect in enumerate(effects):
        label = f"option_effects[{index}]"
        _require_exact_keys(effect, {"option", "effect"}, label, InvalidFindingPackError)
        option = _nonempty_string(effect["option"], f"{label}.option", InvalidFindingPackError)
        if option not in options:
            raise InvalidFindingPackError(f"{label}.option is absent from the Decision Slot")
        normalized.append(
            {
                "option": option,
                "effect": _enum(effect["effect"], f"{label}.effect", OPTION_EFFECTS, InvalidFindingPackError),
            }
        )
    return normalized


def _normalize_research_continuations(value: Any) -> list[dict[str, Any]]:
    continuations = _mapping_sequence(
        value,
        "research_continuations",
        InvalidFindingPackError,
    )
    normalized: list[dict[str, Any]] = []
    for index, continuation in enumerate(continuations):
        label = f"research_continuations[{index}]"
        _require_exact_keys(
            continuation,
            {
                "kind",
                "question",
                "trigger",
                "evidence_needed",
                "oracle",
                "estimated_cost",
            },
            label,
            InvalidFindingPackError,
        )
        cost = continuation["estimated_cost"]
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost <= 0:
            raise InvalidFindingPackError(f"{label}.estimated_cost must be positive")
        normalized.append(
            {
                "kind": _enum(
                    continuation["kind"],
                    f"{label}.kind",
                    CONTINUATION_KINDS,
                    InvalidFindingPackError,
                ),
                "question": _nonempty_string(
                    continuation["question"],
                    f"{label}.question",
                    InvalidFindingPackError,
                ),
                "trigger": _nonempty_string(
                    continuation["trigger"],
                    f"{label}.trigger",
                    InvalidFindingPackError,
                ),
                "evidence_needed": _nonempty_string(
                    continuation["evidence_needed"],
                    f"{label}.evidence_needed",
                    InvalidFindingPackError,
                ),
                "oracle": _nonempty_string(
                    continuation["oracle"],
                    f"{label}.oracle",
                    InvalidFindingPackError,
                ),
                "estimated_cost": float(cost),
            }
        )
    return normalized


def _normalize_validation_result(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise InvalidFindingPackError("validation_result must be a mapping or null")
    _require_exact_keys(
        value,
        {"status", "oracle", "evidence_ref"},
        "validation_result",
        InvalidFindingPackError,
    )
    return {
        "status": _enum(
            value["status"],
            "validation_result.status",
            VALIDATION_RESULTS,
            InvalidFindingPackError,
        ),
        "oracle": _nonempty_string(
            value["oracle"],
            "validation_result.oracle",
            InvalidFindingPackError,
        ),
        "evidence_ref": _nonempty_string(
            value["evidence_ref"],
            "validation_result.evidence_ref",
            InvalidFindingPackError,
        ),
    }


def _resolve_findings(
    artifacts: Sequence[ArtifactRevision],
    values: Any,
    round_id: str,
    target: ArtifactRevision,
    slot_id: str,
) -> tuple[ArtifactRevision, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise InvalidDecisionLedgerError("finding_packs must be a sequence")
    findings: list[ArtifactRevision] = []
    seen_ids: set[str] = set()
    target_ref = ArtifactRef(round_id, target.id, target.revision)
    for index, finding in enumerate(values):
        stored = _resolve_exact(
            artifacts,
            finding,
            FINDING_PACK_KIND,
            f"finding_packs[{index}]",
            InvalidDecisionLedgerError,
        )
        if stored.round_id != round_id:
            raise InvalidDecisionLedgerError("Finding Pack must belong to decision round")
        if stored.id in seen_ids:
            raise InvalidDecisionLedgerError("finding_packs cannot include two revisions of one id")
        seen_ids.add(stored.id)
        if (
            stored.payload.get("blueprint_target_id") != target.id
            or stored.payload.get("decision_slot_id") != slot_id
            or target_ref not in stored.parent_refs
        ):
            raise InvalidDecisionLedgerError(
                "Finding Pack must belong to the exact Blueprint Target and Decision Slot"
            )
        findings.append(stored)
    return tuple(findings)


def _normalize_selected_option(
    value: Any,
    status: str,
    options: tuple[str, ...],
) -> str | None:
    if status in {"selected", "conditional"}:
        selected = _nonempty_string(value, "selected_option", InvalidDecisionLedgerError)
        if selected not in options:
            raise InvalidDecisionLedgerError("selected_option is absent from the Decision Slot")
        return selected
    if value is not None:
        raise InvalidDecisionLedgerError("deferred or blocked decision must not select an option")
    return None


def _normalize_alternatives(
    value: Any,
    options: tuple[str, ...],
    selected: str | None,
) -> list[dict[str, str]]:
    alternatives = _mapping_sequence(value, "alternatives", InvalidDecisionLedgerError)
    if not alternatives:
        raise InvalidDecisionLedgerError("Decision Ledger entry requires at least one alternative")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, alternative in enumerate(alternatives):
        label = f"alternatives[{index}]"
        _require_exact_keys(
            alternative,
            {"option", "disposition", "reason"},
            label,
            InvalidDecisionLedgerError,
        )
        option = _nonempty_string(alternative["option"], f"{label}.option", InvalidDecisionLedgerError)
        if option not in options or option == selected or option in seen:
            raise InvalidDecisionLedgerError(f"{label}.option must be a distinct unselected slot option")
        seen.add(option)
        normalized.append(
            {
                "option": option,
                "disposition": _enum(
                    alternative["disposition"],
                    f"{label}.disposition",
                    ALTERNATIVE_DISPOSITIONS,
                    InvalidDecisionLedgerError,
                ),
                "reason": _nonempty_string(alternative["reason"], f"{label}.reason", InvalidDecisionLedgerError),
            }
        )
    return normalized


def _normalize_decision_anchors(
    value: Any,
    findings: Sequence[ArtifactRevision],
) -> list[dict[str, str]]:
    anchors = _mapping_sequence(value, "anchors", InvalidDecisionLedgerError)
    normalized: list[dict[str, str]] = []
    finding_ids = {finding.id for finding in findings}
    for index, anchor_value in enumerate(anchors):
        anchor = _normalize_anchor(
            anchor_value,
            f"anchors[{index}]",
            ANCHOR_KINDS,
            InvalidDecisionLedgerError,
        )
        if anchor["kind"] == "finding" and anchor["ref"] not in finding_ids:
            raise InvalidDecisionLedgerError("finding anchor must refer to a supplied Finding Pack")
        normalized.append(anchor)
    return normalized


def _normalize_touchpoints(value: Any, slot: Mapping[str, Any]) -> list[dict[str, str | None]]:
    allowed = {
        (item.get("path"), item.get("symbol"))
        for item in _mapping_sequence(
            slot.get("repository_touchpoints"),
            "slot repository_touchpoints",
            InvalidDecisionLedgerError,
        )
    }
    points = _mapping_sequence(value, "repository_touchpoints", InvalidDecisionLedgerError)
    normalized: list[dict[str, str | None]] = []
    for index, point in enumerate(points):
        label = f"repository_touchpoints[{index}]"
        _require_exact_keys(point, {"path", "symbol"}, label, InvalidDecisionLedgerError)
        path = _nonempty_string(point["path"], f"{label}.path", InvalidDecisionLedgerError)
        symbol_raw = point["symbol"]
        if symbol_raw is not None and not isinstance(symbol_raw, str):
            raise InvalidDecisionLedgerError(f"{label}.symbol must be a string or null")
        symbol = None if symbol_raw is None else _nonempty_string(
            symbol_raw,
            f"{label}.symbol",
            InvalidDecisionLedgerError,
        )
        if allowed and (path, symbol) not in allowed:
            raise InvalidDecisionLedgerError(f"{label} is absent from the Decision Slot")
        normalized.append({"path": path, "symbol": symbol})
    if allowed and not normalized:
        raise InvalidDecisionLedgerError("repository-backed Decision Slot requires a touchpoint")
    return normalized


def _normalize_validation(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise InvalidDecisionLedgerError("validation must be a mapping")
    _require_exact_keys(value, {"kind", "oracle"}, "validation", InvalidDecisionLedgerError)
    return {
        "kind": _enum(value["kind"], "validation.kind", VALIDATION_KINDS, InvalidDecisionLedgerError),
        "oracle": _nonempty_string(value["oracle"], "validation.oracle", InvalidDecisionLedgerError),
    }


def _normalize_change_tasks(value: Any, slot: Mapping[str, Any]) -> list[dict[str, Any]]:
    tasks = _mapping_sequence(value, "change_tasks", InvalidDecisionLedgerError)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, task in enumerate(tasks):
        label = f"change_tasks[{index}]"
        _require_exact_keys(
            task,
            {"id", "description", "acceptance_oracle", "repository_touchpoints"},
            label,
            InvalidDecisionLedgerError,
        )
        task_id = _identifier(task["id"], f"{label}.id", InvalidDecisionLedgerError)
        if task_id in seen:
            raise InvalidDecisionLedgerError(f"duplicate change task id: {task_id}")
        seen.add(task_id)
        normalized.append(
            {
                "id": task_id,
                "description": _nonempty_string(task["description"], f"{label}.description", InvalidDecisionLedgerError),
                "acceptance_oracle": _nonempty_string(
                    task["acceptance_oracle"],
                    f"{label}.acceptance_oracle",
                    InvalidDecisionLedgerError,
                ),
                "repository_touchpoints": _normalize_touchpoints(
                    task["repository_touchpoints"],
                    slot,
                ),
            }
        )
    return normalized


def _validate_decision_trace(
    slot: Mapping[str, Any],
    findings: Sequence[ArtifactRevision],
    payload: Mapping[str, Any],
    error_type: type[RuntimeStoreError],
) -> None:
    if slot.get("priority") != "P0" or payload["status"] not in {"selected", "conditional"}:
        return
    finding_anchors = {
        anchor["ref"] for anchor in payload["anchors"] if anchor["kind"] == "finding"
    }
    if not findings or not finding_anchors:
        raise error_type("P0 selected or conditional decision requires a supplied Finding Pack anchor")
    selected_option = payload["selected_option"]
    effects = {
        effect["option"]
        for finding in findings
        for effect in finding.payload.get("option_effects", ())
        if isinstance(effect, Mapping) and isinstance(effect.get("option"), str)
    }
    if selected_option not in effects:
        raise error_type(
            "P0 selected or conditional decision requires a Finding Pack effect for selected_option"
        )
    if not payload["change_tasks"]:
        raise error_type("P0 selected or conditional decision requires at least one change task")


def _latest_artifact(
    artifacts: Sequence[ArtifactRevision], artifact_id: str, kind: str
) -> ArtifactRevision | None:
    matches = [artifact for artifact in artifacts if artifact.id == artifact_id and artifact.kind == kind]
    return max(matches, key=lambda artifact: artifact.revision, default=None)


def _normalize_anchor(
    value: Any,
    label: str,
    allowed_kinds: set[str],
    error_type: type[RuntimeStoreError],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise error_type(f"{label}.anchor must be a mapping")
    if set(value) == {
        "artifact_digest", "artifact_revision", "selector_type", "selector_value",
        "extractor_version", "applicability", "confidence", "limitations",
    }:
        try:
            evidence = ResolvableEvidenceAnchor.from_mapping(value)
        except ValueError as exc:
            raise error_type(str(exc)) from exc
        return {
            "kind": "evidence",
            "ref": evidence.artifact_digest,
            "evidence": evidence.to_dict(),
        }
    if "evidence" in value:
        _require_exact_keys(value, {"kind", "ref", "evidence"}, f"{label}.anchor", error_type)
        try:
            evidence = ResolvableEvidenceAnchor.from_mapping(value["evidence"])
        except (TypeError, ValueError) as exc:
            raise error_type(str(exc)) from exc
        return {
            "kind": _enum(value["kind"], f"{label}.anchor.kind", allowed_kinds, error_type),
            "ref": _nonempty_string(value["ref"], f"{label}.anchor.ref", error_type),
            "evidence": evidence.to_dict(),
        }
    _require_exact_keys(value, {"kind", "ref"}, f"{label}.anchor", error_type)
    return {
        "kind": _enum(value["kind"], f"{label}.anchor.kind", allowed_kinds, error_type),
        "ref": _nonempty_string(value["ref"], f"{label}.anchor.ref", error_type),
    }


def _resolve_strict_evidence(
    observations: Sequence[Mapping[str, Any]],
    artifacts: Sequence[Mapping[str, Any]],
    resolver: EvidenceResolver,
) -> None:
    candidates = list(artifacts)
    for index, observation in enumerate(observations):
        anchor = observation.get("anchor", {})
        if anchor.get("kind") != "evidence":
            continue
        evidence = anchor.get("evidence")
        if not isinstance(evidence, Mapping):
            raise InvalidFindingPackError(f"observations[{index}] evidence anchor is not resolvable")
        digest = evidence.get("artifact_digest")
        matching = [
            artifact for artifact in candidates
            if isinstance(artifact, Mapping)
            and (artifact.get("content_digest") or artifact.get("artifact_digest")) == digest
            and artifact.get("revision", 1) == evidence.get("artifact_revision")
        ]
        if len(matching) != 1:
            raise InvalidFindingPackError(
                f"observations[{index}] requires exactly one matching Evidence Artifact"
            )
        try:
            resolver.resolve(evidence, matching[0])
        except (TypeError, ValueError) as error:
            raise InvalidFindingPackError(str(error)) from error


def _validate_repository_anchor(
    value: str,
    slot: Mapping[str, Any],
    error_type: type[RuntimeStoreError],
) -> None:
    allowed = {
        f"{item.get('path')}:{item.get('symbol')}"
        for item in _mapping_sequence(
            slot.get("repository_touchpoints"),
            "slot repository_touchpoints",
            error_type,
        )
        if item.get("symbol") is not None
    }
    allowed.update(
        str(item.get("path"))
        for item in _mapping_sequence(
            slot.get("repository_touchpoints"),
            "slot repository_touchpoints",
            error_type,
        )
    )
    if value not in allowed:
        raise error_type("repository observation anchor is absent from the Decision Slot")


def _mapping_sequence(
    value: Any,
    label: str,
    error_type: type[RuntimeStoreError],
) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise error_type(f"{label} must be a sequence of mappings")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise error_type(f"{label}[{index}] must be a mapping")
        result.append(item)
    return result


def _string_sequence(
    value: Any,
    label: str,
    *,
    allow_empty: bool = False,
    error_type: type[RuntimeStoreError] = InvalidDecisionLedgerError,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise error_type(f"{label} must be a sequence of strings")
    result = tuple(_nonempty_string(item, label, error_type) for item in value)
    if not result and not allow_empty:
        raise error_type(f"{label} must not be empty")
    return result


def _identifier(value: Any, label: str, error_type: type[RuntimeStoreError]) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise error_type(str(error)) from error


def _enum(
    value: Any,
    label: str,
    allowed: set[str],
    error_type: type[RuntimeStoreError],
) -> str:
    normalized = _nonempty_string(value, label, error_type)
    if normalized not in allowed:
        raise error_type(f"{label} is unsupported: {normalized}")
    return normalized


def _nonempty_string(value: Any, label: str, error_type: type[RuntimeStoreError]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{label} must be a nonempty string")
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    label: str,
    error_type: type[RuntimeStoreError],
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise error_type(f"{label} has unexpected keys; missing={missing}, extra={extra}")
