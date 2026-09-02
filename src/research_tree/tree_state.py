"""Immutable persistence and crash recovery for recursive research state."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .domain import ArtifactRef, ArtifactRevision, RuntimeStoreError, thaw_json, validate_identifier
from .ledger import FINDING_PACK_KIND
from .run_ledger import RunLedger

RESEARCH_TREE_STATE_KIND = "research-tree-state"
TREE_STATUSES = {"searching", "blocked", "delivery_pending", "complete"}

# Issue #492: explicit run-phase discriminator with gated transitions. A tree
# is born `compiled` — revision zero exists only after the confirmed handoff
# compiles — and every phase change must follow the gated graph below.
TREE_PHASES = frozenset({"intake", "alignment", "compiled", "research", "validation", "delivery"})
DEFAULT_TREE_PHASE = "compiled"
TREE_PHASE_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "intake": frozenset({"intake", "alignment"}),
    "alignment": frozenset({"alignment", "compiled"}),
    # `compiled -> alignment` reopens alignment after compile; `research ->
    # alignment` is the reopen edge of the two-option interruption protocol.
    "compiled": frozenset({"compiled", "research", "alignment"}),
    "research": frozenset({"research", "validation", "alignment"}),
    "validation": frozenset({"validation", "delivery"}),
    "delivery": frozenset({"delivery"}),
}
# Optional payload keys validated when present; legacy payloads without them
# stay valid (the direct alignment-handoff append path predates the phase).
_OPTIONAL_TREE_STATE_KEYS = frozenset({"phase", "strategy_authority_fingerprint", "realignment"})
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")
_REALIGNMENT_RECORD_KEYS = frozenset({"schema", "confirmation_digest", "authority_fingerprint", "reason"})


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
        if payload["phase"] != DEFAULT_TREE_PHASE:
            raise ResearchTreeStateError("tree state birth phase must be 'compiled'")
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
        previous_phase = tree_phase_of(stored.payload)
        validate_phase_transition(previous_phase, payload["phase"])
        _validate_strategy_material_change(stored.payload, payload, previous_phase)
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
    if (
        not isinstance(value, Mapping)
        or not required <= set(value)
        or set(value) - (required | _OPTIONAL_TREE_STATE_KEYS)
    ):
        actual = set(value) if isinstance(value, Mapping) else set()
        raise ResearchTreeStateError(
            f"tree state has unexpected keys; missing={sorted(required - actual)}, extra={sorted(actual - required)}"
        )
    if value.get("schema") != 2:
        raise ResearchTreeStateError("tree state schema must be 2")
    validate_identifier(value.get("id"), "tree state id")
    validate_identifier(value.get("round_id"), "tree state round_id")
    transition = value.get("transition_index")
    if isinstance(transition, bool) or not isinstance(transition, int) or transition < 0:
        raise ResearchTreeStateError("transition_index must be a nonnegative integer")
    if value.get("status") not in TREE_STATUSES:
        raise ResearchTreeStateError("tree state status is unsupported")
    if "phase" in value and value["phase"] not in TREE_PHASES:
        raise ResearchTreeStateError("tree state phase is unsupported")
    _validate_strategy_fingerprint(value.get("strategy_authority_fingerprint"))
    if "realignment" in value:
        _validate_realignment_record(value["realignment"], value.get("strategy_authority_fingerprint"))
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


def tree_phase_of(payload: Mapping[str, Any]) -> str:
    """Return the payload's run phase, defaulting to the birth phase.

    Legacy payloads written before the phase field existed are reported as
    ``compiled``: every research tree is born from a compiled handoff.
    """

    phase = payload.get("phase", DEFAULT_TREE_PHASE) if isinstance(payload, Mapping) else None
    if phase not in TREE_PHASES:
        raise ResearchTreeStateError("tree state phase is unsupported")
    return phase  # type: ignore[no-any-return]


def validate_phase_transition(previous_phase: str, next_phase: str) -> None:
    """Reject any phase change outside the gated transition graph (#492)."""

    allowed = TREE_PHASE_TRANSITIONS.get(previous_phase, frozenset())
    if next_phase not in allowed:
        raise ResearchTreeStateError(
            f"illegal tree phase transition: {previous_phase} -> {next_phase}; allowed={sorted(allowed)}"
        )


def _validate_strategy_fingerprint(fingerprint: Any) -> None:
    if fingerprint is None:
        return
    if not isinstance(fingerprint, str) or not _FINGERPRINT_RE.fullmatch(fingerprint):
        raise ResearchTreeStateError(
            "tree state strategy_authority_fingerprint must be a 64-character lowercase hex digest"
        )


def _validate_realignment_record(record: Any, fingerprint: Any) -> None:
    if not isinstance(record, Mapping) or set(record) != _REALIGNMENT_RECORD_KEYS:
        raise ResearchTreeStateError(
            "tree state realignment record must carry exactly schema, confirmation_digest, "
            "authority_fingerprint, reason"
        )
    schema = record.get("schema")
    if isinstance(schema, bool) or not isinstance(schema, int) or schema != 1:
        raise ResearchTreeStateError("tree state realignment record schema must be 1")
    for key in ("confirmation_digest", "authority_fingerprint"):
        digest = record.get(key)
        if not isinstance(digest, str) or not _FINGERPRINT_RE.fullmatch(digest):
            raise ResearchTreeStateError(
                f"tree state realignment record {key} must be a 64-character lowercase hex digest"
            )
    reason = record.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 256:
        raise ResearchTreeStateError("tree state realignment record reason must be a non-empty bounded string")
    if fingerprint is not None and record["authority_fingerprint"] != fingerprint:
        raise ResearchTreeStateError(
            "tree state realignment record must bind the payload's strategy_authority_fingerprint"
        )


def _validate_strategy_material_change(
    previous_payload: Mapping[str, Any],
    payload: Mapping[str, Any],
    previous_phase: str,
) -> None:
    """Reject post-compile strategy-material changes that bypass realignment (#492).

    A changed ``strategy_authority_fingerprint`` is a strategy-material change;
    it is only accepted on the recompile edge out of re-entered alignment and
    only with a realignment record binding the new fingerprint to a fresh user
    confirmation (mechanism from PR #450). Dropping the fingerprint outside
    that edge is rejected too.
    """

    previous_fingerprint = previous_payload.get("strategy_authority_fingerprint")
    next_fingerprint = payload.get("strategy_authority_fingerprint")
    if previous_fingerprint is None or next_fingerprint == previous_fingerprint:
        return
    if (previous_phase, payload["phase"]) != ("alignment", "compiled"):
        raise ResearchTreeStateError(
            "strategy fingerprint changed without user realignment: "
            "re-enter alignment and recompile with a realignment record"
        )
    record = payload.get("realignment")
    if not isinstance(record, Mapping) or record.get("authority_fingerprint") != next_fingerprint:
        raise ResearchTreeStateError(
            "strategy fingerprint change requires a user realignment record binding the new fingerprint"
        )


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
    # A tree is born compiled; writers that predate the phase field get the
    # birth phase injected so the transition gate always has a discriminator.
    payload.setdefault("phase", DEFAULT_TREE_PHASE)
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
