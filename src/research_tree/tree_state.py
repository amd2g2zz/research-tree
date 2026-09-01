"""Immutable persistence and crash recovery for recursive research state."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .domain import ArtifactRef, ArtifactRevision, RuntimeStoreError, thaw_json, validate_identifier
from .ledger import FINDING_PACK_KIND
from .run_ledger import RunLedger

RESEARCH_TREE_STATE_KIND = "research-tree-state"
TREE_STATUSES = {"searching", "blocked", "delivery_pending", "complete"}


class ResearchTreeStateError(RuntimeStoreError):
    """Raised when a tree transition is stale, malformed, or unrecoverable."""


class CanonicalResearchTreeStateService:
    """Append research-tree state revisions directly to one RunLedger."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise ResearchTreeStateError("canonical tree state requires a RunLedger")
        self._ledger = ledger

    def initialize(
        self,
        *,
        round_id: str,
        tree_id: str,
        state: Mapping[str, Any],
        expected_revision: int,
        parent_artifacts: Sequence[ArtifactRevision] = (),
        baseline_findings: Sequence[ArtifactRevision] = (),
    ) -> ArtifactRevision:
        validate_identifier(tree_id, "tree_id")
        snapshot = self._ledger.load_run(round_id)
        if _latest(snapshot.artifacts, tree_id) is not None:
            raise ResearchTreeStateError(f"research tree already exists: {tree_id}")
        payload = _normalized_state(state, tree_id, round_id, expected_transition=0)
        findings = _resolve_findings(snapshot.artifacts, round_id, baseline_findings)
        expected_ids = {finding.id for finding in findings}
        consumed = set(payload["consumed_finding_ids"])
        if consumed != expected_ids:
            raise ResearchTreeStateError("initial consumed_finding_ids must exactly match baseline findings")
        parents = _resolve_artifacts(snapshot.artifacts, round_id, parent_artifacts)
        return self._ledger.append_artifact(
            round_id,
            tree_id,
            RESEARCH_TREE_STATE_KIND,
            payload,
            parent_refs=_unique_refs((*parents, *findings)),
            expected_revision=expected_revision,
        )

    def transition(
        self,
        *,
        round_id: str,
        previous: ArtifactRevision,
        state: Mapping[str, Any],
        consumed_findings: Sequence[ArtifactRevision],
        expected_revision: int,
    ) -> ArtifactRevision:
        snapshot = self._ledger.load_run(round_id)
        stored = _resolve_tree(snapshot.artifacts, round_id, previous)
        latest = _latest(snapshot.artifacts, stored.id)
        if latest != stored:
            raise ResearchTreeStateError("previous tree state is stale")
        payload = _normalized_state(
            state,
            stored.id,
            round_id,
            expected_transition=int(stored.payload["transition_index"]) + 1,
        )
        findings = _resolve_findings(snapshot.artifacts, round_id, consumed_findings)
        previous_ids = set(stored.payload["consumed_finding_ids"])
        next_ids = set(payload["consumed_finding_ids"])
        finding_ids = {finding.id for finding in findings}
        if next_ids != previous_ids | finding_ids:
            raise ResearchTreeStateError("transition consumed_finding_ids must add exactly the supplied Finding Packs")
        return self._ledger.append_artifact(
            round_id,
            stored.id,
            RESEARCH_TREE_STATE_KIND,
            payload,
            parent_refs=_unique_refs((stored, *findings)),
            expected_revision=expected_revision,
        )

    def latest(self, *, round_id: str, tree_id: str) -> ArtifactRevision:
        validate_identifier(tree_id, "tree_id")
        snapshot = self._ledger.load_run(round_id)
        state = _latest(snapshot.artifacts, tree_id)
        if state is None:
            raise ResearchTreeStateError(f"research tree does not exist: {tree_id}")
        validate_tree_state_payload(state.payload)
        return state

    def recover_unconsumed(
        self,
        *,
        round_id: str,
        tree_id: str,
    ) -> tuple[ArtifactRevision, tuple[ArtifactRevision, ...]]:
        """Return the latest checkpoint and persisted findings it has not consumed."""

        snapshot = self._ledger.load_run(round_id)
        state = self.latest(round_id=round_id, tree_id=tree_id)
        consumed = set(state.payload["consumed_finding_ids"])
        pending = tuple(
            artifact
            for artifact in snapshot.artifacts
            if artifact.kind == FINDING_PACK_KIND and artifact.id not in consumed
        )
        return state, pending


def validate_tree_state_payload(value: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "id",
        "round_id",
        "transition_index",
        "status",
        "config",
        "decision_slots",
        "execution_context",
        "deliverables",
        "nodes",
        "frontier_node_ids",
        "evidence_baseline",
        "consumed_finding_ids",
        "delta_history",
        "penalty_history",
        "cross_validation",
        "recursion_receipt",
        "stop_reason",
    }
    if not isinstance(value, Mapping) or not required <= set(value) or set(value) - required:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise ResearchTreeStateError(
            f"tree state has unexpected keys; missing={sorted(required - actual)}, extra={sorted(actual - required)}"
        )
    if value.get("schema") != 1:
        raise ResearchTreeStateError("tree state schema must be 1")
    validate_identifier(value.get("id"), "tree state id")
    validate_identifier(value.get("round_id"), "tree state round_id")
    transition = value.get("transition_index")
    if isinstance(transition, bool) or not isinstance(transition, int) or transition < 0:
        raise ResearchTreeStateError("transition_index must be a nonnegative integer")
    if value.get("status") not in TREE_STATUSES:
        raise ResearchTreeStateError("tree state status is unsupported")
    for key in (
        "config",
        "decision_slots",
        "execution_context",
        "deliverables",
        "nodes",
        "evidence_baseline",
        "cross_validation",
        "recursion_receipt",
    ):
        if not isinstance(value.get(key), Mapping):
            raise ResearchTreeStateError(f"tree state {key} must be a mapping")
    for key in ("frontier_node_ids", "consumed_finding_ids", "delta_history", "penalty_history"):
        if isinstance(value.get(key), (str, bytes)) or not isinstance(value.get(key), Sequence):
            raise ResearchTreeStateError(f"tree state {key} must be a sequence")
    node_ids = set(value["nodes"])
    if set(value["frontier_node_ids"]) - node_ids:
        raise ResearchTreeStateError("frontier references unknown nodes")


def _normalized_state(
    state: Mapping[str, Any],
    tree_id: str,
    round_id: str,
    *,
    expected_transition: int,
) -> dict[str, Any]:
    payload = thaw_json(state) if isinstance(state, Mapping) else state
    if not isinstance(payload, dict):
        raise ResearchTreeStateError("tree state must be a mapping")
    payload["id"] = tree_id
    payload["round_id"] = round_id
    validate_tree_state_payload(payload)
    if payload["transition_index"] != expected_transition:
        raise ResearchTreeStateError(
            f"transition_index must be {expected_transition}; got {payload['transition_index']}"
        )
    return payload


def _latest(artifacts: Sequence[ArtifactRevision], tree_id: str) -> ArtifactRevision | None:
    matches = [
        artifact for artifact in artifacts if artifact.id == tree_id and artifact.kind == RESEARCH_TREE_STATE_KIND
    ]
    return max(matches, key=lambda artifact: artifact.revision, default=None)


def _resolve_tree(artifacts: Sequence[ArtifactRevision], round_id: str, value: ArtifactRevision) -> ArtifactRevision:
    matches = [artifact for artifact in artifacts if artifact.id == value.id and artifact.revision == value.revision]
    if not matches or matches[0] != value:
        raise ResearchTreeStateError("tree state revision is not persisted")
    stored = matches[0]
    if stored.round_id != round_id or stored.kind != RESEARCH_TREE_STATE_KIND:
        raise ResearchTreeStateError("previous artifact is not a tree state for this round")
    return stored


def _resolve_findings(
    artifacts: Sequence[ArtifactRevision],
    round_id: str,
    values: Sequence[ArtifactRevision],
) -> tuple[ArtifactRevision, ...]:
    resolved = _resolve_artifacts(artifacts, round_id, values)
    if any(artifact.kind != FINDING_PACK_KIND for artifact in resolved):
        raise ResearchTreeStateError("consumed findings must be Finding Pack artifacts")
    if len({artifact.id for artifact in resolved}) != len(resolved):
        raise ResearchTreeStateError("consumed findings must not repeat an artifact id")
    return resolved


def _resolve_artifacts(
    artifacts: Sequence[ArtifactRevision],
    round_id: str,
    values: Sequence[ArtifactRevision],
) -> tuple[ArtifactRevision, ...]:
    resolved: list[ArtifactRevision] = []
    for value in values:
        stored = next(
            (artifact for artifact in artifacts if artifact.id == value.id and artifact.revision == value.revision),
            None,
        )
        if stored is None or stored != value or stored.round_id != round_id:
            raise ResearchTreeStateError("tree parent artifact is not persisted in this round")
        resolved.append(stored)
    return tuple(resolved)


def _unique_refs(artifacts: Sequence[ArtifactRevision]) -> tuple[ArtifactRef, ...]:
    refs: list[ArtifactRef] = []
    seen: set[tuple[str, str, int]] = set()
    for artifact in artifacts:
        key = (artifact.round_id, artifact.id, artifact.revision)
        if key in seen:
            continue
        seen.add(key)
        refs.append(ArtifactRef(*key))
    return tuple(refs)
