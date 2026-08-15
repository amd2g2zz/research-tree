"""Compile bounded, traceable Blueprint Targets from a Working Brief."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    thaw_json,
    validate_identifier,
)
from .intake import INPUT_LEDGER_ARTIFACT_KIND
from .intent import INTENT_MODEL_KIND, WORKING_BRIEF_KIND
from .run_ledger import RunLedger


BLUEPRINT_TARGET_KIND = "blueprint-target"
SLOT_KINDS = {
    "architecture",
    "interface",
    "state",
    "security",
    "migration",
    "validation",
    "operations",
    "other",
}
PRIORITIES = {"P0", "P1", "P2"}
LEVELS = {"low", "medium", "high"}
SLOT_STATUSES = {"open", "researching", "selected", "conditional", "deferred", "blocked"}
VALIDATION_KINDS = {"test", "spike", "metric", "review"}
CONSTRAINT_KINDS = {"input", "repository", "assumption"}
CHANGE_KINDS = {"initial", "add", "split", "merge", "remove", "reprioritize"}


class BlueprintTargetError(RuntimeStoreError):
    """Base error for Blueprint Target compilation failures."""


class InvalidBlueprintTargetError(BlueprintTargetError):
    """Raised before a Decision Map contract violation can be persisted."""


class CanonicalBlueprintTargetCompiler:
    """Persist immutable Blueprint Targets directly in the canonical ledger."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise InvalidBlueprintTargetError("canonical Blueprint Target compiler requires a RunLedger")
        self._ledger = ledger

    def compile(
        self,
        *,
        round_id: str,
        target_id: str,
        working_brief: ArtifactRevision,
        slots: Sequence[Mapping[str, Any]],
        change: Mapping[str, Any],
        expected_revision: int,
    ) -> ArtifactRevision:
        """Append one lineage-bound target revision with an explicit precondition."""

        try:
            snapshot = self._ledger.load_run(round_id)
            validate_identifier(target_id, "target_id")
            foreign_kinds = {
                artifact.kind
                for artifact in snapshot.artifacts
                if artifact.id == target_id and artifact.kind != BLUEPRINT_TARGET_KIND
            }
            if foreign_kinds:
                raise InvalidBlueprintTargetError(
                    f"target_id {target_id!r} is already used by artifact kinds: {sorted(foreign_kinds)}"
                )
            brief = _resolve_exact_artifact(snapshot.artifacts, working_brief)
            if brief.kind != WORKING_BRIEF_KIND:
                raise InvalidBlueprintTargetError("working_brief must be a working-brief artifact")
            if brief.round_id != round_id:
                raise InvalidBlueprintTargetError("working_brief must belong to target round")

            model = _resolve_brief_model(snapshot.artifacts, brief)
            brief_inputs = _resolve_brief_inputs(snapshot.artifacts, brief)
            normalized_slots = _normalize_slots(
                slots,
                visible_hypotheses=_brief_hypothesis_ids(brief, model),
                selected_input_ids=_brief_selected_input_ids(brief),
                repository_anchors=_repository_anchors(brief_inputs),
            )
            _validate_dependencies(normalized_slots)
            previous_target = _latest_target(snapshot.artifacts, target_id)
            if previous_target is not None and not _shares_exact_brief_model_lineage(previous_target, brief, model):
                raise InvalidBlueprintTargetError(
                    "later Blueprint Target revisions must retain the prior Brief and Intent Model lineage"
                )
            normalized_change = _normalize_change(change)
            _validate_change(previous_target, normalized_slots, normalized_change)
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidBlueprintTargetError(str(error)) from error

        payload = {
            "id": target_id,
            "round_id": round_id,
            "brief_id": brief.id,
            "intent_model_id": model.id,
            "slots": normalized_slots,
            "change": normalized_change,
        }
        brief_ref = ArtifactRef(round_id, brief.id, brief.revision)
        model_ref = ArtifactRef(round_id, model.id, model.revision)
        parent_refs = (
            (brief_ref, model_ref)
            if previous_target is None
            else (ArtifactRef(round_id, previous_target.id, previous_target.revision), brief_ref, model_ref)
        )
        return self._ledger.append_artifact(
            round_id,
            target_id,
            BLUEPRINT_TARGET_KIND,
            payload,
            parent_refs=parent_refs,
            expected_revision=expected_revision,
        )


def _resolve_exact_artifact(
    artifacts: Sequence[ArtifactRevision], artifact: ArtifactRevision
) -> ArtifactRevision:
    if not isinstance(artifact, ArtifactRevision):
        raise InvalidBlueprintTargetError("working_brief must be an ArtifactRevision")
    for stored in artifacts:
        if stored.id == artifact.id and stored.revision == artifact.revision:
            if stored != artifact:
                raise InvalidBlueprintTargetError("working_brief does not match its stored revision")
            return stored
    raise InvalidBlueprintTargetError("working_brief has not been persisted in this RunStore")


def _resolve_brief_model(
    artifacts: Sequence[ArtifactRevision], brief: ArtifactRevision
) -> ArtifactRevision:
    model_id = _identifier(
        brief.payload.get("intent_model_id"), "working_brief intent_model_id"
    )
    artifact_by_ref = {(artifact.id, artifact.revision): artifact for artifact in artifacts}
    for reference in brief.parent_refs:
        if reference.artifact_id != model_id:
            continue
        model = artifact_by_ref.get((reference.artifact_id, reference.revision))
        if model is not None and model.kind == INTENT_MODEL_KIND:
            return model
    raise InvalidBlueprintTargetError("working_brief has no exact intent-model parent reference")


def _resolve_brief_inputs(
    artifacts: Sequence[ArtifactRevision], brief: ArtifactRevision
) -> tuple[ArtifactRevision, ...]:
    selected_ids = _brief_selected_input_ids(brief)
    artifact_by_ref = {(artifact.id, artifact.revision): artifact for artifact in artifacts}
    selected: list[ArtifactRevision] = []
    for input_id in selected_ids:
        references = [reference for reference in brief.parent_refs if reference.artifact_id == input_id]
        if len(references) != 1:
            raise InvalidBlueprintTargetError(
                f"working_brief must carry one exact parent ref for selected input: {input_id}"
            )
        artifact = artifact_by_ref.get((input_id, references[0].revision))
        if artifact is None or artifact.kind != INPUT_LEDGER_ARTIFACT_KIND:
            raise InvalidBlueprintTargetError(
                f"working_brief input parent is not an Input Ledger artifact: {input_id}"
            )
        if artifact.payload.get("kind") == "context_bundle":
            raise InvalidBlueprintTargetError("working_brief selected inputs cannot be Context Bundles")
        selected.append(artifact)
    return tuple(selected)


def _brief_selected_input_ids(brief: ArtifactRevision) -> tuple[str, ...]:
    return _identifier_sequence(
        brief.payload.get("selected_input_ids"),
        "working_brief selected_input_ids",
    )


def _brief_hypothesis_ids(
    brief: ArtifactRevision, model: ArtifactRevision
) -> frozenset[str]:
    carried_ids = _identifier_sequence(
        brief.payload.get("intent_hypothesis_ids"),
        "working_brief intent_hypothesis_ids",
    )
    viable_raw = brief.payload.get("viable_intent_hypothesis_ids", ())
    viable_ids = _identifier_sequence(
        viable_raw,
        "working_brief viable_intent_hypothesis_ids",
        allow_empty=True,
    )
    model_hypotheses = _mapping_sequence(
        model.payload.get("hypotheses"), "intent_model hypotheses"
    )
    model_ids = {
        _identifier(hypothesis.get("id"), "intent_model hypothesis id")
        for hypothesis in model_hypotheses
    }
    visible = frozenset((*carried_ids, *viable_ids))
    if not visible or not visible <= model_ids:
        raise InvalidBlueprintTargetError(
            "working_brief intent hypotheses must be visible in its exact Intent Model"
        )
    return visible


def _repository_anchors(inputs: Sequence[ArtifactRevision]) -> frozenset[tuple[str, str | None]]:
    anchors: set[tuple[str, str | None]] = set()
    for artifact in inputs:
        if artifact.payload.get("kind") != "repository":
            continue
        baseline = artifact.payload.get("repository_baseline")
        if not isinstance(baseline, Mapping):
            raise InvalidBlueprintTargetError("repository Input Ledger entry has no baseline")
        for anchor in _mapping_sequence(baseline.get("anchors"), "repository baseline anchors"):
            path = _nonempty_string(anchor.get("path"), "repository anchor path")
            symbol_raw = anchor.get("symbol")
            if symbol_raw is not None and not isinstance(symbol_raw, str):
                raise InvalidBlueprintTargetError("repository anchor symbol must be a string or null")
            symbol = None if symbol_raw is None else _nonempty_string(symbol_raw, "repository anchor symbol")
            anchors.add((path, symbol))
    return frozenset(anchors)


def _normalize_slots(
    value: Any,
    *,
    visible_hypotheses: frozenset[str],
    selected_input_ids: tuple[str, ...],
    repository_anchors: frozenset[tuple[str, str | None]],
) -> list[dict[str, Any]]:
    slots = _mapping_sequence(value, "slots")
    if not slots:
        raise InvalidBlueprintTargetError("Blueprint Target requires at least one Decision Slot")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, candidate in enumerate(slots):
        label = f"slots[{index}]"
        _require_exact_keys(
            candidate,
            {
                "id",
                "kind",
                "question",
                "intent_hypothesis_ids",
                "priority",
                "impact",
                "uncertainty",
                "irreversibility",
                "constraints",
                "alternatives",
                "repository_touchpoints",
                "greenfield_assumptions",
                "depends_on",
                "evidence_standard",
                "validation",
                "closure_rule",
                "status",
                "bounded_research_need",
                "fallback",
            },
            label,
        )
        slot_id = _identifier(candidate["id"], f"{label}.id")
        if slot_id in seen_ids:
            raise InvalidBlueprintTargetError(f"duplicate Decision Slot id: {slot_id}")
        seen_ids.add(slot_id)
        kind = _enum(candidate["kind"], f"{label}.kind", SLOT_KINDS)
        hypothesis_ids = _identifier_sequence(
            candidate["intent_hypothesis_ids"], f"{label}.intent_hypothesis_ids"
        )
        unknown_hypotheses = set(hypothesis_ids) - visible_hypotheses
        if unknown_hypotheses:
            raise InvalidBlueprintTargetError(
                f"{label} has hypotheses absent from the Working Brief: {sorted(unknown_hypotheses)}"
            )
        priority = _enum(candidate["priority"], f"{label}.priority", PRIORITIES)
        status = _enum(candidate["status"], f"{label}.status", SLOT_STATUSES)
        alternatives = _string_sequence(candidate["alternatives"], f"{label}.alternatives")
        if len(alternatives) < 2 or len(set(alternatives)) != len(alternatives):
            raise InvalidBlueprintTargetError(f"{label}.alternatives must contain two distinct options")
        touchpoints = _normalize_touchpoints(
            candidate["repository_touchpoints"],
            label,
            repository_anchors,
        )
        assumptions = _string_sequence(
            candidate["greenfield_assumptions"],
            f"{label}.greenfield_assumptions",
            allow_empty=True,
        )
        if not touchpoints and not assumptions:
            raise InvalidBlueprintTargetError(
                f"{label} needs a repository touchpoint or an explicit greenfield assumption"
            )
        if not repository_anchors and touchpoints:
            raise InvalidBlueprintTargetError(
                f"{label} cannot cite repository touchpoints without a selected repository baseline"
            )
        bounded_need = _string_or_empty(
            candidate["bounded_research_need"], f"{label}.bounded_research_need"
        )
        if priority == "P0" and status in {"open", "researching"} and not bounded_need:
            raise InvalidBlueprintTargetError(
                f"{label} P0 {status} slot requires a bounded_research_need"
            )
        normalized.append(
            {
                "id": slot_id,
                "kind": kind,
                "question": _nonempty_string(candidate["question"], f"{label}.question"),
                "intent_hypothesis_ids": list(hypothesis_ids),
                "priority": priority,
                "impact": _enum(candidate["impact"], f"{label}.impact", LEVELS),
                "uncertainty": _enum(candidate["uncertainty"], f"{label}.uncertainty", LEVELS),
                "irreversibility": _enum(
                    candidate["irreversibility"], f"{label}.irreversibility", LEVELS
                ),
                "constraints": _normalize_constraints(
                    candidate["constraints"],
                    label,
                    selected_input_ids,
                    repository_anchors,
                ),
                "alternatives": list(alternatives),
                "repository_touchpoints": touchpoints,
                "greenfield_assumptions": list(assumptions),
                "depends_on": list(
                    _identifier_sequence(
                        candidate["depends_on"], f"{label}.depends_on", allow_empty=True
                    )
                ),
                "evidence_standard": _nonempty_string(
                    candidate["evidence_standard"], f"{label}.evidence_standard"
                ),
                "validation": _normalize_validation(candidate["validation"], label),
                "closure_rule": _nonempty_string(
                    candidate["closure_rule"], f"{label}.closure_rule"
                ),
                "status": status,
                "bounded_research_need": bounded_need,
                "fallback": _nonempty_string(candidate["fallback"], f"{label}.fallback"),
            }
        )
    return normalized


def _normalize_touchpoints(
    value: Any,
    label: str,
    repository_anchors: frozenset[tuple[str, str | None]],
) -> list[dict[str, str | None]]:
    touchpoints = _mapping_sequence(value, f"{label}.repository_touchpoints")
    normalized: list[dict[str, str | None]] = []
    for index, touchpoint in enumerate(touchpoints):
        _require_exact_keys(touchpoint, {"path", "symbol"}, f"{label}.repository_touchpoints[{index}]")
        path = _nonempty_string(touchpoint["path"], f"{label}.repository_touchpoints[{index}].path")
        symbol_raw = touchpoint["symbol"]
        if symbol_raw is not None and not isinstance(symbol_raw, str):
            raise InvalidBlueprintTargetError(
                f"{label}.repository_touchpoints[{index}].symbol must be a string or null"
            )
        symbol = None if symbol_raw is None else _nonempty_string(
            symbol_raw, f"{label}.repository_touchpoints[{index}].symbol"
        )
        if repository_anchors:
            if symbol is None and not any(anchor_path == path for anchor_path, _ in repository_anchors):
                raise InvalidBlueprintTargetError(
                    f"{label}.repository_touchpoints[{index}] path is not in the repository baseline"
                )
            if symbol is not None and (path, symbol) not in repository_anchors:
                raise InvalidBlueprintTargetError(
                    f"{label}.repository_touchpoints[{index}] is not in the repository baseline"
                )
        normalized.append({"path": path, "symbol": symbol})
    return normalized


def _normalize_constraints(
    value: Any,
    label: str,
    selected_input_ids: tuple[str, ...],
    repository_anchors: frozenset[tuple[str, str | None]],
) -> list[dict[str, str]]:
    constraints = _mapping_sequence(value, f"{label}.constraints")
    if not constraints:
        raise InvalidBlueprintTargetError(f"{label}.constraints must not be empty")
    normalized: list[dict[str, str]] = []
    for index, constraint in enumerate(constraints):
        item_label = f"{label}.constraints[{index}]"
        _require_exact_keys(constraint, {"kind", "ref", "statement"}, item_label)
        kind = _enum(constraint["kind"], f"{item_label}.kind", CONSTRAINT_KINDS)
        reference = _nonempty_string(constraint["ref"], f"{item_label}.ref")
        if kind == "input":
            input_id = _identifier(reference, f"{item_label}.ref")
            if input_id not in selected_input_ids:
                raise InvalidBlueprintTargetError(
                    f"{item_label}.ref must be a selected Working Brief input"
                )
        if kind == "repository":
            _validate_repository_ref(reference, item_label, repository_anchors)
        normalized.append(
            {
                "kind": kind,
                "ref": reference,
                "statement": _nonempty_string(constraint["statement"], f"{item_label}.statement"),
            }
        )
    return normalized


def _validate_repository_ref(
    value: str,
    label: str,
    anchors: frozenset[tuple[str, str | None]],
) -> None:
    if not anchors:
        raise InvalidBlueprintTargetError(f"{label}.ref has no selected repository baseline")
    path, separator, symbol = value.partition(":")
    if not path:
        raise InvalidBlueprintTargetError(f"{label}.ref must be path or path:symbol")
    if not separator:
        if not any(anchor_path == path for anchor_path, _ in anchors):
            raise InvalidBlueprintTargetError(f"{label}.ref path is not in the repository baseline")
        return
    if not symbol or (path, symbol) not in anchors:
        raise InvalidBlueprintTargetError(f"{label}.ref is not in the repository baseline")


def _normalize_validation(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise InvalidBlueprintTargetError(f"{label}.validation must be a mapping")
    _require_exact_keys(value, {"kind", "oracle"}, f"{label}.validation")
    return {
        "kind": _enum(value["kind"], f"{label}.validation.kind", VALIDATION_KINDS),
        "oracle": _nonempty_string(value["oracle"], f"{label}.validation.oracle"),
    }


def _validate_dependencies(slots: Sequence[Mapping[str, Any]]) -> None:
    slot_ids = {slot["id"] for slot in slots}
    adjacency: dict[str, tuple[str, ...]] = {}
    for slot in slots:
        slot_id = slot["id"]
        dependencies = tuple(slot["depends_on"])
        unknown = set(dependencies) - slot_ids
        if unknown:
            raise InvalidBlueprintTargetError(
                f"Decision Slot {slot_id} depends on unknown slots: {sorted(unknown)}"
            )
        if slot_id in dependencies:
            raise InvalidBlueprintTargetError(f"Decision Slot {slot_id} cannot depend on itself")
        adjacency[slot_id] = dependencies

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(slot_id: str) -> None:
        if slot_id in visiting:
            raise InvalidBlueprintTargetError("Decision Slot dependencies must be acyclic")
        if slot_id in visited:
            return
        visiting.add(slot_id)
        for dependency in adjacency[slot_id]:
            visit(dependency)
        visiting.remove(slot_id)
        visited.add(slot_id)

    for slot_id in adjacency:
        visit(slot_id)


def _latest_target(
    artifacts: Sequence[ArtifactRevision], target_id: str
) -> ArtifactRevision | None:
    targets = [
        artifact
        for artifact in artifacts
        if artifact.id == target_id and artifact.kind == BLUEPRINT_TARGET_KIND
    ]
    return max(targets, key=lambda artifact: artifact.revision, default=None)


def _shares_exact_brief_model_lineage(
    target: ArtifactRevision,
    brief: ArtifactRevision,
    model: ArtifactRevision,
) -> bool:
    expected = {
        ArtifactRef(brief.round_id, brief.id, brief.revision),
        ArtifactRef(model.round_id, model.id, model.revision),
    }
    return (
        target.payload.get("brief_id") == brief.id
        and target.payload.get("intent_model_id") == model.id
        and expected <= set(target.parent_refs)
    )


def _normalize_change(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidBlueprintTargetError("change must be a mapping")
    _require_exact_keys(value, {"kind", "reason", "from_slot_ids", "to_slot_ids"}, "change")
    return {
        "kind": _enum(value["kind"], "change.kind", CHANGE_KINDS),
        "reason": _nonempty_string(value["reason"], "change.reason"),
        "from_slot_ids": list(
            _identifier_sequence(value["from_slot_ids"], "change.from_slot_ids", allow_empty=True)
        ),
        "to_slot_ids": list(
            _identifier_sequence(value["to_slot_ids"], "change.to_slot_ids", allow_empty=True)
        ),
    }


def _validate_change(
    previous: ArtifactRevision | None,
    current_slots: Sequence[Mapping[str, Any]],
    change: Mapping[str, Any],
) -> None:
    kind = change["kind"]
    current = {slot["id"]: dict(slot) for slot in current_slots}
    from_ids = set(change["from_slot_ids"])
    to_ids = set(change["to_slot_ids"])
    if previous is None:
        if kind != "initial":
            raise InvalidBlueprintTargetError("first Blueprint Target revision must use change.kind initial")
        if from_ids or to_ids != set(current):
            raise InvalidBlueprintTargetError(
                "initial change must have no source slots and list every current slot as a target"
            )
        return

    if kind == "initial":
        raise InvalidBlueprintTargetError("later Blueprint Target revision cannot use change.kind initial")
    previous_slots = _previous_slots(previous)
    previous_ids = set(previous_slots)
    current_ids = set(current)
    added = current_ids - previous_ids
    removed = previous_ids - current_ids
    shared = previous_ids & current_ids

    if kind == "add":
        _require_change_sets(kind, from_ids, to_ids, set(), added)
        _require_shared_slots_unchanged(previous_slots, current, shared)
    elif kind == "remove":
        _require_change_sets(kind, from_ids, to_ids, removed, set())
        _require_shared_slots_unchanged(previous_slots, current, shared)
    elif kind == "split":
        if len(removed) != 1 or len(added) < 2:
            raise InvalidBlueprintTargetError("split must replace one source slot with at least two targets")
        _require_change_sets(kind, from_ids, to_ids, removed, added)
        _require_shared_slots_unchanged(previous_slots, current, shared)
    elif kind == "merge":
        if len(removed) < 2 or len(added) != 1:
            raise InvalidBlueprintTargetError("merge must replace at least two source slots with one target")
        _require_change_sets(kind, from_ids, to_ids, removed, added)
        _require_shared_slots_unchanged(previous_slots, current, shared)
    elif kind == "reprioritize":
        if added or removed or not from_ids or from_ids != to_ids or not from_ids <= shared:
            raise InvalidBlueprintTargetError(
                "reprioritize must retain slot ids and name the changed slots as both source and target"
            )
        for slot_id in shared:
            before = previous_slots[slot_id]
            after = current[slot_id]
            if slot_id not in from_ids:
                if before != after:
                    raise InvalidBlueprintTargetError(
                        "reprioritize cannot modify unlisted Decision Slots"
                    )
                continue
            before_without_priority = {key: value for key, value in before.items() if key != "priority"}
            after_without_priority = {key: value for key, value in after.items() if key != "priority"}
            if before_without_priority != after_without_priority or before["priority"] == after["priority"]:
                raise InvalidBlueprintTargetError(
                    "reprioritize may change only priority and must change it for every listed slot"
                )
    else:
        raise InvalidBlueprintTargetError(f"unsupported change kind: {kind}")


def _previous_slots(previous: ArtifactRevision) -> dict[str, dict[str, Any]]:
    payload_slots = thaw_json(previous.payload.get("slots", ()))
    if not isinstance(payload_slots, list):
        raise InvalidBlueprintTargetError("previous Blueprint Target slots are malformed")
    result: dict[str, dict[str, Any]] = {}
    for index, slot in enumerate(payload_slots):
        if not isinstance(slot, dict):
            raise InvalidBlueprintTargetError(f"previous Blueprint Target slots[{index}] is malformed")
        slot_id = _identifier(slot.get("id"), f"previous Blueprint Target slots[{index}].id")
        result[slot_id] = slot
    return result


def _require_change_sets(
    kind: str,
    from_ids: set[str],
    to_ids: set[str],
    expected_from: set[str],
    expected_to: set[str],
) -> None:
    if from_ids != expected_from or to_ids != expected_to or not (expected_from or expected_to):
        raise InvalidBlueprintTargetError(
            f"{kind} change source/target ids do not match the actual slot changes"
        )


def _require_shared_slots_unchanged(
    previous: Mapping[str, Mapping[str, Any]],
    current: Mapping[str, Mapping[str, Any]],
    shared_ids: set[str],
) -> None:
    changed = [slot_id for slot_id in shared_ids if previous[slot_id] != current[slot_id]]
    if changed:
        raise InvalidBlueprintTargetError(
            "change kind permits only its named id-set transition; changed shared slots: "
            f"{sorted(changed)}"
        )


def _mapping_sequence(value: Any, label: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidBlueprintTargetError(f"{label} must be a sequence of mappings")
    normalized: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise InvalidBlueprintTargetError(f"{label}[{index}] must be a mapping")
        normalized.append(item)
    return normalized


def _identifier_sequence(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidBlueprintTargetError(f"{label} must be a sequence of identifiers")
    result = tuple(_identifier(item, label) for item in value)
    if not result and not allow_empty:
        raise InvalidBlueprintTargetError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise InvalidBlueprintTargetError(f"{label} must not contain duplicate identifiers")
    return result


def _string_sequence(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidBlueprintTargetError(f"{label} must be a sequence of strings")
    result = tuple(_nonempty_string(item, label) for item in value)
    if not result and not allow_empty:
        raise InvalidBlueprintTargetError(f"{label} must not be empty")
    return result


def _identifier(value: Any, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise InvalidBlueprintTargetError(str(error)) from error


def _enum(value: Any, label: str, allowed: set[str]) -> str:
    normalized = _nonempty_string(value, label)
    if normalized not in allowed:
        raise InvalidBlueprintTargetError(f"{label} is unsupported: {normalized}")
    return normalized


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidBlueprintTargetError(f"{label} must be a nonempty string")
    return value


def _string_or_empty(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise InvalidBlueprintTargetError(f"{label} must be a string")
    return value.strip()


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise InvalidBlueprintTargetError(
            f"{label} has unexpected keys; missing={missing}, extra={extra}"
        )
