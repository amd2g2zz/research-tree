"""Immutable persistence and crash recovery for recursive research state."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    RuntimeStoreError,
    canonical_json_bytes,
    thaw_json,
    validate_identifier,
)
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
_OPTIONAL_TREE_STATE_KEYS = frozenset(
    {"phase", "strategy_authority_fingerprint", "realignment", "deliverable_quality_gate", "discarded_evidence"}
)
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")
_REALIGNMENT_RECORD_KEYS = frozenset({"schema", "confirmation_digest", "authority_fingerprint", "reason"})
_QUALITY_GATE_RECORD_KEYS = frozenset({"status", "review_id", "manifest_digests", "remediation_node_ids"})
_QUALITY_GATE_STATUSES = frozenset({"passed", "failed"})
_DISCARDED_EVIDENCE_KEYS = frozenset(
    {
        "node_id",
        "terminal_reason",
        "decision_oracle",
        "evidence_needed",
        "decision_slot_id",
        "depth",
        "selection_value",
    }
)


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

    def advance_phase(
        self,
        *,
        round_id: str,
        tree_id: str,
        phase: str,
        reason: str,
        expected_revision: int | None = None,
    ) -> ArtifactRevision | None:
        """Advance the tree's run phase through the gated graph (issue #530).

        The owned writer primitive for phase transitions: loads the latest
        tree, no-ops (returns None) when the phase is unchanged, and otherwise
        appends one tree transition whose payload carries the new ``phase`` —
        so every production phase change passes through the #502/#492
        transition gate and the state history records who moved the clock.
        The run-level phase store is recorded to match (one event statement).
        """

        previous = self.latest(round_id=round_id, tree_id=tree_id)
        previous_phase = tree_phase_of(previous.payload)
        if previous_phase == phase:
            return None
        validate_phase_transition(previous_phase, phase)
        state = thaw_json(previous.payload)
        state["transition_index"] = int(previous.payload["transition_index"]) + 1
        state["phase"] = phase
        advanced = self.transition(
            round_id=round_id,
            previous=previous,
            state=state,
            consumed_findings=(),
            expected_revision=(self._ledger.get_revision(round_id) if expected_revision is None else expected_revision),
        )
        store = RunPhaseStore(run_phase_dir(self._ledger.workspace, round_id))
        try:
            store.record_transition(
                phase=phase,
                reason=reason,
                tree_transition_index=int(advanced.payload["transition_index"]),
            )
        except (OSError, ResearchTreeStateError):
            # The tree transition is the authority and is already persisted;
            # a store write failure must not roll the validated gate back.
            pass
        return advanced


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
    if "deliverable_quality_gate" in value:
        _validate_quality_gate_record(value["deliverable_quality_gate"])
    if "discarded_evidence" in value:
        _validate_discarded_evidence(value["discarded_evidence"])
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


# Issue #530: the authoritative run-level phase store. Engine-written JSON
# with a digest over the canonical serialization (the turn-records state
# convention) plus an append-only event statement per transition — the store
# the hook reads FIRST, so production phase resolution never guesses.
RUN_PHASE_STORE_SCHEMA = 1
RUN_PHASE_TRANSITION_EVENT = "phase_transition"
RUN_PHASE_STATE_FILENAME = "state.json"
RUN_PHASE_EVENTS_FILENAME = "events.jsonl"
RUN_PHASE_ANNOUNCE_FILENAME = "announce.json"
MAX_PHASE_REASON_LENGTH = 256


def run_phase_dir(workspace: Path, run_id: str) -> Path:
    """Resolve the run-scoped phase directory for one run.

    Follows the alignment-graph run-directory convention (``alignment_graph
    ._run_dir``): the phase record lives under the run's directory with the
    fallback project id, so writers that carry no project id and readers
    (hook, alignment controller) resolve the same path from workspace and
    run id alone.
    """

    validate_identifier(run_id, "run_id")
    root = Path(workspace).resolve()
    return root / ".research-tree" / "projects" / f"alignment-{run_id}" / "runs" / run_id / "phase"


def _phase_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _phase_state_digest(payload: Mapping[str, Any]) -> str:
    material = {key: value for key, value in payload.items() if key != "digest"}
    return hashlib.sha256(canonical_json_bytes(material)).hexdigest()


def render_phase_event(event: Mapping[str, Any]) -> str:
    """Render one phase-transition event statement (single line, fixed shape)."""

    previous = event.get("from") if isinstance(event.get("from"), str) else None
    phase = event.get("to") if isinstance(event.get("to"), str) else None
    reason = event.get("reason") if isinstance(event.get("reason"), str) else "unspecified"
    return f"run-phase: {previous or 'start'} -> {phase or 'unknown'} ({reason})"


class RunPhaseStore:
    """Engine-written run phase record: state JSON with digest + event log."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.state_path = self.directory / RUN_PHASE_STATE_FILENAME
        self.events_path = self.directory / RUN_PHASE_EVENTS_FILENAME
        self.announce_path = self.directory / RUN_PHASE_ANNOUNCE_FILENAME

    # -- reads ---------------------------------------------------------------

    def current(self) -> dict[str, Any] | None:
        """Return the digest-verified phase state, or None when absent/broken.

        Fail-open by design: the hook treats None as "no authority" and falls
        back to its legacy guesses; a tampered store can never inject a phase.
        """

        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("schema") != RUN_PHASE_STORE_SCHEMA:
            return None
        if payload.get("phase") not in TREE_PHASES:
            return None
        digest = payload.get("digest")
        if not isinstance(digest, str) or digest != _phase_state_digest(payload):
            return None
        return payload

    def events(self) -> tuple[dict[str, Any], ...]:
        """Parse the append-only event statements (malformed lines skipped)."""

        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ()
        events: list[dict[str, Any]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("event") == RUN_PHASE_TRANSITION_EVENT:
                events.append(event)
        return tuple(events)

    def announced_count(self) -> int:
        try:
            payload = json.loads(self.announce_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        count = payload.get("announced") if isinstance(payload, dict) else None
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return 0
        return count

    # -- writes ---------------------------------------------------------------

    def record_transition(
        self,
        *,
        phase: str,
        reason: str,
        tree_transition_index: int | None = None,
        recorded_at: str | None = None,
    ) -> dict[str, Any] | None:
        """Record one phase transition: state JSON + exactly one event line.

        A same-phase call is a no-op (returns None): writers fire at owning
        transitions, and re-firing must never emit a duplicate statement.
        """

        if phase not in TREE_PHASES:
            raise ResearchTreeStateError(f"run phase must be one of {sorted(TREE_PHASES)}: {phase!r}")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_PHASE_REASON_LENGTH:
            raise ResearchTreeStateError(
                f"run phase reason must be a non-empty string of at most {MAX_PHASE_REASON_LENGTH} characters"
            )
        if tree_transition_index is not None and (
            isinstance(tree_transition_index, bool)
            or not isinstance(tree_transition_index, int)
            or tree_transition_index < 0
        ):
            raise ResearchTreeStateError("tree_transition_index must be a nonnegative integer or None")
        current = self.current()
        if current is not None and current["phase"] == phase:
            return None
        previous_phase = current.get("phase") if current is not None else None
        timestamp = recorded_at or _phase_now()
        event = {
            "schema": RUN_PHASE_STORE_SCHEMA,
            "event": RUN_PHASE_TRANSITION_EVENT,
            "from": previous_phase,
            "to": phase,
            "reason": reason,
            "tree_transition_index": tree_transition_index,
            "recorded_at": timestamp,
        }
        state = {
            "schema": RUN_PHASE_STORE_SCHEMA,
            "phase": phase,
            "previous_phase": previous_phase,
            "reason": reason,
            "tree_transition_index": tree_transition_index,
            "recorded_at": timestamp,
        }
        state["digest"] = _phase_state_digest(state)
        self.directory.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
        descriptor = os.open(self.events_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(line)
        self._atomic_write_state(state)
        return state

    def mark_announced(self, count: int) -> None:
        """Persist the announce cursor so each statement is injected exactly once."""

        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ResearchTreeStateError("announce count must be a nonnegative integer")
        payload = {
            "schema": RUN_PHASE_STORE_SCHEMA,
            "announced": count,
            "updated_at": _phase_now(),
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.announce_path, payload)

    # -- internals ---------------------------------------------------------------

    def _atomic_write_state(self, payload: Mapping[str, Any]) -> None:
        self._atomic_write(self.state_path, payload)

    def _atomic_write(self, path: Path, payload: Mapping[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


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


def _validate_quality_gate_record(record: Any) -> None:
    """Shape validation for the deliverable-quality gate record (issue #495)."""

    if not isinstance(record, Mapping) or set(record) != _QUALITY_GATE_RECORD_KEYS:
        raise ResearchTreeStateError(
            "tree state deliverable_quality_gate must carry exactly status, review_id, "
            "manifest_digests, remediation_node_ids"
        )
    if record.get("status") not in _QUALITY_GATE_STATUSES:
        raise ResearchTreeStateError("tree state deliverable_quality_gate status is unsupported")
    if not isinstance(record.get("review_id"), str) or not record["review_id"].strip():
        raise ResearchTreeStateError("tree state deliverable_quality_gate review_id must be a non-empty string")
    digests = record.get("manifest_digests")
    if not isinstance(digests, Mapping) or not digests:
        raise ResearchTreeStateError("tree state deliverable_quality_gate manifest_digests must be a non-empty mapping")
    for kind, digest in digests.items():
        if not isinstance(kind, str) or not kind.strip():
            raise ResearchTreeStateError("tree state deliverable_quality_gate manifest kinds must be non-empty strings")
        if not isinstance(digest, str) or not _FINGERPRINT_RE.fullmatch(digest):
            raise ResearchTreeStateError(
                f"tree state deliverable_quality_gate manifest_digests[{kind}] must be a 64-character hex digest"
            )
    remediation = record.get("remediation_node_ids")
    if isinstance(remediation, (str, bytes)) or not isinstance(remediation, Sequence):
        raise ResearchTreeStateError("tree state deliverable_quality_gate remediation_node_ids must be a sequence")
    for node_id in remediation:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ResearchTreeStateError(
                "tree state deliverable_quality_gate remediation_node_ids entries must be non-empty strings"
            )
    if record["status"] == "passed" and remediation:
        raise ResearchTreeStateError("a passed deliverable_quality_gate cannot carry remediation_node_ids")


def _validate_discarded_evidence(registry: Any) -> None:
    """Shape validation for the discarded-evidence registry (issue #495)."""

    if isinstance(registry, (str, bytes)) or not isinstance(registry, Sequence):
        raise ResearchTreeStateError("tree state discarded_evidence must be a sequence")
    seen: set[str] = set()
    for entry in registry:
        if not isinstance(entry, Mapping) or set(entry) != _DISCARDED_EVIDENCE_KEYS:
            raise ResearchTreeStateError(
                "tree state discarded_evidence entry must carry exactly node_id, terminal_reason, "
                "decision_oracle, evidence_needed, decision_slot_id, depth, selection_value"
            )
        node_id = entry.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise ResearchTreeStateError("tree state discarded_evidence node_id must be a non-empty string")
        if node_id in seen:
            raise ResearchTreeStateError(f"tree state discarded_evidence duplicates node: {node_id}")
        seen.add(node_id)
        for key in ("terminal_reason", "decision_oracle", "evidence_needed", "decision_slot_id"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ResearchTreeStateError(f"tree state discarded_evidence {key} must be a non-empty string")
        depth = entry.get("depth")
        if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
            raise ResearchTreeStateError("tree state discarded_evidence depth must be a nonnegative integer")
        selection = entry.get("selection_value")
        if isinstance(selection, bool) or not isinstance(selection, (int, float)):
            raise ResearchTreeStateError("tree state discarded_evidence selection_value must be numeric")


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
