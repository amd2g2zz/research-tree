"""State expansion, pruning, and stop policy for recursive technical research."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import copy
import hashlib
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .domain import thaw_json
from .evidence_delta import (
    EvidenceBaseline,
    baseline_from_finding_packs,
    measure_realized_delta,
)
from .tree_state import ResearchTreeStateService


_WORKER_VALIDATION_STATUSES = frozenset({"passed", "failed", "inconclusive"})
_WORKER_VALIDATION_NODE_MARKER = "worker_validation_continuation"


@dataclass(frozen=True, slots=True)
class RecursiveSearchConfig:
    max_depth: int = 5
    max_frontier: int = 12
    min_expected_value: float = 0.12
    depth_penalty: float = 0.06
    duplicate_penalty: float = 0.35
    stagnation_penalty: float = 0.25
    validation_failure_boost: float = 0.4
    max_residual_boost: float = 1.0
    max_stagnant_transitions: int = 3

    def __post_init__(self) -> None:
        if self.max_depth < 1 or self.max_frontier < 1:
            raise ValueError("max_depth and max_frontier must be positive")
        for name in (
            "min_expected_value",
            "depth_penalty",
            "duplicate_penalty",
            "stagnation_penalty",
            "validation_failure_boost",
            "max_residual_boost",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.max_stagnant_transitions < 1:
            raise ValueError("max_stagnant_transitions must be positive")


def initialize_research_state(
    *,
    round_id: str,
    tree_id: str,
    decision_slots: Mapping[str, Mapping[str, Any]],
    baseline_findings: Sequence[Any] = (),
    execution_context: Mapping[str, Any] | None = None,
    config: RecursiveSearchConfig | None = None,
) -> dict[str, Any]:
    """Bootstrap a tree from existing evidence without claiming initial gain."""

    cfg = config or RecursiveSearchConfig()
    baseline = baseline_from_finding_packs(baseline_findings)
    slots = {
        slot_id: _slot_state(slot_id, slot)
        for slot_id, slot in sorted(decision_slots.items())
        if str(slot.get("status", "open")) in {"open", "researching"}
    }
    state: dict[str, Any] = {
        "schema": 1,
        "id": tree_id,
        "round_id": round_id,
        "transition_index": 0,
        "status": "searching",
        "config": asdict(cfg),
        "decision_slots": slots,
        "execution_context": copy.deepcopy(dict(execution_context or {})),
        "deliverables": {
            "technical_research_package": {"status": "pending"},
            "human_research_report": {"status": "pending"},
        },
        "nodes": {},
        "frontier_node_ids": [],
        "evidence_baseline": baseline.to_dict(),
        "consumed_finding_ids": list(baseline.finding_ids),
        "delta_history": [],
        "penalty_history": [],
        "stop_reason": None,
    }
    by_slot: dict[str, list[Any]] = {slot_id: [] for slot_id in slots}
    for finding in baseline_findings:
        payload = _payload(finding)
        slot_id = str(payload.get("decision_slot_id", ""))
        if slot_id in by_slot:
            by_slot[slot_id].append(finding)
    for slot_id, slot in slots.items():
        root = _root_node(slot_id, slot)
        state["nodes"][root["id"]] = root
        findings = by_slot[slot_id]
        if not findings:
            continue
        for finding in findings:
            _update_slot_evidence(slot, finding)
            _grow_from_finding(state, root, finding, baseline_event=True)
        _ensure_slot_frontier(state, root, slot, trigger_ref="baseline:closure-gap")
    return evaluate_research_stop(prune_research_state(score_research_frontier(state)))


def apply_research_results(
    state: Mapping[str, Any],
    finding_packs: Sequence[Any],
) -> dict[str, Any]:
    """Apply one evidence batch and recursively create successor actions."""

    result = _mutable_state(state)
    baseline = EvidenceBaseline.from_dict(result["evidence_baseline"])
    consumed = set(result["consumed_finding_ids"])
    fresh = [finding for finding in finding_packs if _finding_id(finding) not in consumed]
    if not fresh:
        return result
    transition_index = int(result["transition_index"]) + 1
    delta, next_baseline = measure_realized_delta(
        baseline,
        fresh,
        transition_index=transition_index,
    )
    result["transition_index"] = transition_index
    result["delta_history"].append(delta)
    result["evidence_baseline"] = next_baseline.to_dict()
    result["consumed_finding_ids"] = sorted(
        consumed | {_finding_id(finding) for finding in fresh}
    )

    for finding in fresh:
        payload = _payload(finding)
        slot_id = str(payload.get("decision_slot_id", ""))
        slot = result["decision_slots"].get(slot_id)
        if not isinstance(slot, dict):
            continue
        parent = _resolve_parent(result, payload, slot_id)
        if parent is None:
            continue
        parent["status"] = "completed"
        parent["realized_delta"] = delta["realized_delta"]
        parent["terminal_reason"] = "Finding Pack ingested"
        _update_slot_evidence(slot, finding)
        _grow_from_finding(result, parent, finding, baseline_event=False)
        if delta["duplicate_only"]:
            parent["stagnation_count"] = int(parent.get("stagnation_count", 0)) + 1
            slot["stagnation_count"] = int(slot.get("stagnation_count", 0)) + 1
            result["penalty_history"].append(
                {
                    "transition_index": transition_index,
                    "node_id": parent["id"],
                    "kind": "no_state_change",
                    "amount": result["config"]["stagnation_penalty"],
                    "finding_id": _finding_id(finding),
                }
            )
        _ensure_slot_frontier(
            result,
            parent,
            slot,
            trigger_ref=f"finding:{_finding_id(finding)}:closure-gap",
        )
    return evaluate_research_stop(prune_research_state(score_research_frontier(result)))


def score_research_frontier(state: Mapping[str, Any]) -> dict[str, Any]:
    """Rank actions by residual decision risk normalized by branch complexity."""

    result = _mutable_state(state)
    cfg = RecursiveSearchConfig(**result["config"])
    for node in result["nodes"].values():
        if node["status"] != "frontier":
            continue
        slot = result["decision_slots"][node["decision_slot_id"]]
        _refresh_slot_residual_risk(slot, cfg)
        mandatory = 1.0 if _is_mandatory(node, slot) else 0.0
        novelty = 1.0 if not _has_completed_equivalent(result, node) else 0.0
        complexity = _branch_complexity(result, node)
        penalty_count = int(node.get("stagnation_count", 0)) + int(
            slot.get("stagnation_count", 0)
        )
        penalty = penalty_count * cfg.stagnation_penalty
        priority_band = {"P0": 3.0, "P1": 2.0, "P2": 1.0}.get(
            str(slot["priority"]), 1.5
        )
        value = priority_band + mandatory + float(slot["residual_risk"]) * novelty / complexity
        value -= int(node["depth"]) * cfg.depth_penalty + penalty
        node["branch_complexity"] = round(complexity, 6)
        node["target_residual_risk"] = slot["residual_risk"]
        node["selection_value"] = round(max(0.0, value), 6)
    result["frontier_node_ids"] = [
        node["id"]
        for node in sorted(
            (node for node in result["nodes"].values() if node["status"] == "frontier"),
            key=lambda item: (-item["selection_value"], item["id"]),
        )
    ]
    return result


def prune_research_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Remove dominated actions from the active frontier without deleting them."""

    result = _mutable_state(state)
    cfg = RecursiveSearchConfig(**result["config"])
    seen: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for node_id in list(result["frontier_node_ids"]):
        node = result["nodes"][node_id]
        key = _node_equivalence_key(node)
        prior = seen.get(key)
        if prior is None:
            seen[key] = node
            continue
        loser, winner = (node, prior) if node["selection_value"] <= prior["selection_value"] else (prior, node)
        loser["status"] = "duplicate"
        loser["terminal_reason"] = f"dominated by equivalent node {winner['id']}"
        seen[key] = winner
    frontier = [node for node in result["nodes"].values() if node["status"] == "frontier"]
    for node in frontier:
        if node["depth"] > cfg.max_depth and not _is_mandatory(
            node, result["decision_slots"][node["decision_slot_id"]]
        ):
            node["status"] = "deferred"
            node["terminal_reason"] = "maximum depth guardrail reached"
        elif node["selection_value"] < cfg.min_expected_value and not _is_mandatory(
            node, result["decision_slots"][node["decision_slot_id"]]
        ):
            node["status"] = "deferred"
            node["terminal_reason"] = "selection value below threshold"
        elif (
            int(result["decision_slots"][node["decision_slot_id"]].get("stagnation_count", 0))
            >= cfg.max_stagnant_transitions
            and not _is_mandatory(node, result["decision_slots"][node["decision_slot_id"]])
        ):
            node["status"] = "deferred"
            node["terminal_reason"] = "subtree produced no state change repeatedly"
    frontier = sorted(
        (node for node in result["nodes"].values() if node["status"] == "frontier"),
        key=lambda item: (-item["selection_value"], item["id"]),
    )
    mandatory_frontier = [
        node
        for node in frontier
        if _is_mandatory(node, result["decision_slots"][node["decision_slot_id"]])
    ]
    optional_frontier = [node for node in frontier if node not in mandatory_frontier]
    optional_capacity = max(0, cfg.max_frontier - len(mandatory_frontier))
    selected = sorted(
        mandatory_frontier + optional_frontier[:optional_capacity],
        key=lambda item: (-item["selection_value"], item["id"]),
    )
    for node in optional_frontier[optional_capacity:]:
        node["status"] = "deferred"
        node["terminal_reason"] = "frontier capacity guardrail reached"
    result["frontier_node_ids"] = [node["id"] for node in selected]
    return result


def select_research_actions(
    state: Mapping[str, Any], *, max_parallelism: int
) -> tuple[Mapping[str, Any], ...]:
    if max_parallelism < 1:
        raise ValueError("max_parallelism must be positive")
    return tuple(
        {
            **state["nodes"][node_id],
            "decision_oracle": state["decision_slots"][
                state["nodes"][node_id]["decision_slot_id"]
            ]["validation_oracle"],
            "execution_context": thaw_json(state["execution_context"]),
        }
        for node_id in state["frontier_node_ids"][:max_parallelism]
    )


class RecursiveResearchCoordinator:
    """Persisted facade for the initialize/select/ingest/recover loop."""

    def __init__(self, store: Any) -> None:
        self._states = ResearchTreeStateService(store)

    def initialize(
        self,
        *,
        round_id: str,
        tree_id: str,
        decision_slots: Mapping[str, Mapping[str, Any]],
        baseline_findings: Sequence[Any] = (),
        execution_context: Mapping[str, Any] | None = None,
        parent_artifacts: Sequence[Any] = (),
        config: RecursiveSearchConfig | None = None,
    ) -> Any:
        state = initialize_research_state(
            round_id=round_id,
            tree_id=tree_id,
            decision_slots=decision_slots,
            baseline_findings=baseline_findings,
            execution_context=execution_context,
            config=config,
        )
        return self._states.initialize(
            round_id=round_id,
            tree_id=tree_id,
            state=state,
            parent_artifacts=parent_artifacts,
            baseline_findings=baseline_findings,
        )

    def next_actions(
        self,
        *,
        round_id: str,
        tree_id: str,
        max_parallelism: int,
    ) -> tuple[Mapping[str, Any], ...]:
        state = self._states.latest(round_id=round_id, tree_id=tree_id)
        return select_research_actions(state.payload, max_parallelism=max_parallelism)

    def ingest(
        self,
        *,
        round_id: str,
        tree_id: str,
        finding_packs: Sequence[Any],
    ) -> Any:
        previous = self._states.latest(round_id=round_id, tree_id=tree_id)
        state = apply_research_results(previous.payload, finding_packs)
        if state["transition_index"] == previous.payload["transition_index"]:
            return previous
        return self._states.transition(
            round_id=round_id,
            previous=previous,
            state=state,
            consumed_findings=finding_packs,
        )

    def recover(self, *, round_id: str, tree_id: str) -> Any:
        previous, pending = self._states.recover_unconsumed(
            round_id=round_id,
            tree_id=tree_id,
        )
        if not pending:
            return previous
        state = apply_research_results(previous.payload, pending)
        return self._states.transition(
            round_id=round_id,
            previous=previous,
            state=state,
            consumed_findings=pending,
        )

    def finalize_delivery(
        self,
        *,
        round_id: str,
        tree_id: str,
        technical_report: Path,
        human_report: Path,
    ) -> Any:
        previous = self._states.latest(round_id=round_id, tree_id=tree_id)
        state = finalize_research_delivery(
            previous.payload,
            technical_report=technical_report,
            human_report=human_report,
        )
        state["transition_index"] = int(previous.payload["transition_index"]) + 1
        return self._states.transition(
            round_id=round_id,
            previous=previous,
            state=state,
            consumed_findings=(),
        )


def finalize_research_delivery(
    state: Mapping[str, Any],
    *,
    technical_report: Path,
    human_report: Path,
) -> dict[str, Any]:
    """Register both deep report artifacts before allowing tree completion."""

    result = _mutable_state(state)
    if not result["decision_slots"] or not all(
        slot["status"] == "closed" for slot in result["decision_slots"].values()
    ):
        raise ValueError("decision-slot closure must pass before delivery registration")
    result["deliverables"] = {
        "technical_research_package": _report_manifest(
            technical_report, kind="technical_research_package", minimum_bytes=1024, minimum_headings=3
        ),
        "human_research_report": _report_manifest(
            human_report, kind="human_research_report", minimum_bytes=512, minimum_headings=2
        ),
    }
    result["status"] = "complete"
    result["stop_reason"] = "decision-slot closure and both research deliverables verified"
    return result


def evaluate_research_stop(state: Mapping[str, Any]) -> dict[str, Any]:
    """Close only when slot oracles pass; an empty frontier alone is not success."""

    result = _mutable_state(state)
    blockers: list[str] = []
    for slot_id, slot in result["decision_slots"].items():
        open_nodes = [
            node
            for node in result["nodes"].values()
            if node["decision_slot_id"] == slot_id and node["status"] == "frontier"
        ]
        if _slot_has_minimum_evidence(slot) and not open_nodes and (
            not slot["validation_required"] or slot["validation_passed"]
        ):
            slot["status"] = "closed"
        else:
            slot["status"] = "researching"
            if not _slot_has_minimum_evidence(slot):
                blockers.append(f"{slot_id}: independent evidence is insufficient")
            if slot["validation_required"] and not slot["validation_passed"]:
                blockers.append(f"{slot_id}: validation oracle has not passed")
            if open_nodes:
                blockers.append(f"{slot_id}: {len(open_nodes)} frontier action(s) remain")
    if result["decision_slots"] and all(
        slot["status"] == "closed" for slot in result["decision_slots"].values()
    ):
        if _deliverables_ready(result["deliverables"]):
            result["status"] = "complete"
            result["stop_reason"] = "decision-slot closure and both research deliverables verified"
        else:
            result["status"] = "delivery_pending"
            result["stop_reason"] = "decision slots closed; both research deliverables are still pending"
    elif result["frontier_node_ids"]:
        result["status"] = "searching"
        result["stop_reason"] = None
    else:
        result["status"] = "blocked"
        result["stop_reason"] = "; ".join(blockers) or "no executable frontier remains"
    return result


def _slot_state(slot_id: str, slot: Mapping[str, Any]) -> dict[str, Any]:
    priority = str(slot.get("priority", "P1"))
    validation = slot.get("validation", {})
    validation_oracle = ""
    if isinstance(validation, Mapping):
        validation_oracle = str(validation.get("oracle", "")).strip()
    return {
        "id": slot_id,
        "question": str(slot.get("question", slot_id)),
        "priority": priority,
        "uncertainty": _uncertainty_value(slot.get("uncertainty", "medium")),
        "status": "researching",
        "finding_ids": [],
        "anchor_fingerprints": [],
        "validation_required": priority == "P0" or bool(validation),
        "validation_oracle": validation_oracle,
        "validation_passed": False,
        "validation_status": "pending",
        "validation_attempts": 0,
        "validation_failures": 0,
        "worker_validation_continuation_epoch": 0,
        "stagnation_count": 0,
        "residual_risk": _priority_value(priority),
    }


def _report_manifest(
    path: Path,
    *,
    kind: str,
    minimum_bytes: int,
    minimum_headings: int,
) -> dict[str, Any]:
    resolved = Path(path).resolve()
    raw = resolved.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{kind} must be UTF-8 without BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{kind} must be UTF-8") from exc
    headings = len(re.findall(r"(?m)^#{1,6}\s+\S", text))
    if len(raw) < minimum_bytes or headings < minimum_headings:
        raise ValueError(
            f"{kind} is too shallow: requires at least {minimum_bytes} bytes and "
            f"{minimum_headings} headings"
        )
    return {
        "status": "verified",
        "kind": kind,
        "path": str(resolved),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "heading_count": headings,
    }


def _deliverables_ready(value: Mapping[str, Any]) -> bool:
    return all(
        isinstance(value.get(key), Mapping) and value[key].get("status") == "verified"
        for key in ("technical_research_package", "human_research_report")
    )


def _root_node(slot_id: str, slot: Mapping[str, Any]) -> dict[str, Any]:
    node = _node(
        node_id=f"root:{slot_id}",
        parent_id=None,
        slot_id=slot_id,
        question=slot["question"],
        action_kind="landscape",
        trigger_ref="initial-intent-and-decision-map",
        evidence_needed="A source map, decisive claims, counterevidence, and explicit open gaps.",
        oracle="The evidence landscape is mapped and successor questions are explicit.",
        depth=0,
        estimated_cost=1.0,
        mandatory=True,
    )
    node["decision_oracle"] = slot["validation_oracle"]
    return node


def _grow_from_finding(
    state: dict[str, Any],
    parent: dict[str, Any],
    finding: Any,
    *,
    baseline_event: bool,
) -> None:
    payload = _payload(finding)
    slot = state["decision_slots"][parent["decision_slot_id"]]
    continuations = list(payload.get("research_continuations", ()))
    continuations.extend(
        {
            "kind": "deep_dive",
            "question": str(item),
            "trigger": "legacy remaining_uncertainty",
            "evidence_needed": "Evidence that resolves this uncertainty.",
            "oracle": "The uncertainty is resolved, bounded, or converted to a fallback.",
            "estimated_cost": 1.0,
        }
        for item in payload.get("remaining_uncertainties", ())
        if str(item).strip()
    )
    for continuation in continuations:
        if not isinstance(continuation, Mapping):
            continue
        question = str(continuation.get("question", "")).strip()
        if not question:
            continue
        _add_node(
            state,
            parent=parent,
            slot=slot,
            question=question,
            action_kind=str(continuation.get("kind", "deep_dive")),
            trigger_ref=(
                f"baseline:{_finding_id(finding)}"
                if baseline_event
                else f"finding:{_finding_id(finding)}"
            ),
            evidence_needed=str(
                continuation.get("evidence_needed", "Decision-relevant evidence with provenance.")
            ),
            oracle=str(continuation.get("oracle", "The question is answered with anchored evidence.")),
            estimated_cost=_positive_float(continuation.get("estimated_cost", 1.0)),
        )
    validation = payload.get("validation_result")
    if not isinstance(validation, Mapping):
        return
    raw_status = validation.get("status")
    if not isinstance(raw_status, str):
        return
    status = raw_status.strip()
    if status not in _WORKER_VALIDATION_STATUSES:
        return
    slot["validation_status"] = (
        "reported_passed_untrusted" if status == "passed" else status
    )
    slot["validation_attempts"] = int(slot.get("validation_attempts", 0)) + 1
    if status == "failed":
        slot["validation_failures"] = int(slot.get("validation_failures", 0)) + 1
    if status == "passed" and not bool(slot.get("validation_passed", False)):
        _ensure_worker_validation_continuation(
            state,
            parent=parent,
            slot=slot,
            trigger_ref=(
                f"baseline:{_finding_id(finding)}:worker-reported-pass"
                if baseline_event
                else f"finding:{_finding_id(finding)}:worker-reported-pass"
            ),
        )


def _ensure_worker_validation_continuation(
    state: dict[str, Any],
    *,
    parent: Mapping[str, Any],
    slot: Mapping[str, Any],
    trigger_ref: str,
) -> None:
    """Keep a worker pass as an active, independently verifiable obligation."""

    active = [
        node
        for node in state["nodes"].values()
        if (
            node.get("decision_slot_id") == slot["id"]
            and node.get("action_kind") == "validation"
            and node.get(_WORKER_VALIDATION_NODE_MARKER) is True
            and node.get("status") in {"frontier", "running"}
        )
    ]
    if active:
        return
    epoch = int(slot.get("worker_validation_continuation_epoch", 0)) + 1
    slot["worker_validation_continuation_epoch"] = epoch
    _add_node(
        state,
        parent=parent,
        slot=slot,
        question=(
            "Produce verifier-needed proof for the worker-reported validation pass "
            f"(continuation epoch {epoch})."
        ),
        action_kind="validation",
        trigger_ref=trigger_ref,
        evidence_needed=(
            "An evaluator-owned or independently verified receipt bound to the "
            "reported claim."
        ),
        oracle=slot["validation_oracle"] or (
            "An independent validation oracle produces a source-bound result."
        ),
        estimated_cost=1.0,
        mandatory=True,
        identity_namespace="worker-validation",
        metadata={
            _WORKER_VALIDATION_NODE_MARKER: True,
            "worker_validation_continuation_epoch": epoch,
        },
    )


def _add_node(
    state: dict[str, Any],
    *,
    parent: Mapping[str, Any],
    slot: Mapping[str, Any],
    question: str,
    action_kind: str,
    trigger_ref: str,
    evidence_needed: str,
    oracle: str,
    estimated_cost: float,
    mandatory: bool = False,
    identity_namespace: str = "question",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    normalized_kind = action_kind if action_kind in {
        "deep_dive", "adversarial", "validation", "method_switch"
    } else "deep_dive"
    namespace = str(identity_namespace).strip() or "question"
    identity = _normalize(question)
    if namespace != "question":
        identity = f"{namespace}:{identity}"
    digest = hashlib.sha256(
        f"{slot['id']}:{normalized_kind}:{identity}".encode("utf-8")
    ).hexdigest()[:16]
    node_id = f"node:{slot['id']}:{digest}"
    if node_id in state["nodes"]:
        return state["nodes"][node_id]
    node = _node(
        node_id=node_id,
        parent_id=parent["id"],
        slot_id=slot["id"],
        question=question,
        action_kind=normalized_kind,
        trigger_ref=trigger_ref,
        evidence_needed=evidence_needed,
        oracle=oracle,
        depth=int(parent["depth"]) + 1,
        estimated_cost=estimated_cost,
        mandatory=mandatory,
        identity_namespace=namespace,
    )
    if metadata:
        node.update(copy.deepcopy(dict(metadata)))
    node["decision_oracle"] = slot["validation_oracle"]
    state["nodes"][node_id] = node
    return node


def _ensure_slot_frontier(
    state: dict[str, Any],
    parent: Mapping[str, Any],
    slot: Mapping[str, Any],
    *,
    trigger_ref: str,
) -> None:
    """Grow mandatory closure work when a worker did not propose it."""

    if _has_open_node(state, slot["id"]):
        return
    if not _slot_has_minimum_evidence(slot):
        _add_node(
            state,
            parent=parent,
            slot=slot,
            question="Triangulate the current claims with an independent source or method.",
            action_kind="deep_dive",
            trigger_ref=trigger_ref,
            evidence_needed="An independent anchor that can confirm or overturn the current claim set.",
            oracle="At least two independent Finding Packs and evidence anchors exist for the slot.",
            estimated_cost=1.0,
            mandatory=True,
        )
    elif slot["validation_required"] and not slot["validation_passed"]:
        attempts = int(slot.get("validation_attempts", 0))
        if slot.get("validation_status") == "failed":
            question = (
                "Re-run the Decision Slot validation oracle with an independent "
                f"method after failed attempt {attempts}."
            )
        elif slot.get("validation_status") == "inconclusive":
            question = (
                "Resolve the inconclusive Decision Slot validation with a different "
                f"method after attempt {attempts}."
            )
        else:
            question = "Execute the Decision Slot validation oracle against the leading conclusion."
        _add_node(
            state,
            parent=parent,
            slot=slot,
            question=question,
            action_kind="validation",
            trigger_ref=trigger_ref,
            evidence_needed="Executed or independently reviewed validation evidence.",
            oracle=slot["validation_oracle"] or (
                "The Decision Slot validation result is explicitly passed, failed, or inconclusive."
            ),
            estimated_cost=1.0,
            mandatory=True,
        )


def _node(**values: Any) -> dict[str, Any]:
    return {
        "id": values["node_id"],
        "parent_id": values["parent_id"],
        "decision_slot_id": values["slot_id"],
        "question": values["question"],
        "action_kind": values["action_kind"],
        "identity_namespace": values.get("identity_namespace", "question"),
        "trigger_ref": values["trigger_ref"],
        "evidence_needed": values["evidence_needed"],
        "oracle": values["oracle"],
        "depth": values["depth"],
        "estimated_cost": values["estimated_cost"],
        "mandatory": bool(values.get("mandatory", False)),
        "branch_complexity": 1.0,
        "target_residual_risk": 0.0,
        "selection_value": 0.0,
        "realized_delta": 0.0,
        "stagnation_count": 0,
        "status": "frontier",
        "terminal_reason": None,
    }


def _update_slot_evidence(slot: dict[str, Any], finding: Any) -> None:
    payload = _payload(finding)
    finding_id = _finding_id(finding)
    if finding_id and finding_id not in slot["finding_ids"]:
        slot["finding_ids"].append(finding_id)
    anchors = set(slot["anchor_fingerprints"])
    for observation in payload.get("observations", ()):
        if not isinstance(observation, Mapping) or not isinstance(observation.get("anchor"), Mapping):
            continue
        anchor = observation["anchor"]
        anchors.add(
            hashlib.sha256(f"{anchor.get('kind')}:{anchor.get('ref')}".encode("utf-8")).hexdigest()
        )
    slot["anchor_fingerprints"] = sorted(anchors)


def _resolve_parent(
    state: Mapping[str, Any], payload: Mapping[str, Any], slot_id: str
) -> dict[str, Any] | None:
    explicit = payload.get("research_node_id")
    if isinstance(explicit, str) and explicit in state["nodes"]:
        return state["nodes"][explicit]
    candidates = [
        node
        for node in state["nodes"].values()
        if node["decision_slot_id"] == slot_id and node["status"] in {"frontier", "running"}
    ]
    if candidates:
        return max(candidates, key=lambda node: (node["depth"], node["selection_value"]))
    return state["nodes"].get(f"root:{slot_id}")


def _has_completed_equivalent(state: Mapping[str, Any], node: Mapping[str, Any]) -> bool:
    key = _node_equivalence_key(node)
    return any(
        other["id"] != node["id"]
        and other["status"] == "completed"
        and _node_equivalence_key(other) == key
        for other in state["nodes"].values()
    )


def _node_equivalence_key(node: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(node["decision_slot_id"]),
        str(node["action_kind"]),
        str(node.get("identity_namespace", "question")),
        _normalize(str(node["question"])),
    )


def _is_mandatory(node: Mapping[str, Any], slot: Mapping[str, Any]) -> bool:
    return bool(node.get("mandatory")) or (
        node["action_kind"] in {"adversarial", "validation"} and slot["priority"] == "P0"
    )


def _refresh_slot_residual_risk(
    slot: dict[str, Any], cfg: RecursiveSearchConfig
) -> None:
    """Update the boosting residual only from observable closure state."""

    finding_deficit = max(0.0, (2 - len(slot["finding_ids"])) / 2)
    anchor_deficit = max(0.0, (2 - len(slot["anchor_fingerprints"])) / 2)
    evidence_deficit = max(finding_deficit, anchor_deficit)
    validation_deficit = (
        1.0 if slot["validation_required"] and not slot["validation_passed"] else 0.0
    )
    closure_deficit = max(evidence_deficit, validation_deficit)
    failure_boost = min(
        cfg.max_residual_boost,
        int(slot.get("validation_failures", 0)) * cfg.validation_failure_boost,
    )
    slot["residual_risk"] = round(
        _priority_value(slot["priority"])
        * float(slot["uncertainty"])
        * closure_deficit
        * (1.0 + failure_boost),
        6,
    )


def _branch_complexity(state: Mapping[str, Any], node: Mapping[str, Any]) -> float:
    """C4.5-style split normalization using observed, not imagined, branches."""

    parent_id = node.get("parent_id")
    if parent_id is None:
        return 1.0
    sibling_count = sum(
        1
        for candidate in state["nodes"].values()
        if candidate.get("parent_id") == parent_id
        and candidate.get("status") not in {"duplicate", "invalid"}
    )
    return 1.0 + math.log2(max(1, sibling_count))


def _slot_has_minimum_evidence(slot: Mapping[str, Any]) -> bool:
    return len(slot["finding_ids"]) >= 2 and len(slot["anchor_fingerprints"]) >= 2


def _has_open_node(state: Mapping[str, Any], slot_id: str) -> bool:
    return any(
        node["decision_slot_id"] == slot_id
        and node["status"] in {"frontier", "running"}
        for node in state["nodes"].values()
    )


def _payload(value: Any) -> Mapping[str, Any]:
    payload = value.payload if hasattr(value, "payload") else value
    return payload if isinstance(payload, Mapping) else {}


def _finding_id(value: Any) -> str:
    payload = _payload(value)
    return str(payload.get("id", getattr(value, "id", ""))).strip()


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _priority_value(value: Any) -> float:
    return {"P0": 1.0, "P1": 0.7, "P2": 0.4}.get(str(value), 0.5)


def _uncertainty_value(value: Any) -> float:
    return {"high": 1.0, "medium": 0.65, "low": 0.3}.get(str(value), 0.65)


def _positive_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 1.0
    return result if result > 0 else 1.0


def _mutable_state(state: Mapping[str, Any]) -> dict[str, Any]:
    thawed = thaw_json(state)
    if not isinstance(thawed, dict):
        raise ValueError("research state must be a mapping")
    return copy.deepcopy(thawed)
