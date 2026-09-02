"""State expansion, pruning, and stop policy for recursive technical research."""

from __future__ import annotations

import copy
import hashlib
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .claims import ProvenanceDescriptor, cluster_provenance_components
from .domain import ArtifactRevision, thaw_json
from .evidence_delta import (
    EvidenceBaseline,
    baseline_from_finding_packs,
    measure_realized_delta,
)
from .run_ledger import RunLedger
from .search_portfolio import (
    BATCH_SOURCE_DEPTH_LEVELS,
    InvalidSearchPortfolioError,
    _mechanism_record,
)
from .tree_state import CanonicalResearchTreeStateService

_WORKER_VALIDATION_STATUSES = frozenset({"passed", "failed", "inconclusive"})
_WORKER_VALIDATION_NODE_MARKER = "worker_validation_continuation"
_HEURISTIC_CONTRADICTION_WEIGHT = 0.6
_HEURISTIC_FRONTIER_WEIGHT = 0.4
_MINIMUM_EVIDENCE = 2
_SOURCE_QUALITY_CONFIDENCE = {"high": 1.0, "medium": 0.8, "low": 0.5}
_ROOT_SOURCE_QUALITY = 1.0
# Declared engagement depth per source (issue #494). Ranks mirror the
# BATCH_SOURCE_DEPTH_LEVELS ordering used by the batch assessment.
_SOURCE_DEPTH_RANK = {"none": 0, "snippet": 1, "summary": 2, "full-source": 3, "experiment": 4}
assert set(_SOURCE_DEPTH_RANK) == set(BATCH_SOURCE_DEPTH_LEVELS)
_SHALLOW_SOURCE_DEPTHS = frozenset({"none", "snippet", "summary"})
_DEEP_SOURCE_DEPTHS = frozenset({"full-source", "experiment"})


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
    transition_budget: int = 64
    novelty_stop_threshold: float = 0.0
    initial_marginal_novelty: float = 1.0
    confidence_damping_min: float = 0.05
    confidence_damping_max: float = 0.35
    quality_weight_expandability: float = 0.3
    quality_weight_completeness: float = 0.3
    quality_weight_heuristic: float = 0.25
    quality_weight_association: float = 0.15
    low_confidence_threshold: float = 0.35

    def __post_init__(self) -> None:
        if self.max_depth < 1 or self.max_frontier < 1:
            raise ValueError("max_depth and max_frontier must be positive")
        if (
            isinstance(self.transition_budget, bool)
            or not isinstance(self.transition_budget, int)
            or self.transition_budget < 1
        ):
            raise ValueError("transition_budget must be a positive integer")
        for name in ("novelty_stop_threshold", "initial_marginal_novelty", "low_confidence_threshold"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if not 0 <= self.confidence_damping_min <= 1 or not 0 <= self.confidence_damping_max <= 1:
            raise ValueError("confidence damping bounds must be between 0 and 1")
        if self.confidence_damping_min > self.confidence_damping_max:
            raise ValueError("confidence_damping_min must not exceed confidence_damping_max")
        weights = (
            self.quality_weight_expandability,
            self.quality_weight_completeness,
            self.quality_weight_heuristic,
            self.quality_weight_association,
        )
        if any(not 0 <= weight <= 1 for weight in weights):
            raise ValueError("quality weights must be between 0 and 1")
        if abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError("quality weights must sum to 1.0")
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
        "schema": 2,
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
        "cross_validation": {},
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
        root["confidence"] = min(_source_quality_value(_payload(finding).get("source_quality")) for finding in findings)
        for finding in findings:
            snapshot = _slot_evidence_snapshot(slot)
            _update_slot_evidence(slot, finding)
            ingest = _grow_from_finding(state, root, finding, baseline_event=True, evidence_snapshot=snapshot)
            _apply_ingest_trust(state, slot, finding, ingest)
        _ensure_slot_frontier(state, root, slot, trigger_ref="baseline:closure-gap")
        _ensure_mechanism_drilldown(state, root, slot, trigger_ref="baseline:closure-gap")
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
    result["consumed_finding_ids"] = sorted(consumed | {_finding_id(finding) for finding in fresh})

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
        snapshot = _slot_evidence_snapshot(slot)
        _update_slot_evidence(slot, finding)
        ingest = _grow_from_finding(result, parent, finding, baseline_event=False, evidence_snapshot=snapshot)
        _apply_ingest_trust(result, slot, finding, ingest)
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
        _ensure_mechanism_drilldown(
            result,
            parent,
            slot,
            trigger_ref=f"finding:{_finding_id(finding)}",
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
        penalty_count = int(node.get("stagnation_count", 0)) + int(slot.get("stagnation_count", 0))
        penalty = penalty_count * cfg.stagnation_penalty
        priority_band = {"P0": 3.0, "P1": 2.0, "P2": 1.0}.get(str(slot["priority"]), 1.5)
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
    budget_exhausted = int(result["transition_index"]) >= cfg.transition_budget
    for node in frontier:
        slot = result["decision_slots"][node["decision_slot_id"]]
        mandatory = _is_mandatory(node, slot)
        if node["depth"] > cfg.max_depth and not mandatory:
            node["status"] = "deferred"
            node["terminal_reason"] = "maximum depth guardrail reached"
        elif budget_exhausted and not mandatory:
            node["status"] = "deferred"
            node["terminal_reason"] = "budget-exhausted"
        elif _slot_evidence_saturated(result, slot, cfg) and not mandatory:
            node["status"] = "deferred"
            node["terminal_reason"] = "evidence-saturated"
        elif node["selection_value"] < cfg.min_expected_value and not mandatory:
            node["status"] = "deferred"
            node["terminal_reason"] = "selection value below threshold"
        elif int(slot.get("stagnation_count", 0)) >= cfg.max_stagnant_transitions and not mandatory:
            node["status"] = "deferred"
            node["terminal_reason"] = "subtree produced no state change repeatedly"
    frontier = sorted(
        (node for node in result["nodes"].values() if node["status"] == "frontier"),
        key=lambda item: (-item["selection_value"], item["id"]),
    )
    mandatory_frontier = [
        node for node in frontier if _is_mandatory(node, result["decision_slots"][node["decision_slot_id"]])
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


def select_research_actions(state: Mapping[str, Any], *, max_parallelism: int) -> tuple[Mapping[str, Any], ...]:
    if max_parallelism < 1:
        raise ValueError("max_parallelism must be positive")
    return tuple(
        {
            **state["nodes"][node_id],
            "decision_oracle": state["decision_slots"][state["nodes"][node_id]["decision_slot_id"]][
                "validation_oracle"
            ],
            "execution_context": thaw_json(state["execution_context"]),
        }
        for node_id in state["frontier_node_ids"][:max_parallelism]
    )


class CanonicalRecursiveResearchCoordinator:
    """Persist recursive research transitions in one canonical RunLedger."""

    def __init__(self, ledger: RunLedger) -> None:
        self._states = CanonicalResearchTreeStateService(ledger)

    def initialize(
        self,
        *,
        round_id: str,
        tree_id: str,
        decision_slots: Mapping[str, Mapping[str, Any]],
        expected_revision: int,
        baseline_findings: Sequence[ArtifactRevision] = (),
        execution_context: Mapping[str, Any] | None = None,
        parent_artifacts: Sequence[ArtifactRevision] = (),
        config: RecursiveSearchConfig | None = None,
    ) -> ArtifactRevision:
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
            expected_revision=expected_revision,
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
        finding_packs: Sequence[ArtifactRevision],
        expected_revision: int,
    ) -> ArtifactRevision:
        previous = self._states.latest(round_id=round_id, tree_id=tree_id)
        contributing, _deferred = self._goal_contributing(round_id, finding_packs)
        if not contributing:
            return previous
        state = apply_research_results(previous.payload, contributing)
        if state["transition_index"] == previous.payload["transition_index"]:
            return previous
        return self._states.transition(
            round_id=round_id,
            previous=previous,
            state=state,
            consumed_findings=contributing,
            expected_revision=expected_revision,
        )

    def recover(
        self,
        *,
        round_id: str,
        tree_id: str,
        expected_revision: int,
    ) -> ArtifactRevision:
        previous, pending = self._states.recover_unconsumed(
            round_id=round_id,
            tree_id=tree_id,
        )
        if not pending:
            return previous
        contributing, _deferred = self._goal_contributing(round_id, pending)
        if not contributing:
            return previous
        state = apply_research_results(previous.payload, contributing)
        return self._states.transition(
            round_id=round_id,
            previous=previous,
            state=state,
            consumed_findings=contributing,
            expected_revision=expected_revision,
        )

    def _goal_contributing(self, round_id: str, finding_packs):
        """Drop packs whose goal-contribution verdict blocks tree consumption."""

        if not finding_packs:
            return (), ()
        from .coordinator import partition_goal_contributions

        return partition_goal_contributions(self._states._ledger, round_id, finding_packs)

    def finalize_delivery(
        self,
        *,
        round_id: str,
        tree_id: str,
        technical_report: Path,
        human_report: Path,
        expected_revision: int,
    ) -> ArtifactRevision:
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
            expected_revision=expected_revision,
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
    for manifest in result["deliverables"].values():
        manifest["status"] = "observed"
    result["status"] = "delivery_pending"
    result["stop_reason"] = "report manifests observed; coordinator must verify delivery and acceptance"
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
        slot["status"] = "researching"
        landscape_required = bool(slot.get("landscape_required", True))
        shallow_refs = _shallow_source_refs(slot) if landscape_required else ()
        mechanism_missing = _missing_mechanism_refs(slot) if landscape_required else ()
        slot_blockers: list[str] = []
        if (
            _slot_has_minimum_evidence(slot)
            and not open_nodes
            and not shallow_refs
            and not mechanism_missing
            and (not slot["validation_required"] or slot["validation_passed"])
        ):
            slot_blockers.append(f"{slot_id}: closure candidate requires coordinator assessment")
        if not _slot_has_minimum_evidence(slot):
            slot_blockers.append(f"{slot_id}: independent evidence is insufficient")
        if slot["validation_required"] and not slot["validation_passed"]:
            slot_blockers.append(f"{slot_id}: validation oracle has not passed")
        if shallow_refs:
            slot_blockers.append(f"{slot_id}: shallow source depth blocks landscape closure: {', '.join(shallow_refs)}")
        if mechanism_missing:
            slot_blockers.append(
                f"{slot_id}: promoted sources without mechanism artifacts: {', '.join(mechanism_missing)}"
            )
        if open_nodes:
            slot_blockers.append(f"{slot_id}: {len(open_nodes)} frontier action(s) remain")
        slot["closure_blockers"] = slot_blockers
        blockers.extend(slot_blockers)
    if result["decision_slots"] and all(slot["status"] == "closed" for slot in result["decision_slots"].values()):
        result["status"] = "delivery_pending"
        result["stop_reason"] = "coordinator must assess slot closure and delivery obligations"
    elif result["frontier_node_ids"]:
        result["status"] = "searching"
        result["stop_reason"] = None
    else:
        result["status"] = "blocked"
        result["stop_reason"] = "; ".join(blockers) or "no executable frontier remains"
    result["recursion_receipt"] = _recursion_receipt(result)
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
        "contradiction_refs": [],
        "quarantined_finding_ids": [],
        "trusted_anchor_fingerprints": [],
        "search_comparison": {"provider_fanout": 0, "duplicates": 0, "captures": 0},
        "residual_risk": _priority_value(priority),
        "landscape_required": bool(slot.get("landscape_required", True)),
        "source_depths": {},
        "mechanism_source_refs": [],
        "closure_blockers": [],
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
            f"{kind} is too shallow: requires at least {minimum_bytes} bytes and {minimum_headings} headings"
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
    evidence_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _payload(finding)
    cfg = RecursiveSearchConfig(**state["config"])
    slot = state["decision_slots"][parent["decision_slot_id"]]
    snapshot = evidence_snapshot or _slot_evidence_snapshot(slot)
    _absorb_cross_comparison(slot, payload)
    continuations = list(payload.get("research_continuations", ()))
    continuations.extend(
        {
            "kind": "deep_dive",
            "question": str(item),
            "trigger": "remaining_uncertainty",
            "evidence_needed": "Evidence that resolves this uncertainty.",
            "oracle": "The uncertainty is resolved, bounded, or converted to a fallback.",
            "estimated_cost": 1.0,
        }
        for item in payload.get("remaining_uncertainties", ())
        if str(item).strip()
    )
    known_ids = set(state["nodes"])
    created: list[dict[str, Any]] = []
    for continuation in continuations:
        if not isinstance(continuation, Mapping):
            continue
        question = str(continuation.get("question", "")).strip()
        if not question:
            continue
        node = _add_node(
            state,
            parent=parent,
            slot=slot,
            question=question,
            action_kind=str(continuation.get("kind", "deep_dive")),
            trigger_ref=(f"baseline:{_finding_id(finding)}" if baseline_event else f"finding:{_finding_id(finding)}"),
            evidence_needed=str(continuation.get("evidence_needed", "Decision-relevant evidence with provenance.")),
            oracle=str(continuation.get("oracle", "The question is answered with anchored evidence.")),
            estimated_cost=_positive_float(continuation.get("estimated_cost", 1.0)),
        )
        if node["id"] not in known_ids:
            created.append(node)
    quality, _marginal = _ingest_quality(state, slot, payload, snapshot, new_children=len(created), cfg=cfg)
    damping = cfg.confidence_damping_min + (cfg.confidence_damping_max - cfg.confidence_damping_min) * (1.0 - quality)
    child_confidence = round(float(parent.get("confidence", 1.0)) * (1.0 - damping), 6)
    for node in created:
        node["confidence"] = child_confidence
        node["damping"] = round(damping, 6)
        node["quality"] = quality
    ingest = {
        "confidence": child_confidence,
        "damping": round(damping, 6),
        "quality": quality,
        "baseline": bool(baseline_event),
        "anchor_fingerprints": _finding_anchor_fingerprints(payload),
    }
    validation = payload.get("validation_result")
    if not isinstance(validation, Mapping):
        return ingest
    raw_status = validation.get("status")
    if not isinstance(raw_status, str):
        return ingest
    status = raw_status.strip()
    if status not in _WORKER_VALIDATION_STATUSES:
        return ingest
    slot["validation_status"] = "reported_passed_untrusted" if status == "passed" else status
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
    return ingest


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
            f"Produce verifier-needed proof for the worker-reported validation pass (continuation epoch {epoch})."
        ),
        action_kind="validation",
        trigger_ref=trigger_ref,
        evidence_needed=("An evaluator-owned or independently verified receipt bound to the reported claim."),
        oracle=slot["validation_oracle"] or ("An independent validation oracle produces a source-bound result."),
        estimated_cost=1.0,
        mandatory=True,
        identity_namespace="worker-validation",
        metadata={
            _WORKER_VALIDATION_NODE_MARKER: True,
            "worker_validation_continuation_epoch": epoch,
        },
        confidence=_closure_growth_confidence(state, parent),
        damping=RecursiveSearchConfig(**state["config"]).confidence_damping_max,
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
    confidence: float | None = None,
    damping: float | None = None,
    quality: float | None = None,
) -> dict[str, Any] | None:
    normalized_kind = (
        action_kind if action_kind in {"deep_dive", "adversarial", "validation", "method_switch"} else "deep_dive"
    )
    namespace = str(identity_namespace).strip() or "question"
    identity = _normalize(question)
    if namespace != "question":
        identity = f"{namespace}:{identity}"
    digest = hashlib.sha256(f"{slot['id']}:{normalized_kind}:{identity}".encode("utf-8")).hexdigest()[:16]
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
    if confidence is not None:
        node["confidence"] = float(confidence)
    if damping is not None:
        node["damping"] = float(damping)
    if quality is not None:
        node["quality"] = float(quality)
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
    """Grow mandatory closure work when a worker did not propose it.

    A failed validation oracle demands the independent-method retry before
    anything else; otherwise unmet evidence minimums grow triangulation, and
    a never-attempted required validation grows the validation node.
    """

    if _has_open_node(state, slot["id"]):
        return
    cfg = RecursiveSearchConfig(**state["config"])
    validation_pending = bool(slot["validation_required"]) and not bool(slot["validation_passed"])
    failed_validation = validation_pending and int(slot.get("validation_failures", 0)) > 0
    retry_question = ""
    if failed_validation:
        attempts = int(slot.get("validation_attempts", 0))
        retry_question = (
            f"Re-run the Decision Slot validation oracle with an independent method after failed attempt {attempts}."
        )
    if failed_validation:
        _reopen_completed_obligation(
            _add_node(
                state,
                parent=parent,
                slot=slot,
                question=retry_question,
                action_kind="validation",
                trigger_ref=trigger_ref,
                evidence_needed="Executed or independently reviewed validation evidence.",
                oracle=slot["validation_oracle"]
                or ("The Decision Slot validation result is explicitly passed, failed, or inconclusive."),
                estimated_cost=1.0,
                mandatory=True,
                confidence=_closure_growth_confidence(state, parent),
                damping=cfg.confidence_damping_max,
            )
        )
    elif not _slot_has_minimum_evidence(slot):
        _reopen_completed_obligation(
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
                confidence=_closure_growth_confidence(state, parent),
                damping=cfg.confidence_damping_max,
            )
        )
    elif validation_pending:
        _reopen_completed_obligation(
            _add_node(
                state,
                parent=parent,
                slot=slot,
                question="Execute the Decision Slot validation oracle against the leading conclusion.",
                action_kind="validation",
                trigger_ref=trigger_ref,
                evidence_needed="Executed or independently reviewed validation evidence.",
                oracle=slot["validation_oracle"]
                or ("The Decision Slot validation result is explicitly passed, failed, or inconclusive."),
                estimated_cost=1.0,
                mandatory=True,
                confidence=_closure_growth_confidence(state, parent),
                damping=cfg.confidence_damping_max,
            )
        )


def _shallow_source_refs(slot: Mapping[str, Any]) -> tuple[str, ...]:
    """Sources declared at none/snippet/summary engagement depth (issue #494)."""

    depths = slot.get("source_depths") or {}
    return tuple(sorted(ref for ref, depth in depths.items() if depth in _SHALLOW_SOURCE_DEPTHS))


def _missing_mechanism_refs(slot: Mapping[str, Any]) -> tuple[str, ...]:
    """Sources engaged at promoted depth without a valid mechanism record."""

    depths = slot.get("source_depths") or {}
    covered = set(slot.get("mechanism_source_refs") or ())
    return tuple(sorted(ref for ref, depth in depths.items() if depth in _DEEP_SOURCE_DEPTHS and ref not in covered))


def _ensure_mechanism_drilldown(
    state: dict[str, Any],
    parent: Mapping[str, Any],
    slot: dict[str, Any],
    *,
    trigger_ref: str,
) -> None:
    """Schedule the deeper follow-up batch for shallow or mechanism-missing sources.

    Issue #494: shallow source engagement must not merely downgrade a score —
    it blocks landscape closure and triggers a mandatory deeper action on the
    same source. One identity-deduplicated node per named source.
    """

    if not slot.get("landscape_required", True):
        return
    targets = sorted(set(_shallow_source_refs(slot)) | set(_missing_mechanism_refs(slot)))
    if not targets:
        return
    cfg = RecursiveSearchConfig(**state["config"])
    for ref in targets:
        _reopen_completed_obligation(
            _add_node(
                state,
                parent=parent,
                slot=slot,
                question=(
                    f"Drill into {ref}: engage the source at full-source depth and record its "
                    "mechanism with evidence beyond the README."
                ),
                action_kind="deep_dive",
                trigger_ref=f"{trigger_ref}:mechanism-drilldown",
                evidence_needed=(
                    "Full-source or experiment engagement with the named source plus a mechanism "
                    "record citing inspected code, a design doc, or an experiment."
                ),
                oracle=(
                    "The named source is engaged at full-source or experiment depth and its "
                    "mechanism record cites evidence beyond the README."
                ),
                estimated_cost=1.0,
                mandatory=True,
                confidence=_closure_growth_confidence(state, parent),
                damping=cfg.confidence_damping_max,
            )
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
        "confidence": float(values.get("confidence", 0.5)),
        "damping": float(values.get("damping", 0.0)),
        "quality": values.get("quality"),
        "status": "frontier",
        "terminal_reason": None,
    }


def _update_slot_evidence(slot: dict[str, Any], finding: Any) -> None:
    payload = _payload(finding)
    finding_id = _finding_id(finding)
    if finding_id and finding_id not in slot["finding_ids"]:
        slot["finding_ids"].append(finding_id)
    slot["anchor_fingerprints"] = sorted(set(slot["anchor_fingerprints"]) | _finding_anchor_fingerprints(payload))
    slot["claim_fingerprints"] = sorted(set(slot.get("claim_fingerprints", ())) | _finding_claim_fingerprints(payload))
    slot["effect_fingerprints"] = sorted(
        set(slot.get("effect_fingerprints", ()))
        | {
            hashlib.sha256(f"{item.get('option')}:{item.get('effect')}".encode("utf-8")).hexdigest()
            for item in payload.get("option_effects", ())
            if isinstance(item, Mapping)
        }
    )
    _absorb_source_depths(slot, payload)
    _absorb_mechanism_record(slot, payload)


def _absorb_source_depths(slot: dict[str, Any], payload: Mapping[str, Any]) -> None:
    """Record the deepest declared engagement per cited source (issue #494).

    A source is drilled once it has been engaged at full-source/experiment
    depth; re-declaring it shallowly later cannot un-drill it, while a source
    whose best engagement is still snippet/summary stays a closure blocker.
    """

    declared = payload.get("sources")
    if not isinstance(declared, (list, tuple)) or isinstance(declared, (str, bytes)):
        return
    depths = slot.setdefault("source_depths", {})
    for item in declared:
        if not isinstance(item, Mapping):
            continue
        ref = str(item.get("ref", "")).strip()
        depth = str(item.get("depth", "")).strip()
        if not ref or depth not in _SOURCE_DEPTH_RANK:
            continue
        prior = depths.get(ref)
        if prior is None or _SOURCE_DEPTH_RANK[depth] > _SOURCE_DEPTH_RANK[prior]:
            depths[ref] = depth


def _absorb_mechanism_record(slot: dict[str, Any], payload: Mapping[str, Any]) -> None:
    """Mark a source mechanism-covered when its record satisfies the contract.

    Absorption is lenient by design (issue #494): a malformed or README-only
    record does not reject the evidence batch — the source simply stays
    mechanism-missing and the drill-down loop asks for the real artifact.
    """

    raw = payload.get("mechanism")
    if not isinstance(raw, Mapping):
        return
    try:
        record = _mechanism_record(raw)
    except InvalidSearchPortfolioError:
        return
    covered = slot.setdefault("mechanism_source_refs", [])
    if record.source_ref not in covered:
        covered.append(record.source_ref)


def _resolve_parent(state: Mapping[str, Any], payload: Mapping[str, Any], slot_id: str) -> dict[str, Any] | None:
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
        other["id"] != node["id"] and other["status"] == "completed" and _node_equivalence_key(other) == key
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


def _refresh_slot_residual_risk(slot: dict[str, Any], cfg: RecursiveSearchConfig) -> None:
    """Update the boosting residual only from observable closure state."""

    evidence_deficit = _slot_closure_deficit(slot)
    validation_deficit = 1.0 if slot["validation_required"] and not slot["validation_passed"] else 0.0
    closure_deficit = max(evidence_deficit, validation_deficit)
    failure_boost = min(
        cfg.max_residual_boost,
        int(slot.get("validation_failures", 0)) * cfg.validation_failure_boost,
    )
    slot["residual_risk"] = round(
        _priority_value(slot["priority"]) * float(slot["uncertainty"]) * closure_deficit * (1.0 + failure_boost),
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
        if candidate.get("parent_id") == parent_id and candidate.get("status") not in {"duplicate", "invalid"}
    )
    return 1.0 + math.log2(max(1, sibling_count))


def _slot_has_minimum_evidence(slot: Mapping[str, Any]) -> bool:
    """Satisfied evidence excludes quarantined low-confidence findings."""
    quarantined = set(slot.get("quarantined_finding_ids", ()))
    trusted_findings = len(set(slot["finding_ids"]) - quarantined)
    if quarantined:
        anchors = slot.get("trusted_anchor_fingerprints") or ()
    else:
        anchors = slot["anchor_fingerprints"]
    return trusted_findings >= _MINIMUM_EVIDENCE and len(anchors) >= _MINIMUM_EVIDENCE


def _has_open_node(state: Mapping[str, Any], slot_id: str) -> bool:
    return any(
        node["decision_slot_id"] == slot_id and node["status"] in {"frontier", "running"}
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


def _slot_evidence_snapshot(slot: Mapping[str, Any]) -> dict[str, Any]:
    """Pre-ingest evidence state used to measure marginal quality."""
    return {
        "finding_ids": frozenset(slot["finding_ids"]),
        "findings": len(slot["finding_ids"]),
        "anchors": frozenset(slot["anchor_fingerprints"]),
        "contradictions": frozenset(slot.get("contradiction_refs", ())),
        "claims": frozenset(slot.get("claim_fingerprints", ())),
        "effects": frozenset(slot.get("effect_fingerprints", ())),
        "quarantined": frozenset(slot.get("quarantined_finding_ids", ())),
        "trusted_anchors": frozenset(slot.get("trusted_anchor_fingerprints", ())),
    }


def _closure_deficit_from_counts(findings: int, anchors: int) -> float:
    finding_deficit = max(0.0, (_MINIMUM_EVIDENCE - findings) / 2)
    anchor_deficit = max(0.0, (_MINIMUM_EVIDENCE - anchors) / 2)
    return max(finding_deficit, anchor_deficit)


def _slot_closure_deficit(slot: Mapping[str, Any]) -> float:
    """Closure deficit counts trusted findings and trusted anchors only."""
    quarantined = set(slot.get("quarantined_finding_ids", ()))
    findings = len(set(slot["finding_ids"]) - quarantined)
    anchors = slot.get("trusted_anchor_fingerprints", ()) if quarantined else slot["anchor_fingerprints"]
    return _closure_deficit_from_counts(findings, len(anchors))


def _finding_anchor_fingerprints(payload: Mapping[str, Any]) -> frozenset[str]:
    anchors: set[str] = set()
    for observation in payload.get("observations", ()):
        if not isinstance(observation, Mapping) or not isinstance(observation.get("anchor"), Mapping):
            continue
        anchor = observation["anchor"]
        anchors.add(hashlib.sha256(f"{anchor.get('kind')}:{anchor.get('ref')}".encode("utf-8")).hexdigest())
    return frozenset(anchors)


def _source_quality_value(value: Any) -> float:
    """Missing or unknown capture quality defaults to the conservative 0.5."""
    return _SOURCE_QUALITY_CONFIDENCE.get(str(value), 0.5)


def _closure_growth_confidence(state: Mapping[str, Any], parent: Mapping[str, Any]) -> float:
    """Mandatory closure work descends at the declared worst-case damping."""
    cfg = RecursiveSearchConfig(**state["config"])
    return round(float(parent.get("confidence", 1.0)) * (1.0 - cfg.confidence_damping_max), 6)


def _absorb_cross_comparison(slot: dict[str, Any], payload: Mapping[str, Any]) -> None:
    """Merge cross-comparison contradictions and measured totals into the slot."""
    resolved = {str(item) for item in payload.get("resolved_contradictions", ()) if str(item).strip()}
    if resolved:
        slot["contradiction_refs"] = [ref for ref in slot.get("contradiction_refs", []) if ref not in resolved]
    for item in payload.get("contradictions", ()):
        ref = str(item).strip()
        if ref and ref not in slot["contradiction_refs"]:
            slot["contradiction_refs"].append(ref)
    comparison = payload.get("search_comparison")
    if isinstance(comparison, Mapping):
        for item in comparison.get("contradictions", ()):
            ref = str(item).strip()
            if ref and ref not in slot["contradiction_refs"]:
                slot["contradiction_refs"].append(ref)
        totals = slot.setdefault("search_comparison", {"provider_fanout": 0, "coverage_met": 0, "batches": {}})
        totals["provider_fanout"] = max(
            int(totals.get("provider_fanout", 0)), int(comparison.get("provider_fanout", 0))
        )
        totals["coverage_met"] = max(int(totals.get("coverage_met", 0)), int(comparison.get("coverage_met", 0) or 0))
        batch_key = str(comparison.get("comparison_id") or "").strip() or _comparison_key(comparison)
        batches = totals.setdefault("batches", {})
        batches[batch_key] = {
            "duplicates": int(comparison.get("duplicates", 0) or 0),
            "captures": int(comparison.get("captures", 0) or 0),
            "coverage_met": int(comparison.get("coverage_met", 0) or 0),
        }


def _ingest_quality(
    state: Mapping[str, Any],
    slot: dict[str, Any],
    payload: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    new_children: int,
    cfg: RecursiveSearchConfig,
) -> tuple[float, bool]:
    """Measure the four recursion-quality dimensions for one evidence ingest.

    Completeness is measured against a snapshot excluding the finding under
    judgment (H3b/M4): a finding cannot credit itself with the gap it
    appears to close. The slot's marginal novelty is recorded per-slot (M6),
    never derived from the global last-transition delta.
    """

    finding_id = str(payload.get("id", "")).strip()
    finding_anchors = _finding_anchor_fingerprints(payload)
    new_anchors = len(finding_anchors - set(snapshot["anchors"]))
    expandability = new_anchors / max(1, len(finding_anchors))

    quarantined_before = set(snapshot["quarantined"])
    trusted_before = len(set(snapshot["finding_ids"]) - quarantined_before)
    anchors_before = snapshot["trusted_anchors"] if quarantined_before else snapshot["anchors"]
    deficit_before = _closure_deficit_from_counts(trusted_before, len(anchors_before))
    others_now = set(slot["finding_ids"]) - set(slot.get("quarantined_finding_ids", ())) - {finding_id}
    deficit_after = _closure_deficit_from_counts(len(others_now), len(anchors_before))
    completeness = max(0.0, min(1.0, 1.0 - deficit_after / deficit_before)) if deficit_before > 0 else 0.0

    new_claims = len(_finding_claim_fingerprints(payload) - set(snapshot["claims"]))
    new_effects = len(
        {
            hashlib.sha256(f"{item.get('option')}:{item.get('effect')}".encode("utf-8")).hexdigest()
            for item in payload.get("option_effects", ())
            if isinstance(item, Mapping)
        }
        - set(snapshot["effects"])
    )
    new_contradictions = len(
        {str(item) for item in payload.get("contradictions", ())} - set(snapshot["contradictions"])
    )
    heuristic = _HEURISTIC_CONTRADICTION_WEIGHT * min(
        1.0, float(new_contradictions)
    ) + _HEURISTIC_FRONTIER_WEIGHT * min(1.0, float(new_children))
    cross_links = sum(
        1
        for other_id, other in state["decision_slots"].items()
        if other_id != slot["id"] and set(other["anchor_fingerprints"]) & finding_anchors
    )
    association = min(1.0, cross_links / 2)
    marginal = bool(new_anchors or new_claims or new_effects or new_contradictions or new_children)
    slot["marginal_novelty"] = 1.0 if marginal else 0.0
    return (
        round(
            cfg.quality_weight_expandability * expandability
            + cfg.quality_weight_completeness * completeness
            + cfg.quality_weight_heuristic * heuristic
            + cfg.quality_weight_association * association,
            6,
        ),
        marginal,
    )


def _apply_ingest_trust(
    state: dict[str, Any],
    slot: dict[str, Any],
    finding: Any,
    ingest: Mapping[str, Any],
) -> None:
    """Quarantine low-confidence evidence and record cross-validation objectively.

    A finding whose ingest confidence falls below the declared threshold is
    quarantined: it cannot count toward satisfied evidence until a trusted
    finding restates one of its claims from a disjoint provenance cluster
    (corroboration = claim overlap plus cluster independence; sharing an
    anchor means the same source and never lifts quarantine) or an explicit
    verification pass clears it. Verification failures stay recorded with
    attempts and reason; nothing is dropped silently.
    """

    payload = _payload(finding)
    finding_id = _finding_id(finding)
    cfg = RecursiveSearchConfig(**state["config"])
    ledger = state.setdefault("cross_validation", {})
    ingest_claims = _finding_claim_fingerprints(payload)
    ingest_clusters = _finding_cluster_labels(payload)
    verification = payload.get("verification")
    if isinstance(verification, Mapping) and str(verification.get("status", "")).strip() in {
        "passed",
        "failed",
        "inconclusive",
    }:
        target = str(verification.get("target_finding_id") or finding_id).strip()
        status = str(verification.get("status")).strip()
        record = dict(
            ledger.get(target)
            or {
                "status": "required",
                "attempts": 0,
                "reason": "",
                "anchor_fingerprints": sorted(ingest["anchor_fingerprints"]),
                "claim_fingerprints": sorted(ingest_claims),
                "cluster_labels": sorted(ingest_clusters),
            }
        )
        record["attempts"] = int(record.get("attempts", 0)) + 1
        record["reason"] = str(verification.get("reason", "") or f"verification-{status}")
        record["status"] = "verified" if status == "passed" else "failed"
        ledger[target] = record
        if record["status"] == "verified":
            _lift_quarantine(slot, target, record)
    trusted = bool(ingest["baseline"]) or float(ingest["confidence"]) >= cfg.low_confidence_threshold
    if trusted and finding_id:
        for other_id in list(slot.get("quarantined_finding_ids", ())):
            other = dict(ledger.get(other_id) or {})
            claim_overlap = set(other.get("claim_fingerprints", ())) & set(ingest_claims)
            cluster_overlap = set(other.get("cluster_labels", ())) & set(ingest_clusters)
            if claim_overlap and not cluster_overlap:
                other["status"] = "corroborated"
                ledger[other_id] = other
                _lift_quarantine(slot, other_id, other)
    if trusted:
        if finding_id:
            slot["trusted_anchor_fingerprints"] = sorted(
                set(slot.get("trusted_anchor_fingerprints", ())) | set(ingest["anchor_fingerprints"])
            )
    elif finding_id and finding_id not in slot.get("quarantined_finding_ids", ()):
        slot["quarantined_finding_ids"].append(finding_id)
        ledger[finding_id] = {
            "status": "required",
            "attempts": int(ledger.get(finding_id, {}).get("attempts", 0)),
            "reason": "confidence-below-threshold",
            "confidence": ingest["confidence"],
            "anchor_fingerprints": sorted(ingest["anchor_fingerprints"]),
            "claim_fingerprints": sorted(ingest_claims),
            "cluster_labels": sorted(ingest_clusters),
        }


def _lift_quarantine(slot: dict[str, Any], finding_id: str, record: Mapping[str, Any]) -> None:
    if finding_id in slot.get("quarantined_finding_ids", ()):
        slot["quarantined_finding_ids"] = [item for item in slot["quarantined_finding_ids"] if item != finding_id]
    slot["trusted_anchor_fingerprints"] = sorted(
        set(slot.get("trusted_anchor_fingerprints", ())) | set(record.get("anchor_fingerprints", ()))
    )


def _slot_evidence_saturated(state: Mapping[str, Any], slot: Mapping[str, Any], cfg: RecursiveSearchConfig) -> bool:
    """True when no continue-signal holds: no contradictions, coverage met, novelty spent.

    Novelty is attributed per slot from that slot's own latest ingest (M6),
    and once a batch comparison has been recorded for the slot, saturation is
    additionally gated on the measured intent coverage from that comparison:
    captured-but-never-complete coverage stays a coverage gap (M6/H1).
    """

    if slot.get("contradiction_refs"):
        return False
    if not _slot_has_minimum_evidence(slot):
        return False
    comparison = slot.get("search_comparison") or {}
    captures = sum(int(batch.get("captures", 0)) for batch in (comparison.get("batches") or {}).values())
    if captures > 0 and int(comparison.get("coverage_met", 0)) < 1:
        return False
    marginal = float(slot.get("marginal_novelty", cfg.initial_marginal_novelty))
    return marginal <= cfg.novelty_stop_threshold


def _recursion_receipt(result: Mapping[str, Any]) -> dict[str, Any]:
    """Run-level falsifiability signals: stop reasons, fan-out, dedup, confidence."""
    cfg = RecursiveSearchConfig(**result["config"])
    distribution: dict[str, int] = {}
    for node in result["nodes"].values():
        if node["status"] == "deferred" and node.get("terminal_reason"):
            distribution[node["terminal_reason"]] = distribution.get(node["terminal_reason"], 0) + 1
    confidences = [float(node["confidence"]) for node in result["nodes"].values()]
    fanout = 0
    duplicates = 0
    captures = 0
    for slot in result["decision_slots"].values():
        comparison = slot.get("search_comparison") or {}
        fanout = max(fanout, int(comparison.get("provider_fanout", 0)))
        for batch in (comparison.get("batches") or {}).values():
            duplicates += int(batch.get("duplicates", 0))
            captures += int(batch.get("captures", 0))
    cross_validation = result.get("cross_validation") or {}
    quarantine_live = sum(len(slot.get("quarantined_finding_ids", ())) for slot in result["decision_slots"].values())
    return {
        "terminal_reason_distribution": dict(sorted(distribution.items())),
        "provider_fanout": fanout,
        "dedup_ratio": round(duplicates / captures, 6) if captures else 0.0,
        "quarantine_count": quarantine_live,
        "cross_validation_records": len(cross_validation),
        "cross_validation_failures": sum(1 for record in cross_validation.values() if record.get("status") == "failed"),
        "confidence": {
            "min": min(confidences) if confidences else 1.0,
            "max": max(confidences) if confidences else 1.0,
            "count": len(confidences),
            "damping_min": cfg.confidence_damping_min,
            "damping_max": cfg.confidence_damping_max,
            "low_confidence_threshold": cfg.low_confidence_threshold,
            "novelty_stop_threshold": cfg.novelty_stop_threshold,
            "initial_marginal_novelty": cfg.initial_marginal_novelty,
            "transition_budget": cfg.transition_budget,
            "quality_weights": {
                "expandability": cfg.quality_weight_expandability,
                "completeness": cfg.quality_weight_completeness,
                "heuristic": cfg.quality_weight_heuristic,
                "association": cfg.quality_weight_association,
            },
        },
    }


def _finding_claim_fingerprints(payload: Mapping[str, Any]) -> frozenset[str]:
    """Normalized claim-text fingerprints used for corroboration matching."""
    claims: set[str] = set()
    for observation in payload.get("observations", ()):
        if not isinstance(observation, Mapping):
            continue
        claim = str(observation.get("claim", "")).strip()
        if claim:
            claims.add(hashlib.sha256(" ".join(claim.lower().split()).encode("utf-8")).hexdigest())
    return frozenset(claims)


def _finding_cluster_labels(payload: Mapping[str, Any]) -> frozenset[str]:
    """Provenance cluster labels of a finding's anchors, via claims clustering."""
    descriptors = []
    for observation in payload.get("observations", ()):
        anchor = observation.get("anchor") if isinstance(observation, Mapping) else None
        if not isinstance(anchor, Mapping):
            continue
        ref = anchor.get("ref")
        if isinstance(ref, str) and ref.strip():
            descriptors.append(ProvenanceDescriptor(upstream_id=ref.strip()))
    if not descriptors:
        return frozenset()
    return frozenset(label for label, _identities in cluster_provenance_components(descriptors))


def _comparison_key(comparison: Mapping[str, Any]) -> str:
    """Stable identity for a batch comparison when no comparison_id is declared."""
    import json

    return (
        "digest:"
        + hashlib.sha256(json.dumps(dict(comparison), sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    )


def _reopen_completed_obligation(node: Mapping[str, Any] | None) -> None:
    """Re-open an obligation node that completed while its grounding held.

    When the evidence that grounded a mandatory closure obligation is later
    quarantined, the obligation must return to the frontier instead of
    silently vanishing behind an already-completed node identity.
    """

    if node is None or node["status"] != "completed":
        return
    node["status"] = "frontier"
    node["terminal_reason"] = None
