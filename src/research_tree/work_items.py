"""Compile bounded research work from exact Blueprint Target decisions."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .decision_map import BLUEPRINT_TARGET_KIND
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    thaw_json,
    validate_identifier,
)
from .storage import RunStore
from .run_ledger import RunLedger


WORK_ITEM_KIND = "work-item"
ROUND_SUPERSESSION_KIND = "round-supersession"
WORK_KINDS = {"external_research", "repository_analysis", "prototype", "evaluation"}
WORK_METHODS = {
    "primary_docs",
    "repository_inspection",
    "prototype",
    "benchmark",
    "standards",
    "evaluation",
}
WORK_STATUSES = {"planned", "ready", "running", "complete", "cancelled", "deferred"}
ACTIVE_SLOT_STATUSES = {"open", "researching"}
TERMINAL_SLOT_STATUSES = {"selected", "conditional", "deferred", "blocked"}
PLANNING_MODES = {"serial", "dependency_respecting"}


class WorkItemError(RuntimeStoreError):
    """Base error for invalid bounded research work."""


class InvalidWorkItemError(WorkItemError):
    """Raised before a Work Item can escape its Decision Slot boundary."""


class WorkItemCompiler:
    """Persist one exact Decision Slot research task as an immutable artifact."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def compile(
        self,
        *,
        round_id: str,
        work_item_id: str,
        blueprint_target: ArtifactRevision,
        decision_slot_id: str,
        kind: str,
        scope: str,
        exclusions: str,
        decision_change_reason: str,
        depends_on: Sequence[str],
        methods: Sequence[str],
        budget: Mapping[str, Any],
        completion_rule: str,
        intent_hypothesis_ids: Sequence[str] | None = None,
        status: str | None = None,
        exception_reason: str | None = None,
    ) -> ArtifactRevision:
        """Validate a bounded task against the exact target before appending it."""

        try:
            snapshot = self._store.load_round(round_id)
            _ensure_round_accepts_normal_work(snapshot.artifacts)
            validate_identifier(work_item_id, "work_item_id")
            _ensure_work_id_compatibility(snapshot.artifacts, work_item_id)
            target = _resolve_exact_target(snapshot.artifacts, blueprint_target)
            if target.round_id != round_id:
                raise InvalidWorkItemError("blueprint_target must belong to work item round")
            slot_id = _identifier(decision_slot_id, "decision_slot_id")
            slot = _target_slot(target, slot_id)
            target_hypotheses = _identifier_sequence(
                slot.get("intent_hypothesis_ids"), "slot intent_hypothesis_ids"
            )
            hypotheses = (
                target_hypotheses
                if intent_hypothesis_ids is None
                else _identifier_sequence(intent_hypothesis_ids, "intent_hypothesis_ids")
            )
            if not set(hypotheses) <= set(target_hypotheses):
                raise InvalidWorkItemError(
                    "Work Item intent hypotheses must be owned by its Decision Slot"
                )
            normalized_dependencies, dependency_artifacts = _resolve_dependencies(
                snapshot.artifacts,
                round_id,
                work_item_id,
                depends_on,
                target,
            )
            normalized_status, status_reason = _normalize_initial_status(
                slot,
                normalized_dependencies,
                status,
                exception_reason,
            )
            payload = {
                "id": work_item_id,
                "round_id": round_id,
                "blueprint_target_id": target.id,
                "decision_slot_id": slot_id,
                "intent_hypothesis_ids": list(hypotheses),
                "kind": _enum(kind, "kind", WORK_KINDS),
                "scope": _nonempty_string(scope, "scope"),
                "exclusions": _nonempty_string(exclusions, "exclusions"),
                "decision_change_reason": _nonempty_string(
                    decision_change_reason, "decision_change_reason"
                ),
                "depends_on": list(normalized_dependencies),
                "methods": list(_enum_sequence(methods, "methods", WORK_METHODS)),
                "budget": _normalize_budget(budget),
                "completion_rule": _nonempty_string(completion_rule, "completion_rule"),
                "expected_finding_pack": _expected_finding_pack(),
                "status": normalized_status,
                "status_reason": status_reason,
            }
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidWorkItemError(str(error)) from error

        target_ref = ArtifactRef(round_id, target.id, target.revision)
        dependency_refs = tuple(
            ArtifactRef(round_id, artifact.id, artifact.revision)
            for artifact in dependency_artifacts
        )
        return self._store.append_artifact(
            round_id,
            work_item_id,
            WORK_ITEM_KIND,
            payload,
            parent_refs=(target_ref, *dependency_refs),
        )


class CanonicalWorkItemCompiler:
    """Persist bounded research work directly in the canonical RunLedger."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise InvalidWorkItemError("canonical Work Item compiler requires a RunLedger")
        self._ledger = ledger

    def compile(
        self,
        *,
        round_id: str,
        work_item_id: str,
        blueprint_target: ArtifactRevision,
        decision_slot_id: str,
        kind: str,
        scope: str,
        exclusions: str,
        decision_change_reason: str,
        depends_on: Sequence[str],
        methods: Sequence[str],
        budget: Mapping[str, Any],
        completion_rule: str,
        expected_revision: int,
        intent_hypothesis_ids: Sequence[str] | None = None,
        status: str | None = None,
        exception_reason: str | None = None,
    ) -> ArtifactRevision:
        """Validate a bounded task before appending it with an exact revision."""

        try:
            snapshot = self._ledger.load_run(round_id)
            _ensure_round_accepts_normal_work(snapshot.artifacts)
            validate_identifier(work_item_id, "work_item_id")
            _ensure_work_id_compatibility(snapshot.artifacts, work_item_id)
            target = _resolve_exact_target(snapshot.artifacts, blueprint_target)
            if target.round_id != round_id:
                raise InvalidWorkItemError("blueprint_target must belong to work item round")
            slot_id = _identifier(decision_slot_id, "decision_slot_id")
            slot = _target_slot(target, slot_id)
            target_hypotheses = _identifier_sequence(
                slot.get("intent_hypothesis_ids"), "slot intent_hypothesis_ids"
            )
            hypotheses = (
                target_hypotheses
                if intent_hypothesis_ids is None
                else _identifier_sequence(intent_hypothesis_ids, "intent_hypothesis_ids")
            )
            if not set(hypotheses) <= set(target_hypotheses):
                raise InvalidWorkItemError(
                    "Work Item intent hypotheses must be owned by its Decision Slot"
                )
            normalized_dependencies, dependency_artifacts = _resolve_dependencies(
                snapshot.artifacts,
                round_id,
                work_item_id,
                depends_on,
                target,
            )
            normalized_status, status_reason = _normalize_initial_status(
                slot,
                normalized_dependencies,
                status,
                exception_reason,
            )
            payload = {
                "id": work_item_id,
                "round_id": round_id,
                "blueprint_target_id": target.id,
                "decision_slot_id": slot_id,
                "intent_hypothesis_ids": list(hypotheses),
                "kind": _enum(kind, "kind", WORK_KINDS),
                "scope": _nonempty_string(scope, "scope"),
                "exclusions": _nonempty_string(exclusions, "exclusions"),
                "decision_change_reason": _nonempty_string(
                    decision_change_reason, "decision_change_reason"
                ),
                "depends_on": list(normalized_dependencies),
                "methods": list(_enum_sequence(methods, "methods", WORK_METHODS)),
                "budget": _normalize_budget(budget),
                "completion_rule": _nonempty_string(completion_rule, "completion_rule"),
                "expected_finding_pack": _expected_finding_pack(),
                "status": normalized_status,
                "status_reason": status_reason,
            }
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidWorkItemError(str(error)) from error

        target_ref = ArtifactRef(round_id, target.id, target.revision)
        dependency_refs = tuple(
            ArtifactRef(round_id, artifact.id, artifact.revision)
            for artifact in dependency_artifacts
        )
        return self._ledger.append_artifact(
            round_id,
            work_item_id,
            WORK_ITEM_KIND,
            payload,
            parent_refs=(target_ref, *dependency_refs),
            expected_revision=expected_revision,
        )


class CanonicalWorkItemPlanner:
    """Generate bounded work through the canonical ledger only."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise InvalidWorkItemError("canonical Work Item planner requires a RunLedger")
        self._ledger = ledger
        self._compiler = CanonicalWorkItemCompiler(ledger)

    def plan(
        self,
        *,
        round_id: str,
        blueprint_target: ArtifactRevision,
        work_item_ids: Mapping[str, str],
        mode: str = "dependency_respecting",
    ) -> tuple[ArtifactRevision, ...]:
        try:
            snapshot = self._ledger.load_run(round_id)
            _ensure_round_accepts_normal_work(snapshot.artifacts)
            target = _resolve_exact_target(snapshot.artifacts, blueprint_target)
            if target.round_id != round_id:
                raise InvalidWorkItemError("blueprint_target must belong to planner round")
            planning_mode = _enum(mode, "mode", PLANNING_MODES)
            active_slots = {
                slot["id"]: slot
                for slot in _target_slots(target)
                if slot.get("status") in ACTIVE_SLOT_STATUSES
            }
            normalized_ids = _normalize_work_item_ids(work_item_ids, active_slots)
            ordered_slot_ids = _stable_topological_order(active_slots)
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidWorkItemError(str(error)) from error

        emitted: list[ArtifactRevision] = []
        previous_work_id: str | None = None
        for slot_id in ordered_slot_ids:
            slot = active_slots[slot_id]
            dependencies = (
                ()
                if planning_mode == "serial" and previous_work_id is None
                else (
                    (previous_work_id,)
                    if planning_mode == "serial"
                    else tuple(
                        normalized_ids[dependency]
                        for dependency in slot["depends_on"]
                        if dependency in active_slots
                    )
                )
            )
            work = self._compiler.compile(
                round_id=round_id,
                work_item_id=normalized_ids[slot_id],
                blueprint_target=target,
                decision_slot_id=slot_id,
                kind="repository_analysis" if slot["repository_touchpoints"] else "external_research",
                scope=slot["question"],
                exclusions="Do not close the Decision Slot, select an alternative, or add unrelated scope.",
                decision_change_reason="Findings can change the decision among: "
                + ", ".join(slot["alternatives"])
                + ".",
                depends_on=dependencies,
                methods=(
                    ("repository_inspection",)
                    if slot["repository_touchpoints"]
                    else ("primary_docs",)
                ),
                budget={"tool_calls": 8, "time": "bounded"},
                completion_rule=(
                    "Return a Finding Pack with atomic observations, option effects, "
                    "implementation implications, and remaining uncertainties; or explain "
                    "why evidence is unavailable."
                ),
                intent_hypothesis_ids=tuple(slot["intent_hypothesis_ids"]),
                expected_revision=self._ledger.get_revision(round_id),
            )
            emitted.append(work)
            previous_work_id = work.id
        return tuple(emitted)


class WorkItemPlanner:
    """Generate one deterministic bounded task graph for active target slots."""

    def __init__(self, store: RunStore) -> None:
        self._store = store
        self._compiler = WorkItemCompiler(store)

    def plan(
        self,
        *,
        round_id: str,
        blueprint_target: ArtifactRevision,
        work_item_ids: Mapping[str, str],
        mode: str = "dependency_respecting",
    ) -> tuple[ArtifactRevision, ...]:
        """Plan active slots in a stable topological order without executing work."""

        try:
            snapshot = self._store.load_round(round_id)
            _ensure_round_accepts_normal_work(snapshot.artifacts)
            target = _resolve_exact_target(snapshot.artifacts, blueprint_target)
            if target.round_id != round_id:
                raise InvalidWorkItemError("blueprint_target must belong to planner round")
            planning_mode = _enum(mode, "mode", PLANNING_MODES)
            active_slots = {
                slot["id"]: slot
                for slot in _target_slots(target)
                if slot.get("status") in ACTIVE_SLOT_STATUSES
            }
            normalized_ids = _normalize_work_item_ids(work_item_ids, active_slots)
            ordered_slot_ids = _stable_topological_order(active_slots)
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidWorkItemError(str(error)) from error

        emitted: list[ArtifactRevision] = []
        previous_work_id: str | None = None
        for slot_id in ordered_slot_ids:
            slot = active_slots[slot_id]
            if planning_mode == "serial":
                dependencies = () if previous_work_id is None else (previous_work_id,)
            else:
                dependencies = tuple(
                    normalized_ids[dependency]
                    for dependency in slot["depends_on"]
                    if dependency in active_slots
                )
            work = self._compiler.compile(
                round_id=round_id,
                work_item_id=normalized_ids[slot_id],
                blueprint_target=target,
                decision_slot_id=slot_id,
                kind=(
                    "repository_analysis"
                    if slot["repository_touchpoints"]
                    else "external_research"
                ),
                scope=slot["question"],
                exclusions=(
                    "Do not close the Decision Slot, select an alternative, or add unrelated scope."
                ),
                decision_change_reason=(
                    "Findings can change the decision among: "
                    + ", ".join(slot["alternatives"])
                    + "."
                ),
                depends_on=dependencies,
                methods=(
                    ("repository_inspection",)
                    if slot["repository_touchpoints"]
                    else ("primary_docs",)
                ),
                budget={"tool_calls": 8, "time": "bounded"},
                completion_rule=(
                    "Return a Finding Pack with atomic observations, option effects, "
                    "implementation implications, and remaining uncertainties; or explain "
                    "why evidence is unavailable."
                ),
                intent_hypothesis_ids=tuple(slot["intent_hypothesis_ids"]),
            )
            emitted.append(work)
            previous_work_id = work.id
        return tuple(emitted)


class WorkItemStatusService:
    """Append a cancellation or deferral revision with an explicit reason."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def update(
        self,
        *,
        round_id: str,
        work_item: ArtifactRevision,
        blueprint_target: ArtifactRevision,
        status: str,
        reason: str,
    ) -> ArtifactRevision:
        """Retain work history while recording a controlled terminal adjustment."""

        try:
            snapshot = self._store.load_round(round_id)
            stored_work = _resolve_exact_work_item(snapshot.artifacts, work_item)
            target = _resolve_exact_target(snapshot.artifacts, blueprint_target)
            if stored_work.round_id != round_id or target.round_id != round_id:
                raise InvalidWorkItemError("work item and target must belong to the update round")
            if stored_work.payload.get("blueprint_target_id") != target.id:
                raise InvalidWorkItemError("work item does not belong to the supplied Blueprint Target")
            decision_slot_id = _identifier(
                stored_work.payload.get("decision_slot_id"), "work_item decision_slot_id"
            )
            current_slot = next(
                (slot for slot in _target_slots(target) if slot.get("id") == decision_slot_id),
                None,
            )
            if current_slot is not None and current_slot.get("status") in ACTIVE_SLOT_STATUSES:
                raise InvalidWorkItemError(
                    "cancelled or deferred work requires a closed or superseded Decision Slot"
                )
            next_status = _enum(status, "status", {"cancelled", "deferred"})
            status_reason = _nonempty_string(reason, "reason")
            payload = thaw_json(stored_work.payload)
            if not isinstance(payload, dict):
                raise InvalidWorkItemError("stored work item payload is malformed")
            payload["status"] = next_status
            payload["status_reason"] = status_reason
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidWorkItemError(str(error)) from error

        previous_ref = ArtifactRef(round_id, stored_work.id, stored_work.revision)
        target_ref = ArtifactRef(round_id, target.id, target.revision)
        return self._store.append_artifact(
            round_id,
            stored_work.id,
            WORK_ITEM_KIND,
            payload,
            parent_refs=(previous_ref, target_ref),
        )


class CanonicalWorkItemStatusService:
    """Append controlled Work Item status revisions in the canonical ledger."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise InvalidWorkItemError("canonical Work Item status service requires a RunLedger")
        self._ledger = ledger

    def update(
        self,
        *,
        round_id: str,
        work_item: ArtifactRevision,
        blueprint_target: ArtifactRevision,
        status: str,
        reason: str,
        expected_revision: int,
    ) -> ArtifactRevision:
        try:
            snapshot = self._ledger.load_run(round_id)
            stored_work = _resolve_exact_work_item(snapshot.artifacts, work_item)
            target = _resolve_exact_target(snapshot.artifacts, blueprint_target)
            if stored_work.round_id != round_id or target.round_id != round_id:
                raise InvalidWorkItemError("work item and target must belong to the update round")
            if stored_work.payload.get("blueprint_target_id") != target.id:
                raise InvalidWorkItemError("work item does not belong to the supplied Blueprint Target")
            decision_slot_id = _identifier(
                stored_work.payload.get("decision_slot_id"), "work_item decision_slot_id"
            )
            current_slot = next(
                (slot for slot in _target_slots(target) if slot.get("id") == decision_slot_id),
                None,
            )
            if current_slot is not None and current_slot.get("status") in ACTIVE_SLOT_STATUSES:
                raise InvalidWorkItemError(
                    "cancelled or deferred work requires a closed or superseded Decision Slot"
                )
            next_status = _enum(status, "status", {"cancelled", "deferred"})
            status_reason = _nonempty_string(reason, "reason")
            payload = thaw_json(stored_work.payload)
            if not isinstance(payload, dict):
                raise InvalidWorkItemError("stored work item payload is malformed")
            payload["status"] = next_status
            payload["status_reason"] = status_reason
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidWorkItemError(str(error)) from error

        previous_ref = ArtifactRef(round_id, stored_work.id, stored_work.revision)
        target_ref = ArtifactRef(round_id, target.id, target.revision)
        return self._ledger.append_artifact(
            round_id,
            stored_work.id,
            WORK_ITEM_KIND,
            payload,
            parent_refs=(previous_ref, target_ref),
            expected_revision=expected_revision,
        )


def _ensure_work_id_compatibility(
    artifacts: Sequence[ArtifactRevision], work_item_id: str
) -> None:
    foreign_kinds = {
        artifact.kind
        for artifact in artifacts
        if artifact.id == work_item_id and artifact.kind != WORK_ITEM_KIND
    }
    if foreign_kinds:
        raise InvalidWorkItemError(
            f"work_item_id {work_item_id!r} is already used by artifact kinds: {sorted(foreign_kinds)}"
        )


def supersession_for_round(artifacts: Sequence[ArtifactRevision]) -> ArtifactRevision | None:
    """Return the latest immutable overlay that stops normal predecessor work."""

    candidates = [
        artifact
        for artifact in artifacts
        if artifact.kind == ROUND_SUPERSESSION_KIND and artifact.payload.get("status") == "superseded"
    ]
    return max(
        candidates,
        key=lambda artifact: (artifact.created_at, artifact.id, artifact.revision),
        default=None,
    )


def _ensure_round_accepts_normal_work(artifacts: Sequence[ArtifactRevision]) -> None:
    supersession = supersession_for_round(artifacts)
    if supersession is None:
        return
    successor = supersession.payload.get("successor_round_id")
    suffix = f" by {successor}" if isinstance(successor, str) and successor else ""
    raise InvalidWorkItemError(f"round is superseded{suffix}; normal work cannot be planned")


def _resolve_exact_target(
    artifacts: Sequence[ArtifactRevision], target: ArtifactRevision
) -> ArtifactRevision:
    if not isinstance(target, ArtifactRevision):
        raise InvalidWorkItemError("blueprint_target must be an ArtifactRevision")
    for stored in artifacts:
        if stored.id == target.id and stored.revision == target.revision:
            if stored != target:
                raise InvalidWorkItemError("blueprint_target does not match its stored revision")
            if stored.kind != BLUEPRINT_TARGET_KIND:
                raise InvalidWorkItemError("blueprint_target must be a blueprint-target artifact")
            return stored
    raise InvalidWorkItemError("blueprint_target has not been persisted in this RunStore")


def _resolve_exact_work_item(
    artifacts: Sequence[ArtifactRevision], work_item: ArtifactRevision
) -> ArtifactRevision:
    if not isinstance(work_item, ArtifactRevision):
        raise InvalidWorkItemError("work_item must be an ArtifactRevision")
    for stored in artifacts:
        if stored.id == work_item.id and stored.revision == work_item.revision:
            if stored != work_item:
                raise InvalidWorkItemError("work_item does not match its stored revision")
            if stored.kind != WORK_ITEM_KIND:
                raise InvalidWorkItemError("work_item must be a work-item artifact")
            return stored
    raise InvalidWorkItemError("work_item has not been persisted in this RunStore")


def _target_slots(target: ArtifactRevision) -> list[Mapping[str, Any]]:
    return _mapping_sequence(target.payload.get("slots"), "blueprint_target slots")


def _target_slot(target: ArtifactRevision, slot_id: str) -> Mapping[str, Any]:
    for slot in _target_slots(target):
        if slot.get("id") == slot_id:
            return slot
    raise InvalidWorkItemError(f"Decision Slot is absent from Blueprint Target: {slot_id}")


def _resolve_dependencies(
    artifacts: Sequence[ArtifactRevision],
    round_id: str,
    work_item_id: str,
    depends_on: Sequence[str],
    target: ArtifactRevision,
) -> tuple[tuple[str, ...], tuple[ArtifactRevision, ...]]:
    dependency_ids = _identifier_sequence(depends_on, "depends_on", allow_empty=True)
    if work_item_id in dependency_ids:
        raise InvalidWorkItemError("Work Item cannot depend on itself")
    resolved: list[ArtifactRevision] = []
    for dependency_id in dependency_ids:
        candidates = [
            artifact
            for artifact in artifacts
            if artifact.id == dependency_id
            and artifact.round_id == round_id
            and artifact.kind == WORK_ITEM_KIND
        ]
        dependency = max(candidates, key=lambda artifact: artifact.revision, default=None)
        if dependency is None:
            raise InvalidWorkItemError(f"depends_on Work Item is unknown: {dependency_id}")
        if dependency.payload.get("blueprint_target_id") != target.id:
            raise InvalidWorkItemError(
                f"depends_on Work Item belongs to a different Blueprint Target: {dependency_id}"
            )
        target_ref = ArtifactRef(target.round_id, target.id, target.revision)
        if target_ref not in dependency.parent_refs:
            raise InvalidWorkItemError(
                f"depends_on Work Item belongs to a different Blueprint Target revision: {dependency_id}"
            )
        resolved.append(dependency)
    return dependency_ids, tuple(resolved)


def _normalize_initial_status(
    slot: Mapping[str, Any],
    dependencies: tuple[str, ...],
    status: str | None,
    exception_reason: str | None,
) -> tuple[str, str | None]:
    slot_status = slot.get("status")
    if slot_status in ACTIVE_SLOT_STATUSES:
        if exception_reason is not None:
            raise InvalidWorkItemError("active Decision Slot work must not carry an exception_reason")
        selected_status = (
            ("planned" if dependencies else "ready")
            if status is None
            else _enum(status, "status", WORK_STATUSES)
        )
        return selected_status, None
    if slot_status in TERMINAL_SLOT_STATUSES:
        reason = _nonempty_string(exception_reason, "exception_reason")
        selected_status = "deferred" if status is None else _enum(status, "status", WORK_STATUSES)
        if selected_status not in {"cancelled", "deferred"}:
            raise InvalidWorkItemError(
                "closed Decision Slot exception work must be cancelled or deferred"
            )
        return selected_status, reason
    raise InvalidWorkItemError(f"Decision Slot has unsupported status: {slot_status!r}")


def _normalize_work_item_ids(
    value: Mapping[str, str], active_slots: Mapping[str, Mapping[str, Any]]
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise InvalidWorkItemError("work_item_ids must be a mapping")
    if set(value) != set(active_slots):
        raise InvalidWorkItemError("work_item_ids must map exactly the active Decision Slot ids")
    normalized: dict[str, str] = {}
    for slot_id in active_slots:
        _identifier(slot_id, "work_item_ids Decision Slot id")
        normalized[slot_id] = _identifier(value[slot_id], f"work_item_ids[{slot_id}]")
    if len(set(normalized.values())) != len(normalized):
        raise InvalidWorkItemError("work_item_ids values must be unique")
    return normalized


def _stable_topological_order(active_slots: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    dependencies = {
        slot_id: {
            dependency
            for dependency in _identifier_sequence(
                slot.get("depends_on"),
                f"Decision Slot {slot_id} depends_on",
                allow_empty=True,
            )
            if dependency in active_slots
        }
        for slot_id, slot in active_slots.items()
    }
    ordered: list[str] = []
    while dependencies:
        ready = sorted(slot_id for slot_id, edges in dependencies.items() if not edges)
        if not ready:
            raise InvalidWorkItemError("active Decision Slot dependencies must be acyclic")
        ordered.extend(ready)
        for slot_id in ready:
            dependencies.pop(slot_id)
        for edges in dependencies.values():
            edges.difference_update(ready)
    return tuple(ordered)


def _normalize_budget(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidWorkItemError("budget must be a mapping")
    _require_exact_keys(value, {"tool_calls", "time"}, "budget")
    tool_calls = value["tool_calls"]
    if isinstance(tool_calls, bool) or not isinstance(tool_calls, int) or tool_calls < 1:
        raise InvalidWorkItemError("budget.tool_calls must be a positive integer")
    return {
        "tool_calls": tool_calls,
        "time": _nonempty_string(value["time"], "budget.time"),
    }


def _expected_finding_pack() -> dict[str, str]:
    return {
        "observations": "atomic observations with anchors, applicability, confidence, and limitations",
        "option_effects": "how each observation supports, contradicts, or limits an option",
        "implementation_implications": "concrete repository or greenfield design consequence",
        "remaining_uncertainties": "unresolved evidence that can still change the decision",
        "research_node_id": "the exact persisted research-tree node being answered",
        "research_continuations": "structured successor actions triggered by evidence, not prose suggestions",
        "validation_result": "an optional passed, failed, or inconclusive result with its oracle and evidence",
    }


def _mapping_sequence(value: Any, label: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidWorkItemError(f"{label} must be a sequence of mappings")
    normalized: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise InvalidWorkItemError(f"{label}[{index}] must be a mapping")
        normalized.append(item)
    return normalized


def _identifier_sequence(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidWorkItemError(f"{label} must be a sequence of identifiers")
    result = tuple(_identifier(item, label) for item in value)
    if not result and not allow_empty:
        raise InvalidWorkItemError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise InvalidWorkItemError(f"{label} must not contain duplicate identifiers")
    return result


def _enum_sequence(value: Any, label: str, allowed: set[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidWorkItemError(f"{label} must be a sequence")
    result = tuple(_enum(item, label, allowed) for item in value)
    if not result:
        raise InvalidWorkItemError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise InvalidWorkItemError(f"{label} must not contain duplicate values")
    return result


def _identifier(value: Any, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise InvalidWorkItemError(str(error)) from error


def _enum(value: Any, label: str, allowed: set[str]) -> str:
    normalized = _nonempty_string(value, label)
    if normalized not in allowed:
        raise InvalidWorkItemError(f"{label} is unsupported: {normalized}")
    return normalized


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidWorkItemError(f"{label} must be a nonempty string")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise InvalidWorkItemError(f"{label} has unexpected keys; missing={missing}, extra={extra}")
