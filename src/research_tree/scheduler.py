"""Schedule bounded research work without conflating it with provenance graphs."""

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
from .work_items import WORK_ITEM_KIND


WORK_PORTFOLIO_KIND = "work-portfolio"
EVENT_KINDS = {
    "initial",
    "evidence_conflict",
    "prototype_failure",
    "repository_fact_disproved",
    "new_p0_decision",
    "budget_saturated",
    "cancellation",
}
LEVEL_SCORES = {"low": 1, "medium": 2, "high": 3}


class PortfolioError(RuntimeStoreError):
    """Base error for invalid adaptive portfolio scheduling."""


class InvalidPortfolioError(PortfolioError):
    """Raised before an ambiguous or unrebuildable portfolio is persisted."""


class AdaptivePortfolioScheduler:
    """Compile a local, explainable schedule from exact Work Item revisions."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def schedule(
        self,
        *,
        round_id: str,
        portfolio_id: str,
        blueprint_target: ArtifactRevision,
        work_items: Sequence[ArtifactRevision],
        scoring_inputs: Mapping[str, Mapping[str, int]],
        tool_call_budget: int,
        max_parallelism: int,
        prior_portfolio: ArtifactRevision | None = None,
        event: Mapping[str, Any] | None = None,
    ) -> ArtifactRevision:
        """Append a deterministic schedule for one explicit work portfolio."""

        try:
            snapshot = self._store.load_round(round_id)
            validate_identifier(portfolio_id, "portfolio_id")
            _ensure_id_compatibility(snapshot.artifacts, portfolio_id, WORK_PORTFOLIO_KIND)
            target = _resolve_exact(
                snapshot.artifacts, blueprint_target, BLUEPRINT_TARGET_KIND, "blueprint_target"
            )
            if target.round_id != round_id:
                raise InvalidPortfolioError("blueprint_target must belong to portfolio round")
            works = _resolve_work_items(snapshot.artifacts, round_id, target, work_items)
            dag = _dependency_dag(works)
            _ensure_acyclic(dag)
            inputs = _normalize_scoring_inputs(scoring_inputs, works)
            budget = _nonnegative_int(tool_call_budget, "tool_call_budget")
            parallelism = _positive_int(max_parallelism, "max_parallelism")
            previous = _resolve_prior_portfolio(
                snapshot.artifacts, round_id, portfolio_id, prior_portfolio
            )
            normalized_event, event_artifacts = _normalize_event(
                snapshot.artifacts, round_id, works, event, previous
            )
            scores = _score_work(works, _target_slots(target), dag, inputs)
            payload = _portfolio_payload(
                portfolio_id,
                round_id,
                target,
                works,
                dag,
                scores,
                budget,
                parallelism,
                normalized_event,
            )
            validate_portfolio_payload(payload)
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidPortfolioError(str(error)) from error

        refs = _unique_refs(
            (() if previous is None else (ArtifactRef(round_id, previous.id, previous.revision),))
            + (ArtifactRef(round_id, target.id, target.revision),)
            + tuple(ArtifactRef(round_id, work.id, work.revision) for work in works)
            + tuple(ArtifactRef(round_id, item.id, item.revision) for item in event_artifacts)
        )
        return self._store.append_artifact(
            round_id,
            portfolio_id,
            WORK_PORTFOLIO_KIND,
            payload,
            parent_refs=refs,
        )


def validate_portfolio_payload(payload: Mapping[str, Any]) -> None:
    """Validate the persisted, rebuildable scheduler projection."""

    _require_exact_keys(
        payload,
        {
            "id",
            "round_id",
            "blueprint_target_ref",
            "work_dependency_dag",
            "scoring",
            "ready_portfolio",
            "dispatch_batches",
            "scheduling_decisions",
            "budget",
            "replan_event",
        },
        "work portfolio",
    )
    _nonempty_string(payload["id"], "portfolio id")
    _nonempty_string(payload["round_id"], "portfolio round_id")
    if not isinstance(payload["blueprint_target_ref"], Mapping):
        raise InvalidPortfolioError("blueprint_target_ref must be a mapping")
    for label in ("work_dependency_dag", "scoring", "dispatch_batches", "scheduling_decisions"):
        _mapping_sequence(payload[label], label, allow_empty=True)
    _identifier_sequence(payload["ready_portfolio"], "ready_portfolio", allow_empty=True)
    if not isinstance(payload["budget"], Mapping):
        raise InvalidPortfolioError("budget must be a mapping")
    _require_exact_keys(
        payload["budget"],
        {"tool_call_limit", "scheduled_tool_calls", "remaining_tool_calls"},
        "budget",
    )
    if not isinstance(payload["replan_event"], Mapping):
        raise InvalidPortfolioError("replan_event must be a mapping")


def _resolve_exact(
    artifacts: Sequence[ArtifactRevision], artifact: ArtifactRevision, expected_kind: str, label: str
) -> ArtifactRevision:
    if not isinstance(artifact, ArtifactRevision):
        raise InvalidPortfolioError(f"{label} must be an ArtifactRevision")
    for stored in artifacts:
        if stored.id == artifact.id and stored.revision == artifact.revision:
            if stored != artifact:
                raise InvalidPortfolioError(f"{label} does not match its stored revision")
            if stored.kind != expected_kind:
                raise InvalidPortfolioError(f"{label} must be a {expected_kind} artifact")
            return stored
    raise InvalidPortfolioError(f"{label} has not been persisted in this RunStore")


def _resolve_work_items(
    artifacts: Sequence[ArtifactRevision],
    round_id: str,
    target: ArtifactRevision,
    values: Sequence[ArtifactRevision],
) -> tuple[ArtifactRevision, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise InvalidPortfolioError("work_items must be a nonempty sequence of Work Item artifacts")
    target_ref = ArtifactRef(round_id, target.id, target.revision)
    works: list[ArtifactRevision] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        work = _resolve_exact(artifacts, value, WORK_ITEM_KIND, f"work_items[{index}]")
        if work.round_id != round_id:
            raise InvalidPortfolioError("Work Item must belong to portfolio round")
        if work.id in seen:
            raise InvalidPortfolioError("work_items must not contain duplicate ids")
        if work.payload.get("blueprint_target_id") != target.id or target_ref not in work.parent_refs:
            raise InvalidPortfolioError("Work Item must belong to the exact Blueprint Target revision")
        if _latest_artifact(artifacts, work.id, WORK_ITEM_KIND) != work:
            raise InvalidPortfolioError(f"Work Item revision is stale for portfolio input: {work.id}")
        seen.add(work.id)
        works.append(work)
    return tuple(sorted(works, key=lambda work: work.id))


def _dependency_dag(works: Sequence[ArtifactRevision]) -> dict[str, tuple[str, ...]]:
    ids = {work.id for work in works}
    result: dict[str, tuple[str, ...]] = {}
    for work in works:
        depends_on = _identifier_sequence(
            work.payload.get("depends_on"), f"Work Item {work.id} depends_on", allow_empty=True
        )
        unknown = set(depends_on) - ids
        if unknown:
            raise InvalidPortfolioError(
                f"Work Item {work.id} depends on work outside the supplied portfolio: {sorted(unknown)}"
            )
        if work.id in depends_on:
            raise InvalidPortfolioError(f"Work Item {work.id} cannot depend on itself")
        result[work.id] = depends_on
    return result


def _ensure_acyclic(dag: Mapping[str, Sequence[str]]) -> None:
    remaining = {work_id: set(edges) for work_id, edges in dag.items()}
    while remaining:
        ready = sorted(work_id for work_id, edges in remaining.items() if not edges)
        if not ready:
            raise InvalidPortfolioError("Work Item dependency graph contains a cycle")
        for work_id in ready:
            remaining.pop(work_id)
        for edges in remaining.values():
            edges.difference_update(ready)


def _normalize_scoring_inputs(
    value: Mapping[str, Mapping[str, int]], works: Sequence[ArtifactRevision]
) -> dict[str, dict[str, int]]:
    if not isinstance(value, Mapping):
        raise InvalidPortfolioError("scoring_inputs must be a mapping")
    ids = {work.id for work in works}
    if set(value) != ids:
        raise InvalidPortfolioError("scoring_inputs must cover exactly the supplied Work Item ids")
    result: dict[str, dict[str, int]] = {}
    for work in works:
        raw = value[work.id]
        if not isinstance(raw, Mapping):
            raise InvalidPortfolioError(f"scoring_inputs[{work.id}] must be a mapping")
        _require_exact_keys(
            raw,
            {"expected_information_gain", "cost", "duplicate_risk"},
            f"scoring_inputs[{work.id}]",
        )
        result[work.id] = {
            key: _score_input(raw[key], f"scoring_inputs[{work.id}].{key}")
            for key in ("expected_information_gain", "cost", "duplicate_risk")
        }
    return result


def _resolve_prior_portfolio(
    artifacts: Sequence[ArtifactRevision],
    round_id: str,
    portfolio_id: str,
    value: ArtifactRevision | None,
) -> ArtifactRevision | None:
    latest = _latest_artifact(artifacts, portfolio_id, WORK_PORTFOLIO_KIND)
    if value is None:
        if latest is not None:
            raise InvalidPortfolioError(
                "a later portfolio revision must provide the latest prior_portfolio"
            )
        return None
    prior = _resolve_exact(artifacts, value, WORK_PORTFOLIO_KIND, "prior_portfolio")
    if prior.round_id != round_id or prior.id != portfolio_id:
        raise InvalidPortfolioError("prior_portfolio must use the same round and portfolio id")
    if latest != prior:
        raise InvalidPortfolioError("prior_portfolio must be the latest portfolio revision")
    return prior


def _normalize_event(
    artifacts: Sequence[ArtifactRevision],
    round_id: str,
    works: Sequence[ArtifactRevision],
    value: Mapping[str, Any] | None,
    prior: ArtifactRevision | None,
) -> tuple[dict[str, Any], tuple[ArtifactRevision, ...]]:
    if value is None:
        if prior is not None:
            raise InvalidPortfolioError("a later portfolio revision requires a replan event")
        return (
            {
                "kind": "initial",
                "reason": "Initial portfolio scheduling.",
                "affected_work_item_ids": [],
                "evidence_refs": [],
            },
            (),
        )
    if not isinstance(value, Mapping):
        raise InvalidPortfolioError("event must be a mapping")
    _require_exact_keys(
        value,
        {"kind", "reason", "affected_work_item_ids", "evidence_refs"},
        "event",
    )
    kind = _nonempty_string(value["kind"], "event.kind")
    if kind not in EVENT_KINDS:
        raise InvalidPortfolioError(f"event.kind is unsupported: {kind}")
    if prior is not None and kind == "initial":
        raise InvalidPortfolioError("a later portfolio revision cannot use an initial event")
    affected = _identifier_sequence(
        value["affected_work_item_ids"], "event.affected_work_item_ids", allow_empty=True
    )
    if prior is not None and not affected:
        raise InvalidPortfolioError(
            "a later replan event must identify affected Work Items"
        )
    unknown = set(affected) - {work.id for work in works}
    if unknown:
        raise InvalidPortfolioError(
            f"event references Work Items outside the supplied portfolio: {sorted(unknown)}"
        )
    evidence_values = _mapping_sequence(value["evidence_refs"], "event.evidence_refs", allow_empty=True)
    by_ref = {(artifact.id, artifact.revision): artifact for artifact in artifacts}
    evidence: list[ArtifactRevision] = []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for index, raw in enumerate(evidence_values):
        _require_exact_keys(raw, {"artifact_id", "revision"}, f"event.evidence_refs[{index}]")
        artifact_id = _identifier(raw["artifact_id"], f"event.evidence_refs[{index}].artifact_id")
        revision = _positive_int(raw["revision"], f"event.evidence_refs[{index}].revision")
        artifact = by_ref.get((artifact_id, revision))
        if artifact is None or artifact.round_id != round_id:
            raise InvalidPortfolioError("event evidence reference must resolve in the portfolio round")
        if (artifact_id, revision) not in seen:
            seen.add((artifact_id, revision))
            evidence.append(artifact)
            refs.append(ArtifactRef(round_id, artifact_id, revision).to_dict())
    if prior is not None and not evidence:
        raise InvalidPortfolioError(
            "a later replan event must include at least one supporting artifact reference"
        )
    return (
        {
            "kind": kind,
            "reason": _nonempty_string(value["reason"], "event.reason"),
            "affected_work_item_ids": list(affected),
            "evidence_refs": refs,
        },
        tuple(evidence),
    )


def _target_slots(target: ArtifactRevision) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, slot in enumerate(_mapping_sequence(target.payload.get("slots"), "Blueprint Target slots")):
        result[_identifier(slot.get("id"), f"Blueprint Target slots[{index}].id")] = slot
    return result


def _score_work(
    works: Sequence[ArtifactRevision],
    slots: Mapping[str, Mapping[str, Any]],
    dag: Mapping[str, Sequence[str]],
    inputs: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, Any]]:
    leverage = _downstream_leverage(dag)
    result: dict[str, dict[str, Any]] = {}
    for work in works:
        slot_id = _identifier(work.payload.get("decision_slot_id"), f"Work Item {work.id} decision_slot_id")
        slot = slots.get(slot_id)
        if slot is None:
            raise InvalidPortfolioError(f"Work Item {work.id} references an absent Decision Slot")
        factors = inputs[work.id]
        components = {
            "impact": _level(slot.get("impact"), f"Decision Slot {slot_id}.impact") * 30,
            "uncertainty": _level(slot.get("uncertainty"), f"Decision Slot {slot_id}.uncertainty") * 20,
            "downstream_leverage": leverage[work.id] * 10,
            "irreversibility": _level(slot.get("irreversibility"), f"Decision Slot {slot_id}.irreversibility") * 15,
            "expected_information_gain": factors["expected_information_gain"],
            "cost": -factors["cost"],
            "duplicate_risk": -factors["duplicate_risk"],
        }
        result[work.id] = {"score": sum(components.values()), "components": components}
    return result


def _downstream_leverage(dag: Mapping[str, Sequence[str]]) -> dict[str, int]:
    reverse = {work_id: set() for work_id in dag}
    for work_id, dependencies in dag.items():
        for dependency in dependencies:
            reverse[dependency].add(work_id)
    result: dict[str, int] = {}
    for work_id in dag:
        reached: set[str] = set()
        frontier = list(reverse[work_id])
        while frontier:
            candidate = frontier.pop()
            if candidate not in reached:
                reached.add(candidate)
                frontier.extend(reverse[candidate] - reached)
        result[work_id] = len(reached)
    return result


def _portfolio_payload(
    portfolio_id: str,
    round_id: str,
    target: ArtifactRevision,
    works: Sequence[ArtifactRevision],
    dag: Mapping[str, Sequence[str]],
    scores: Mapping[str, Mapping[str, Any]],
    tool_call_budget: int,
    max_parallelism: int,
    event: Mapping[str, Any],
) -> dict[str, Any]:
    by_id = {work.id: work for work in works}
    duplicates = _duplicate_work(by_id, scores, dag)
    duplicate_cancellations = {
        work_id
        for work_id in duplicates
        if _work_status(by_id[work_id]) not in {"complete", "running", "cancelled", "deferred"}
    }
    running = [work_id for work_id in sorted(by_id) if _work_status(by_id[work_id]) == "running"]
    running_tool_calls = sum(_work_tool_calls(by_id[work_id]) for work_id in running)
    if running_tool_calls > tool_call_budget:
        raise InvalidPortfolioError("running Work Items exceed the portfolio tool-call budget")
    if len(running) > max_parallelism:
        raise InvalidPortfolioError("running Work Items exceed the portfolio max_parallelism")
    decisions: dict[str, dict[str, Any]] = {}
    ready: list[str] = []
    for work_id in sorted(by_id):
        work = by_id[work_id]
        status = _work_status(work)
        base = {"work_item_id": work_id, "score": scores[work_id]["score"]}
        if status == "complete":
            decisions[work_id] = {**base, "action": "complete", "reason": "Work Item is already complete."}
        elif status == "running":
            decisions[work_id] = {**base, "action": "running", "reason": "Work Item is already running."}
        elif status in {"cancelled", "deferred"}:
            decisions[work_id] = {
                **base,
                "action": "cancelled" if status == "cancelled" else "deferred",
                "reason": f"Work Item is already {status}.",
            }
        elif work_id in duplicate_cancellations:
            decisions[work_id] = {
                **base,
                "score_components": dict(scores[work_id]["components"]),
                "action": "cancelled",
                "reason": f"Duplicate of {duplicates[work_id]} for the same bounded Decision Slot work.",
            }
        else:
            terminal = sorted(
                dependency
                for dependency in dag[work_id]
                if dependency in duplicate_cancellations
                or _work_status(by_id[dependency]) in {"cancelled", "deferred"}
            )
            if terminal:
                decisions[work_id] = {
                    **base,
                    "action": "deferred",
                    "reason": (
                        "Blocked by terminal dependencies: "
                        + ", ".join(terminal)
                        + ". A replacement Work Item or revised Blueprint Target is required."
                    ),
                }
                continue
            incomplete = sorted(
                dependency
                for dependency in dag[work_id]
                if _nonempty_string(by_id[dependency].payload.get("status"), f"Work Item {dependency}.status")
                != "complete"
            )
            if incomplete:
                decisions[work_id] = {
                    **base,
                    "action": "waiting",
                    "reason": "Waiting for incomplete dependencies: " + ", ".join(incomplete) + ".",
                }
            else:
                ready.append(work_id)
    ready.sort(key=lambda work_id: (-scores[work_id]["score"], work_id))

    dispatched: list[str] = []
    remaining = tool_call_budget - running_tool_calls
    available_parallelism = max_parallelism - len(running)
    for work_id in ready:
        work_cost = _work_tool_calls(by_id[work_id])
        base = {
            "work_item_id": work_id,
            "score": scores[work_id]["score"],
            "score_components": dict(scores[work_id]["components"]),
        }
        if len(dispatched) >= available_parallelism:
            decisions[work_id] = {
                **base,
                "action": "deferred",
                "reason": "Max parallelism is reached by higher-ranked independent work.",
            }
        elif work_cost > remaining:
            decisions[work_id] = {
                **base,
                "action": "deferred",
                "reason": "Tool-call budget is exhausted by higher-ranked work.",
            }
        else:
            _ensure_independent(work_id, dispatched, dag)
            dispatched.append(work_id)
            remaining -= work_cost
            decisions[work_id] = {
                **base,
                "action": "dispatch",
                "reason": "Ready, independent, non-duplicate, and within the remaining budget.",
            }
    batches = [] if not dispatched else [
        {
            "batch": 1,
            "work_item_ids": dispatched,
            "reason": "All items are dependency-independent, non-duplicate, and budgeted.",
        }
    ]
    return {
        "id": portfolio_id,
        "round_id": round_id,
        "blueprint_target_ref": ArtifactRef(round_id, target.id, target.revision).to_dict(),
        "work_dependency_dag": [
            {"work_item_id": work_id, "depends_on": list(dag[work_id])}
            for work_id in sorted(dag)
        ],
        "scoring": [
            {
                "work_item_id": work_id,
                "score": scores[work_id]["score"],
                "score_components": dict(scores[work_id]["components"]),
            }
            for work_id in sorted(scores)
        ],
        "ready_portfolio": ready,
        "dispatch_batches": batches,
        "scheduling_decisions": [decisions[work_id] for work_id in sorted(decisions)],
        "budget": {
            "tool_call_limit": tool_call_budget,
            "scheduled_tool_calls": tool_call_budget - remaining,
            "remaining_tool_calls": remaining,
        },
        "replan_event": dict(event),
    }


def _duplicate_work(
    works: Mapping[str, ArtifactRevision],
    scores: Mapping[str, Mapping[str, Any]],
    dag: Mapping[str, Sequence[str]],
) -> dict[str, str]:
    groups: dict[tuple[str, str, str], list[str]] = {}
    for work_id, work in works.items():
        signature = (
            _identifier(work.payload.get("decision_slot_id"), f"Work Item {work_id} decision_slot_id"),
            _nonempty_string(work.payload.get("kind"), f"Work Item {work_id}.kind"),
            _nonempty_string(work.payload.get("scope"), f"Work Item {work_id}.scope"),
        )
        groups.setdefault(signature, []).append(work_id)
    duplicates: dict[str, str] = {}
    for group in groups.values():
        if len(group) > 1:
            canonical = min(
                group,
                key=lambda work_id: _duplicate_canonical_rank(
                    work_id, group, works, scores, dag
                ),
            )
            duplicates.update({work_id: canonical for work_id in group if work_id != canonical})
    return duplicates


def _duplicate_canonical_rank(
    work_id: str,
    group: Sequence[str],
    works: Mapping[str, ArtifactRevision],
    scores: Mapping[str, Mapping[str, Any]],
    dag: Mapping[str, Sequence[str]],
) -> tuple[int, int, int, str]:
    status = _work_status(works[work_id])
    status_rank = {
        "complete": 0,
        "running": 1,
        "ready": 2,
        "planned": 2,
        "deferred": 4,
        "cancelled": 4,
    }.get(status, 3)
    depends_on_peer = any(
        peer != work_id and _depends_on(work_id, peer, dag) for peer in group
    )
    return (status_rank, int(depends_on_peer), -scores[work_id]["score"], work_id)


def _work_status(work: ArtifactRevision) -> str:
    return _nonempty_string(work.payload.get("status"), f"Work Item {work.id}.status")


def _ensure_independent(candidate: str, dispatched: Sequence[str], dag: Mapping[str, Sequence[str]]) -> None:
    for existing in dispatched:
        if _depends_on(candidate, existing, dag) or _depends_on(existing, candidate, dag):
            raise InvalidPortfolioError("scheduler attempted to dispatch dependent Work Items concurrently")


def _depends_on(candidate: str, dependency: str, dag: Mapping[str, Sequence[str]]) -> bool:
    frontier = list(dag[candidate])
    visited: set[str] = set()
    while frontier:
        current = frontier.pop()
        if current == dependency:
            return True
        if current not in visited:
            visited.add(current)
            frontier.extend(dag[current])
    return False


def _work_tool_calls(work: ArtifactRevision) -> int:
    budget = thaw_json(work.payload.get("budget"))
    if not isinstance(budget, Mapping):
        raise InvalidPortfolioError(f"Work Item {work.id}.budget must be a mapping")
    return _positive_int(budget.get("tool_calls"), f"Work Item {work.id}.budget.tool_calls")


def _ensure_id_compatibility(
    artifacts: Sequence[ArtifactRevision], artifact_id: str, expected_kind: str
) -> None:
    foreign = {
        artifact.kind
        for artifact in artifacts
        if artifact.id == artifact_id and artifact.kind != expected_kind
    }
    if foreign:
        raise InvalidPortfolioError(
            f"artifact id {artifact_id!r} is already used by kinds: {sorted(foreign)}"
        )


def _latest_artifact(
    artifacts: Sequence[ArtifactRevision], artifact_id: str, kind: str
) -> ArtifactRevision | None:
    matches = [artifact for artifact in artifacts if artifact.id == artifact_id and artifact.kind == kind]
    return max(matches, key=lambda artifact: artifact.revision, default=None)


def _unique_refs(values: Sequence[ArtifactRef]) -> tuple[ArtifactRef, ...]:
    result: list[ArtifactRef] = []
    seen: set[tuple[str, str, int]] = set()
    for value in values:
        key = (value.round_id, value.artifact_id, value.revision)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def _mapping_sequence(value: Any, label: str, *, allow_empty: bool = False) -> list[Mapping[str, Any]]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidPortfolioError(f"{label} must be a sequence of mappings")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(plain):
        if not isinstance(item, Mapping):
            raise InvalidPortfolioError(f"{label}[{index}] must be a mapping")
        result.append(item)
    if not result and not allow_empty:
        raise InvalidPortfolioError(f"{label} must not be empty")
    return result


def _identifier_sequence(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidPortfolioError(f"{label} must be a sequence of identifiers")
    result = tuple(_identifier(item, label) for item in plain)
    if not result and not allow_empty:
        raise InvalidPortfolioError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise InvalidPortfolioError(f"{label} must not contain duplicate ids")
    return result


def _identifier(value: Any, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise InvalidPortfolioError(str(error)) from error


def _nonempty_string(value: Any, label: str) -> str:
    plain = thaw_json(value)
    if not isinstance(plain, str) or not plain.strip():
        raise InvalidPortfolioError(f"{label} must be a nonempty string")
    return plain


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidPortfolioError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidPortfolioError(f"{label} must be a nonnegative integer")
    return value


def _score_input(value: Any, label: str) -> int:
    number = _nonnegative_int(value, label)
    if number > 100:
        raise InvalidPortfolioError(f"{label} must be at most 100")
    return number


def _level(value: Any, label: str) -> int:
    normalized = _nonempty_string(value, label)
    if normalized not in LEVEL_SCORES:
        raise InvalidPortfolioError(f"{label} is unsupported: {normalized}")
    return LEVEL_SCORES[normalized]


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise InvalidPortfolioError(
            f"{label} has unexpected keys; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
