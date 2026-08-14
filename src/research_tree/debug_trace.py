"""Write and summarize sanitized, opt-in research workflow traces."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
from typing import Any, Iterable, Mapping, Sequence

from .coordinator import (
    COMPLETION_RECORD_KIND,
    CORRECTION_EVENT_KIND,
    HOST_EVENT_KIND,
    HOST_EVENT_PROJECTION_KIND,
    LEASE_KIND,
    LIFECYCLE_EVENT_KIND,
    RESEARCH_RUN_STATE_KIND,
    STALE_STATE_QUARANTINE_KIND,
    _TRANSITIONS,
    ResearchRunCoordinator,
)
from .domain import ArtifactRef, ArtifactRevision, canonical_json_bytes, thaw_json, validate_identifier
from .feedback import CorrectionEvent
from .host_events import HostEvent, HostEventError, normalize_host_path
from .run_ledger import RunLedger
from .strategy_projection import macro_stage


TRACE_DIRECTORY = Path(".research-tree-debug") / "events"
HOSTS = frozenset({"codex", "claude", "hermes"})
PHASES = frozenset(
    {
        "lifecycle_observed",
        "intake",
        "reconnaissance",
        "alignment_turn",
        "alignment_checkpoint",
        "alignment_blocked",
        "research_started",
        "implementation_started",
        "worker_blocked",
        "completed",
        "aborted",
    }
)
STATUSES = frozenset({"started", "completed", "blocked", "skipped", "failed"})
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
CODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
CAUSAL_TRACE_SCHEMA_VERSION = 1
_SENSITIVE_KEY_PARTS = (
    "chain_of_thought",
    "credential",
    "password",
    "prompt",
    "raw_error",
    "response",
    "secret",
    "token",
    "tool_input",
)
_HOST_OBSERVATION_FIELDS = frozenset({"event_id", "attempt_id", "status", "sequence", "category", "code", "log_ref"})
_HOST_STATUSES = frozenset({"active", "running", "complete", "completed", "failed", "unknown"})
_SAFE_HOST_DIAGNOSTIC_FIELDS = frozenset(
    {"category", "code", "retry_count", "log_ref", "reason", "retry_of", "verdict", "outcome", "evidence_refs"}
)
_OBLIGATION_KINDS = {
    "p0_closure_tokens": frozenset({"slot-closure-assessment"}),
    "insights_non_blocking": frozenset({"insight-digest"}),
    "readiness_ref": frozenset({"readiness-record"}),
    "evaluation_ref": frozenset({"blueprint-evaluation"}),
    "technical_delivery_ref": frozenset({"technical-research-package"}),
    "human_delivery_ref": frozenset({"human-research-report"}),
    "acceptance_ref": frozenset({"delivery-acceptance"}),
}


def _digest_payload(value: Any) -> str:
    def normalize(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): normalize(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        return item

    return hashlib.sha256(canonical_json_bytes(normalize(value))).hexdigest()


class DebugTraceError(ValueError):
    """Raised when a debug trace would be ambiguous or unsafe to persist."""


class CausalTraceError(DebugTraceError):
    """Raised when canonical lineage cannot be safely explained or replayed."""


class CausalTraceService:
    """Project deterministic, sanitized explanations from the canonical ledger."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise CausalTraceError("causal tracing requires a RunLedger")
        self.ledger = ledger

    def replay(self, run_id: str) -> dict[str, Any]:
        validate_identifier(run_id, "run_id")
        snapshot = self.ledger.load_run(run_id)
        states = [item for item in snapshot.artifacts if item.kind == RESEARCH_RUN_STATE_KIND]
        if not states:
            return self._replay_from_immutable_inputs(run_id, snapshot)
        by_sequence: dict[int, list[ArtifactRevision]] = {}
        for state in states:
            sequence = state.payload.get("lifecycle_revision")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
                raise CausalTraceError("invalid lifecycle revision")
            by_sequence.setdefault(sequence, []).append(state)
        if any(len(items) != 1 for items in by_sequence.values()):
            raise CausalTraceError("forked lifecycle revision")
        ordered_sequences = sorted(by_sequence)
        if ordered_sequences != list(range(len(ordered_sequences))):
            raise CausalTraceError("missing lifecycle revision")
        ordered = [by_sequence[index][0] for index in ordered_sequences]
        artifacts = {self._artifact_ref(item): item for item in snapshot.artifacts}
        artifact_order = {
            event.artifact_ref: index
            for index, event in enumerate(snapshot.lineage_events)
            if event.artifact_ref is not None
        }
        transitions: list[dict[str, Any]] = []
        semantic_divergences: list[dict[str, Any]] = []
        for state in ordered:
            self._verify_state_digest(state)
        recomputed: list[dict[str, Any]] = []
        for sequence, state in enumerate(ordered):
            if sequence > 0:
                cause_refs = [
                    reference
                    for reference in state.parent_refs
                    if reference in artifacts
                    and artifacts[reference].kind
                    in {
                        LIFECYCLE_EVENT_KIND,
                        CORRECTION_EVENT_KIND,
                    }
                ]
                for reference in cause_refs:
                    revision_error = self._event_revision_error(artifacts[reference], artifact_order)
                    if revision_error is not None:
                        semantic_divergences.append(revision_error)
            if sequence == 0:
                expected = self._recompute_initial_state(run_id, state, artifacts)
            else:
                previous = ordered[sequence - 1]
                previous_ref = self._artifact_ref(previous)
                declared_previous = state.payload.get("previous_state_ref")
                if declared_previous != previous_ref.to_dict() or previous_ref not in state.parent_refs:
                    raise CausalTraceError("missing_cause: previous state lineage")
                causes = [
                    artifacts[reference]
                    for reference in state.parent_refs
                    if reference in artifacts and artifacts[reference].kind == LIFECYCLE_EVENT_KIND
                ]
                corrections = [
                    artifacts[reference]
                    for reference in state.parent_refs
                    if reference in artifacts and artifacts[reference].kind == CORRECTION_EVENT_KIND
                ]
                if len(causes) + len(corrections) != 1:
                    raise CausalTraceError("missing_cause: lifecycle event")
                cause = causes[0] if causes else corrections[0]
                if cause.kind == LIFECYCLE_EVENT_KIND:
                    expected, transition_error = self._recompute_lifecycle_state(
                        run_id, previous, state, cause, artifacts, artifact_order=artifact_order
                    )
                    if transition_error is None:
                        transitions.append(self._trace_record(run_id, sequence, previous, state, cause))
                    else:
                        semantic_divergences.append(transition_error)
                        transitions.append(
                            self._trace_record(
                                run_id,
                                sequence,
                                previous,
                                state,
                                cause,
                                divergence=transition_error,
                            )
                        )
                else:
                    expected, transition_error = self._recompute_correction_state(
                        run_id, previous, state, cause, artifacts
                    )
                    transitions.append(
                        self._trace_record(
                            run_id,
                            sequence,
                            previous,
                            state,
                            cause,
                            divergence=transition_error,
                        )
                    )
                    if transition_error is not None:
                        semantic_divergences.append(transition_error)
            recomputed.append(expected)
        state_divergences = [
            result
            for state, expected in zip(ordered, recomputed)
            if (result := self._state_divergence(state, expected)) is not None
        ]
        divergence = (semantic_divergences + state_divergences or [None])[0]
        host_divergences, host_digests = self._validate_host_events(run_id, snapshot, artifacts)
        if divergence is None and host_divergences:
            divergence = host_divergences[0]
        terminal = ordered[-1]
        terminal_expected = recomputed[-1]
        obligations = tuple(ResearchRunCoordinator(self.ledger)._completion_obligations(run_id))
        legal_actions = tuple(terminal_expected.get("legal_next_actions", ()))
        semantic_digest = self._semantic_digest(run_id, recomputed, host_digests, obligations, legal_actions)
        return {
            "schema_version": CAUSAL_TRACE_SCHEMA_VERSION,
            "run_id": run_id,
            "verified": divergence is None,
            "replay_mode": "semantic",
            "chain_intact": True,
            "terminal_state": terminal_expected["state"],
            "state_digest": terminal.payload["state_digest"],
            "stored_digest": terminal.payload["state_digest"],
            "recomputed_digest": terminal_expected["state_digest"],
            "semantic_digest": semantic_digest,
            "state_count": len(ordered),
            "transitions": transitions,
            "unresolved_references": host_divergences,
            "unresolved_obligations": list(obligations),
            "legal_next_actions": list(legal_actions),
            "earliest_divergence": divergence,
        }

    @staticmethod
    def _semantic_digest(
        run_id: str,
        states: Sequence[Mapping[str, Any]],
        host_digests: Sequence[str],
        obligations: Sequence[str],
        legal_actions: Sequence[str],
    ) -> str:
        def project(value: Any) -> Any:
            if isinstance(value, Mapping):
                return {
                    str(key): project(child)
                    for key, child in value.items()
                    if key not in {"state_digest", "previous_state_ref", "idempotency_key"}
                }
            if isinstance(value, (list, tuple)):
                return [project(child) for child in value]
            return value

        return _digest_payload(
            {
                "run_id": run_id,
                "states": [project(state) for state in states],
                "host_events": sorted(host_digests),
                "unresolved_obligations": sorted(obligations),
                "legal_next_actions": list(legal_actions),
            }
        )

    def _replay_from_immutable_inputs(self, run_id: str, snapshot: Any) -> dict[str, Any]:
        artifacts = {self._artifact_ref(item): item for item in snapshot.artifacts}
        lineage_order = {
            event.artifact_ref: index
            for index, event in enumerate(snapshot.lineage_events)
            if event.artifact_ref is not None
        }
        causes = sorted(
            (item for item in snapshot.artifacts if item.kind in {LIFECYCLE_EVENT_KIND, CORRECTION_EVENT_KIND}),
            key=lambda item: (
                lineage_order.get(self._artifact_ref(item), len(lineage_order)),
                item.created_at,
                item.id,
                item.revision,
            ),
        )
        if not causes:
            raise CausalTraceError("run is not initialized")
        handoff_candidates = sorted(
            (item for item in snapshot.artifacts if item.kind == "alignment-handoff"),
            key=lambda item: (
                lineage_order.get(self._artifact_ref(item), len(lineage_order)),
                item.created_at,
                item.id,
                item.revision,
            ),
        )
        target_candidates = sorted(
            (item for item in snapshot.artifacts if item.kind == "blueprint-target"),
            key=lambda item: (
                lineage_order.get(self._artifact_ref(item), len(lineage_order)),
                item.created_at,
                item.id,
                item.revision,
            ),
        )
        initial_inputs = next(
            (
                (handoff, target)
                for handoff in handoff_candidates
                for target in target_candidates
                if self._artifact_ref(handoff) in target.parent_refs
            ),
            None,
        )
        if initial_inputs is None:
            raise CausalTraceError("missing_cause: immutable initialization inputs")
        initial_payload = ResearchRunCoordinator(self.ledger)._state_payload(
            state="alignment",
            lifecycle_revision=0,
            obligations=(),
            legal_actions=("alignment_projection_ready", "authority_impossible", "supersede"),
        )
        initial_state = self._synthetic_state(
            run_id,
            revision=1,
            payload=initial_payload,
            parent_refs=(self._artifact_ref(initial_inputs[0]), self._artifact_ref(initial_inputs[1])),
        )
        initial_expected = self._recompute_initial_state(
            run_id,
            initial_state,
            {
                **artifacts,
                self._artifact_ref(initial_inputs[0]): initial_inputs[0],
                self._artifact_ref(initial_inputs[1]): initial_inputs[1],
            },
        )
        initial_state = self._synthetic_state(
            run_id,
            revision=1,
            payload=initial_expected,
            parent_refs=initial_state.parent_refs,
        )
        synthetic_states = [initial_state]
        recomputed = [initial_expected]
        completion_target = initial_inputs[1]
        completion_obligations = self._completion_obligations_from_artifacts(artifacts, completion_target, run_id)
        transitions: list[dict[str, Any]] = []
        semantic_divergences: list[dict[str, Any]] = []
        for sequence, cause in enumerate(causes, start=1):
            previous = synthetic_states[-1]
            event_ref = self._artifact_ref(cause)
            parent_refs: list[ArtifactRef] = [self._artifact_ref(previous), event_ref]
            revision_error = self._event_revision_error(cause, lineage_order)
            if revision_error is not None:
                semantic_divergences.append(revision_error)
            if cause.kind == LIFECYCLE_EVENT_KIND and thaw_json(cause.payload).get("event") == "delivery_accepted":
                completion = next(
                    (
                        item
                        for item in snapshot.artifacts
                        if item.kind == COMPLETION_RECORD_KIND and event_ref in item.parent_refs
                    ),
                    None,
                )
                if completion is not None:
                    parent_refs.append(self._artifact_ref(completion))
            if cause.kind == CORRECTION_EVENT_KIND:
                correction_id = thaw_json(cause.payload).get("event_id")
                quarantine = next(
                    (
                        item
                        for item in snapshot.artifacts
                        if item.kind == STALE_STATE_QUARANTINE_KIND
                        and item.payload.get("correction_event_id") == correction_id
                    ),
                    None,
                )
                if quarantine is not None:
                    parent_refs.append(self._artifact_ref(quarantine))
            projected = self._synthetic_state(
                run_id,
                revision=sequence + 1,
                payload={
                    "quarantine_ref": parent_refs[-1].to_dict()
                    if cause.kind == CORRECTION_EVENT_KIND and len(parent_refs) > 2
                    else {}
                },
                parent_refs=tuple(parent_refs),
            )
            if cause.kind == LIFECYCLE_EVENT_KIND:
                expected, transition_error = self._recompute_lifecycle_state(
                    run_id,
                    previous,
                    projected,
                    cause,
                    artifacts,
                    artifact_order=lineage_order,
                    completion_obligations=completion_obligations,
                )
            else:
                expected, transition_error = self._recompute_correction_state(
                    run_id, previous, projected, cause, artifacts
                )
            if transition_error is not None:
                semantic_divergences.append(transition_error)
            projected = self._synthetic_state(
                run_id,
                revision=sequence + 1,
                payload=expected,
                parent_refs=tuple(parent_refs),
            )
            transitions.append(
                self._trace_record(
                    run_id,
                    sequence,
                    previous,
                    projected,
                    cause,
                    divergence=transition_error,
                )
            )
            synthetic_states.append(projected)
            recomputed.append(expected)
            artifacts[self._artifact_ref(projected)] = projected
        host_divergences, host_digests = self._validate_host_events(run_id, snapshot, artifacts)
        divergence = (semantic_divergences + host_divergences or [None])[0]
        terminal = recomputed[-1]
        obligations = tuple(self._completion_obligations_from_artifacts(artifacts, completion_target, run_id))
        legal_actions = tuple(terminal.get("legal_next_actions", ()))
        semantic_digest = self._semantic_digest(run_id, recomputed, host_digests, obligations, legal_actions)
        return {
            "schema_version": CAUSAL_TRACE_SCHEMA_VERSION,
            "run_id": run_id,
            "verified": divergence is None,
            "replay_mode": "semantic",
            "chain_intact": True,
            "projection_rebuilt": True,
            "terminal_state": terminal["state"],
            "state_digest": terminal["state_digest"],
            "stored_digest": None,
            "recomputed_digest": terminal["state_digest"],
            "semantic_digest": semantic_digest,
            "state_count": len(recomputed),
            "transitions": transitions,
            "unresolved_references": host_divergences,
            "unresolved_obligations": list(obligations),
            "legal_next_actions": list(legal_actions),
            "earliest_divergence": divergence,
        }

    @staticmethod
    def _artifact_ref(item: ArtifactRevision) -> ArtifactRef:
        return ArtifactRef(item.round_id, item.id, item.revision)

    @staticmethod
    def _synthetic_state(
        run_id: str,
        *,
        revision: int,
        payload: Mapping[str, Any],
        parent_refs: Sequence[ArtifactRef],
    ) -> ArtifactRevision:
        candidate = ArtifactRevision.create(
            artifact_id="run-state",
            round_id=run_id,
            revision=revision,
            kind=RESEARCH_RUN_STATE_KIND,
            payload=payload,
            parent_refs=tuple(parent_refs),
        )
        body = candidate.content_dict()
        body["created_at"] = "1970-01-01T00:00:00+00:00"
        body["content_hash"] = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        return ArtifactRevision.from_dict(body | {"content_hash": body["content_hash"]})

    def _recompute_initial_state(
        self,
        run_id: str,
        state: ArtifactRevision,
        artifacts: Mapping[ArtifactRef, ArtifactRevision],
    ) -> dict[str, Any]:
        coordinator = ResearchRunCoordinator(self.ledger)
        handoffs = [
            artifacts[reference]
            for reference in state.parent_refs
            if reference in artifacts and artifacts[reference].kind == "alignment-handoff"
        ]
        targets = [
            artifacts[reference]
            for reference in state.parent_refs
            if reference in artifacts and artifacts[reference].kind == "blueprint-target"
        ]
        if len(handoffs) != 1 or len(targets) != 1:
            raise CausalTraceError("missing_cause: immutable initialization inputs")
        expected = coordinator._state_payload(
            state="alignment",
            lifecycle_revision=0,
            obligations=(),
            legal_actions=coordinator._next_actions("alignment"),
            idempotency_key=state.payload.get("idempotency_key"),
        )
        expected["macro_stage"] = 1
        authority = coordinator._lineage_authority(targets[0], handoffs[0])
        if authority is not None:
            bindings, task_id, domain_id = authority
            expected.update(
                authority_streams={role: binding.artifact_ref.artifact_id for role, binding in bindings.items()},
                task_id=task_id,
                domain_id=domain_id,
            )
        expected["state_digest"] = _digest_payload(
            {key: value for key, value in expected.items() if key != "state_digest"}
        )
        return expected

    @staticmethod
    def _event_revision_error(
        event: ArtifactRevision,
        artifact_order: Mapping[ArtifactRef, int],
    ) -> dict[str, Any] | None:
        body = thaw_json(event.payload)
        declared = body.get("expected_revision")
        payload = body.get("payload")
        if declared is None and isinstance(payload, Mapping):
            declared = payload.get("expected_revision")
        if declared is None:
            return None
        expected = artifact_order.get(ArtifactRef(event.round_id, event.id, event.revision))
        if isinstance(declared, bool) or not isinstance(declared, int) or declared != expected:
            return {
                "reason": "stale_expected_revision",
                "event_id": event.id,
                "declared": declared,
                "recomputed": expected,
            }
        return None

    @staticmethod
    def _artifacts_before_event(
        artifacts: Mapping[ArtifactRef, ArtifactRevision],
        event: ArtifactRevision,
        artifact_order: Mapping[ArtifactRef, int] | None,
    ) -> Mapping[ArtifactRef, ArtifactRevision]:
        if artifact_order is None:
            return artifacts
        event_index = artifact_order.get(ArtifactRef(event.round_id, event.id, event.revision), len(artifact_order))
        return {
            reference: item for reference, item in artifacts.items() if artifact_order.get(reference, -1) < event_index
        }

    def _validate_lifecycle_guard(
        self,
        run_id: str,
        transition: str,
        inputs: Mapping[str, Any],
        previous: ArtifactRevision,
        event: ArtifactRevision,
        artifacts: Mapping[ArtifactRef, ArtifactRevision],
        artifact_order: Mapping[ArtifactRef, int] | None,
    ) -> dict[str, Any] | None:
        available = self._artifacts_before_event(artifacts, event, artifact_order)
        if transition in {"alignment_projection_ready", "handoff_confirmed"}:
            try:
                projection_ref = ArtifactRef.from_dict(inputs.get("projection_ref"))
            except (TypeError, ValueError):
                return {"reason": "projection_reference_invalid", "event_id": event.id}
            projection = available.get(projection_ref)
            if projection is None or projection.kind != "strategy-projection":
                return {"reason": "projection_reference_missing", "event_id": event.id}
            display_digest = inputs.get("display_digest")
            if projection.payload.get("display_digest") != display_digest:
                return {"reason": "projection_digest_mismatch", "event_id": event.id}
            if transition == "handoff_confirmed":
                if projection.payload.get("status") not in {"displayed", "confirmed"}:
                    return {"reason": "projection_not_displayed", "event_id": event.id}
                confirmation = inputs.get("confirmation")
                if not isinstance(confirmation, str) or display_digest not in confirmation:
                    return {"reason": "confirmation_digest_mismatch", "event_id": event.id}
                if previous.payload.get("correction_event_id") is not None:
                    authority = inputs.get("authority_binding")
                    if not isinstance(authority, Mapping) or authority.get(
                        "correction_event_id"
                    ) != previous.payload.get("correction_event_id"):
                        return {"reason": "correction_authority_mismatch", "event_id": event.id}
                elif not any(
                    item.payload.get("confirmed") is True
                    for item in available.values()
                    if item.kind == "alignment-handoff"
                ):
                    return {"reason": "handoff_confirmation_missing", "event_id": event.id}
            return None
        if transition in {"all_slots_closed", "readiness_passed", "deliveries_compiled"}:
            latest = {}
            for item in available.values():
                latest[item.kind] = max(
                    (candidate for candidate in available.values() if candidate.kind == item.kind),
                    key=lambda candidate: (
                        artifact_order.get(self._artifact_ref(candidate), -1) if artifact_order else -1,
                        candidate.revision,
                        candidate.id,
                    ),
                )
            if transition == "all_slots_closed":
                target = latest.get("blueprint-target")
                p0_slots = {
                    str(slot.get("id"))
                    for slot in (target.payload.get("decision_slots", ()) if target is not None else ())
                    if isinstance(slot, Mapping) and slot.get("priority") == "P0" and slot.get("id")
                }
                closed_slots = {
                    str(item.payload.get("slot_id"))
                    for item in available.values()
                    if item.kind == "slot-closure-assessment"
                    and item.payload.get("status") == "passed"
                    and item.payload.get("closure_token")
                    and (target is None or self._artifact_ref(target) in item.parent_refs)
                }
                if not p0_slots or not p0_slots <= closed_slots:
                    return {"reason": "closure_obligations_unresolved", "event_id": event.id}
            elif transition == "readiness_passed":
                readiness = latest.get("readiness-record")
                evaluation = latest.get("blueprint-evaluation")
                if readiness is None or readiness.payload.get("status") not in {"ready", "passed"}:
                    return {"reason": "readiness_missing", "event_id": event.id}
                if evaluation is None or evaluation.payload.get("status") not in {"passed", "pass"}:
                    return {"reason": "evaluation_missing", "event_id": event.id}
            elif transition == "deliveries_compiled":
                if latest.get("technical-research-package") is None or latest.get("human-research-report") is None:
                    return {"reason": "delivery_inputs_missing", "event_id": event.id}
            return None
        return None

    def _completion_obligations_from_artifacts(
        self,
        artifacts: Mapping[ArtifactRef, ArtifactRevision],
        target: ArtifactRevision,
        run_id: str,
    ) -> tuple[str, ...]:
        coordinator = ResearchRunCoordinator(self.ledger)
        quarantined = coordinator._quarantined_refs(run_id)
        target_ref = self._artifact_ref(target)
        p0_slots = {
            str(slot.get("id"))
            for slot in target.payload.get("decision_slots", ())
            if isinstance(slot, Mapping) and slot.get("priority") == "P0" and slot.get("id")
        }
        assessments = [
            item
            for item in artifacts.values()
            if item.kind == "slot-closure-assessment"
            and self._artifact_ref(item) not in quarantined
            and self.ledger.is_latest_artifact(self._artifact_ref(item))
            and item.payload.get("status") == "passed"
            and item.payload.get("closure_token")
            and target_ref in item.parent_refs
        ]
        missing: list[str] = []
        if not p0_slots or not p0_slots <= {str(item.payload.get("slot_id")) for item in assessments}:
            missing.append("p0_closure_tokens")
        inputs = coordinator._completion_inputs(run_id)
        insight = inputs.get("insight_ref")
        if insight is None or insight.payload.get("status") != "non_blocking":
            missing.append("insights_non_blocking")
        readiness = inputs.get("readiness_ref")
        if readiness is None or readiness.payload.get("status") not in {"ready", "passed"}:
            missing.append("readiness_ref")
        evaluation = inputs.get("evaluation_ref")
        if evaluation is None or evaluation.payload.get("status") not in {"passed", "pass"}:
            missing.append("evaluation_ref")
        technical = inputs.get("technical_delivery_ref")
        if technical is None:
            missing.append("technical_delivery_ref")
        human = inputs.get("human_delivery_ref")
        if human is None:
            missing.append("human_delivery_ref")
        acceptance = inputs.get("acceptance_ref")
        if not coordinator._acceptance_matches(acceptance, technical, human):
            missing.append("acceptance_ref")
        return tuple(dict.fromkeys(missing))

    def _recompute_lifecycle_state(
        self,
        run_id: str,
        previous: ArtifactRevision,
        state: ArtifactRevision,
        event: ArtifactRevision,
        artifacts: Mapping[ArtifactRef, ArtifactRevision],
        *,
        artifact_order: Mapping[ArtifactRef, int] | None = None,
        completion_obligations: Sequence[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        body = thaw_json(event.payload)
        transition = body.get("event")
        source = body.get("from")
        target = body.get("to")
        actor = body.get("actor")
        edge = _TRANSITIONS.get((str(previous.payload.get("state")), str(transition)))
        if source != previous.payload.get("state"):
            return dict(state.payload), self._divergence("event.from", source, previous.payload.get("state"))
        if edge is None:
            return dict(state.payload), {"reason": "illegal_transition", "event": transition}
        if (
            target != edge[0]
            or actor != edge[1]
            and not (edge[1] == "human_or_operator" and actor in {"human", "operator"})
        ):
            return dict(state.payload), {
                "reason": "transition_authority_violation",
                "event": transition,
                "expected_target": edge[0],
                "expected_actor": edge[1],
            }
        coordinator = ResearchRunCoordinator(self.ledger)
        inputs = body.get("payload", {})
        if transition == "delivery_accepted":
            expected = coordinator._state_payload(
                state=str(target),
                lifecycle_revision=int(previous.payload.get("lifecycle_revision", 0)) + 1,
                obligations=(),
                legal_actions=("export_audit",),
                idempotency_key=body.get("idempotency_key"),
            )
        else:
            if not isinstance(inputs, Mapping):
                return dict(state.payload), {"reason": "event_payload_invalid", "event": transition}
            guard_error = self._validate_lifecycle_guard(
                run_id,
                str(transition),
                inputs,
                previous,
                event,
                artifacts,
                artifact_order,
            )
            if guard_error is not None:
                return dict(state.payload), guard_error
            expected = coordinator._state_payload(
                state=str(target),
                lifecycle_revision=int(previous.payload.get("lifecycle_revision", 0)) + 1,
                obligations=inputs.get("unmet_obligations", previous.payload.get("unmet_obligations", ())),
                legal_actions=coordinator._next_actions(str(target)),
                idempotency_key=body.get("idempotency_key"),
                macro_stage_value=macro_stage(str(target), prior_stage=previous.payload.get("macro_stage")),
            )
            expected["transition_payload"] = dict(inputs)
        expected["previous_state_ref"] = self._artifact_ref(previous).to_dict()
        coordinator._carry_correction_context(previous, expected)
        if isinstance(inputs, Mapping) and "authority_binding" in inputs:
            expected["active_authority"] = thaw_json(inputs["authority_binding"])
        if isinstance(inputs, Mapping) and "projection_ref" in inputs:
            expected["strategy_projection_ref"] = thaw_json(inputs["projection_ref"])
            expected["strategy_display_digest"] = inputs.get("display_digest")
        if transition == "delivery_accepted":
            completion = next(
                (
                    artifacts[reference]
                    for reference in state.parent_refs
                    if reference in artifacts and artifacts[reference].kind == COMPLETION_RECORD_KIND
                ),
                None,
            )
            if completion is None:
                return expected, {"reason": "completion_record_missing", "event": transition}
            requirements = thaw_json(completion.payload.get("requirements", {}))
            expected["completion_requirements"] = requirements
            reference_error = self._completion_reference_error(expected["completion_requirements"], artifacts)
            if reference_error is not None:
                return expected, reference_error
            canonical_inputs = coordinator._completion_inputs(run_id)
            canonical_requirements = {
                key: self._artifact_ref(item).to_dict() for key, item in sorted(canonical_inputs.items())
            }
            if requirements != canonical_requirements:
                return expected, {
                    "reason": "completion_inputs_divergence",
                    "stored_digest": _digest_payload(requirements),
                    "recomputed_digest": _digest_payload(canonical_requirements),
                }
            missing = (
                tuple(completion_obligations)
                if completion_obligations is not None
                else coordinator._completion_obligations(run_id)
            )
            if missing:
                return expected, {
                    "reason": "completion_obligations_unresolved",
                    "obligations": list(missing),
                }
            completion_parent_refs = set(completion.parent_refs)
            if any(
                ArtifactRef.from_dict(reference) not in completion_parent_refs for reference in requirements.values()
            ):
                return expected, {"reason": "completion_record_lineage_incomplete"}
            if completion.payload.get("source_state_ref") != self._artifact_ref(previous).to_dict():
                return expected, {"reason": "completion_source_state_mismatch"}
        expected["state_digest"] = _digest_payload(
            {key: value for key, value in expected.items() if key != "state_digest"}
        )
        return expected, None

    def _recompute_correction_state(
        self,
        run_id: str,
        previous: ArtifactRevision,
        state: ArtifactRevision,
        event: ArtifactRevision,
        artifacts: Mapping[ArtifactRef, ArtifactRevision],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        try:
            correction = CorrectionEvent.from_value(thaw_json(event.payload))
        except (TypeError, ValueError) as error:
            return dict(state.payload), {"reason": "correction_event_invalid", "detail": str(error)}
        coordinator = ResearchRunCoordinator(self.ledger)
        expected = coordinator._state_payload(
            state="alignment",
            lifecycle_revision=int(previous.payload.get("lifecycle_revision", 0)) + 1,
            obligations=(
                "alignment_reconfirmation",
                "strategy_reprojection",
                "handoff_reconfirmation",
                "closure_revalidation",
                "delivery_recompilation",
                "acceptance_reconfirmation",
            ),
            legal_actions=coordinator._next_actions("alignment"),
            idempotency_key=correction.event_id,
            reason=correction.reason,
        )
        quarantine_ref = state.payload.get("quarantine_ref")
        expected.update(
            {
                "task_id": correction.successor_task_id,
                "domain_id": correction.successor_domain_id,
                "correction_event_id": correction.event_id,
                "correction_relation": correction.relation,
                "previous_state_ref": self._artifact_ref(previous).to_dict(),
                "quarantine_ref": thaw_json(quarantine_ref),
                "authority_streams": thaw_json(previous.payload.get("authority_streams", {})),
            }
        )
        if not isinstance(quarantine_ref, Mapping):
            return expected, {"reason": "quarantine_reference_missing"}
        try:
            quarantine = artifacts[ArtifactRef.from_dict(quarantine_ref)]
        except (KeyError, TypeError, ValueError):
            return expected, {"reason": "quarantine_reference_invalid"}
        if quarantine.kind != STALE_STATE_QUARANTINE_KIND:
            return expected, {"reason": "quarantine_kind_invalid"}
        if quarantine.payload.get("correction_event_id") != correction.event_id:
            return expected, {"reason": "quarantine_correction_mismatch"}
        expected["state_digest"] = _digest_payload(
            {key: value for key, value in expected.items() if key != "state_digest"}
        )
        return expected, None

    def _validate_host_events(
        self,
        run_id: str,
        snapshot: Any,
        artifacts: Mapping[ArtifactRef, ArtifactRevision],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        coordinator = ResearchRunCoordinator(self.ledger)
        host_events = sorted(
            (item for item in snapshot.artifacts if item.kind == HOST_EVENT_KIND),
            key=lambda item: (item.created_at, item.id, item.revision),
        )
        artifact_lineage = [event.artifact_ref for event in snapshot.lineage_events if event.artifact_ref is not None]
        artifact_order = {reference: index for index, reference in enumerate(artifact_lineage)}
        by_attempt: dict[str, list[HostEvent]] = {}
        divergences: list[dict[str, Any]] = []
        digests: list[str] = []
        for item in host_events:
            body = thaw_json(item.payload)
            if "run_id" not in body or "expected_revision" not in body:
                continue
            try:
                envelope = HostEvent.from_value(body)
            except (HostEventError, TypeError, ValueError) as error:
                divergences.append({"reason": "host_event_invalid", "event_id": item.id, "detail": str(error)})
                continue
            digests.append(envelope.semantic_digest)
            if body.get("authoritative") is not False or body.get("semantic_digest") != envelope.semantic_digest:
                divergences.append({"reason": "host_event_digest_or_authority_invalid", "event_id": item.id})
            if envelope.expected_revision != artifact_order.get(self._artifact_ref(item), -1):
                divergences.append({"reason": "stale_expected_revision", "event_id": item.id})
            projection = next(
                (
                    candidate
                    for candidate in snapshot.artifacts
                    if candidate.kind == HOST_EVENT_PROJECTION_KIND
                    and candidate.payload.get("event_ref") == self._artifact_ref(item).to_dict()
                ),
                None,
            )
            lease = next(
                (
                    artifacts[reference]
                    for reference in (projection.parent_refs if projection is not None else ())
                    if reference in artifacts and artifacts[reference].kind == LEASE_KIND
                ),
                None,
            )
            if lease is None or lease.payload.get("attempt_id") != envelope.attempt_id:
                divergences.append({"reason": "lease_missing_or_mismatched", "event_id": item.id})
            else:
                expires_at = lease.payload.get("expires_at")
                try:
                    expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")) if expires_at else None
                    created = datetime.fromisoformat(envelope.created_at.replace("Z", "+00:00"))
                    if lease.payload.get("status") != "active" or expiry is not None and created >= expiry:
                        divergences.append({"reason": "lease_invalid_at_event", "event_id": item.id})
                except (TypeError, ValueError):
                    divergences.append({"reason": "lease_expiry_invalid", "event_id": item.id})
            by_attempt.setdefault(envelope.attempt_id, []).append(envelope)
            try:
                coordinator._validate_host_event_payload(envelope, run_id=run_id, attempt_id=envelope.attempt_id)
            except Exception as error:
                divergences.append({"reason": "host_event_payload_invalid", "event_id": item.id, "detail": str(error)})
        for attempt_id, events in by_attempt.items():
            ordered = sorted(events, key=lambda item: item.sequence)
            previous_id = None
            for expected_sequence, event in enumerate(ordered, start=1):
                if event.sequence != expected_sequence:
                    divergences.append({"reason": "host_event_sequence_gap", "event_id": event.event_id})
                if event.sequence == 1:
                    if event.causation_id not in (None, attempt_id):
                        divergences.append({"reason": "host_event_causation_invalid", "event_id": event.event_id})
                elif event.causation_id != previous_id:
                    divergences.append({"reason": "host_event_causation_invalid", "event_id": event.event_id})
                previous_id = event.event_id
        return divergences, sorted(digests)

    @staticmethod
    def _completion_reference_error(
        requirements: Any,
        artifacts: Mapping[ArtifactRef, ArtifactRevision],
    ) -> dict[str, Any] | None:
        if not isinstance(requirements, Mapping):
            return {"reason": "completion_requirements_invalid"}
        for name, value in requirements.items():
            try:
                reference = ArtifactRef.from_dict(value)
            except (TypeError, ValueError):
                return {"reason": "completion_reference_invalid", "field": str(name)}
            if reference not in artifacts:
                return {"reason": "completion_reference_missing", "field": str(name)}
        return None

    @staticmethod
    def _state_divergence(state: ArtifactRevision, expected: Mapping[str, Any]) -> dict[str, Any] | None:
        actual = thaw_json(state.payload)
        expected_value = thaw_json(expected)
        if actual == expected_value:
            return None
        keys = sorted(set(actual) | set(expected_value))
        for key in keys:
            if actual.get(key) != expected_value.get(key):
                return {
                    "reason": "state_divergence",
                    "sequence": state.payload.get("lifecycle_revision"),
                    "field": key,
                    "stored_digest": _digest_payload(actual.get(key)),
                    "recomputed_digest": _digest_payload(expected_value.get(key)),
                }
        return {"reason": "state_divergence", "sequence": state.payload.get("lifecycle_revision")}

    @staticmethod
    def _divergence(field: str, actual: Any, expected: Any) -> dict[str, Any]:
        return {
            "reason": "semantic_divergence",
            "field": field,
            "stored_digest": _digest_payload(actual),
            "recomputed_digest": _digest_payload(expected),
        }

    def explain_run(self, run_id: str) -> dict[str, Any]:
        replay = self.replay(run_id)
        why = self.why_not_complete(run_id)
        return {
            **replay,
            "state": why["state"],
            "unmet_obligations": why["unmet_obligations"],
            "next_actions": why["next_actions"],
            "evidence_gaps": why["evidence_gaps"],
            "host_events": self._host_traces(run_id),
            "completion_authority": "coordinator_only",
        }

    def why_not_complete(self, run_id: str) -> dict[str, Any]:
        result = ResearchRunCoordinator(self.ledger).why_not_complete(run_id)
        artifacts = self.ledger.load_run(run_id).artifacts
        gaps = []
        for obligation in result["unmet_obligations"]:
            kinds = _OBLIGATION_KINDS.get(obligation, frozenset())
            refs = sorted(
                (
                    ArtifactRef(item.round_id, item.id, item.revision).to_dict()
                    for item in artifacts
                    if item.kind in kinds
                ),
                key=lambda item: (item["artifact_id"], item["revision"]),
            )
            gaps.append({"obligation": obligation, "evidence_refs": refs})
        return {**result, "evidence_gaps": gaps, "completion_authority": "coordinator_only"}

    def why_action(self, run_id: str, action_id: str) -> dict[str, Any]:
        validate_identifier(run_id, "run_id")
        validate_identifier(action_id, "action_id")
        candidates = [
            item
            for item in self.ledger.load_run(run_id).artifacts
            if item.id == action_id or item.payload.get("action_id") == action_id
        ]
        if not candidates:
            raise CausalTraceError("unresolved action")
        action = max(candidates, key=lambda item: (item.revision, item.id))
        payload = thaw_json(action.payload)
        return {
            "schema_version": CAUSAL_TRACE_SCHEMA_VERSION,
            "run_id": run_id,
            "action_id": action_id,
            "artifact_ref": ArtifactRef(action.round_id, action.id, action.revision).to_dict(),
            "kind": action.kind,
            "inputs": _safe_value(payload.get("inputs", {}), "action inputs"),
            "score_components": dict(sorted(_score_components(payload.get("score_components", {})).items())),
            "outcome": _safe_value(payload.get("outcome", payload.get("disposition", "unknown")), "outcome"),
            "reason": _safe_value(payload.get("reason", "unspecified"), "reason"),
            "causal_refs": [reference.to_dict() for reference in action.parent_refs],
            "redaction_class": "allowlisted",
        }

    def reconcile_host(self, run_id: str, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        validate_identifier(run_id, "run_id")
        if isinstance(observations, (str, bytes)) or len(observations) > 500:
            raise CausalTraceError("host observations must be a bounded sequence")
        normalized = [_host_observation(value) for value in observations]
        counts = Counter(item["event_id"] for item in normalized)
        duplicates = sorted(event_id for event_id, count in counts.items() if count > 1)
        snapshot = self.ledger.load_run(run_id)
        canonical = {
            str(item.payload.get("event_id", item.id)): item
            for item in snapshot.artifacts
            if item.kind == HOST_EVENT_KIND
        }
        latest_sequence: dict[str, int] = {}
        for item in canonical.values():
            attempt_id = str(item.payload.get("attempt_id", ""))
            latest_sequence[attempt_id] = max(latest_sequence.get(attempt_id, 0), int(item.payload.get("sequence", 0)))
        results = []
        seen: set[str] = set()
        for item in normalized:
            event_id = item["event_id"]
            if event_id in seen:
                continue
            seen.add(event_id)
            recorded = canonical.get(event_id)
            if item["status"] == "unknown":
                classification = "uncertain"
            elif recorded is None:
                classification = "missing"
            elif recorded.payload.get("attempt_id") != item["attempt_id"]:
                classification = "divergent"
            elif item.get("sequence", 0) < latest_sequence.get(item["attempt_id"], 0):
                classification = "stale"
            else:
                classification = "matched"
            results.append({**item, "classification": classification, "authoritative": False})
        current = ResearchRunCoordinator(self.ledger).state(run_id)
        return {
            "schema_version": CAUSAL_TRACE_SCHEMA_VERSION,
            "run_id": run_id,
            "completion_authority": "coordinator_only",
            "canonical_state": current.payload["state"],
            "state_digest": current.payload["state_digest"],
            "duplicate_event_ids": duplicates,
            "observations": results,
        }

    @staticmethod
    def _verify_state_digest(state: ArtifactRevision) -> None:
        payload = thaw_json(state.payload)
        recorded = payload.pop("state_digest", None)
        calculated = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        if recorded == calculated:
            return
        if payload.get("lifecycle_revision") == 0:
            payload.pop("idempotency_key", None)
            payload.pop("reason", None)
            calculated = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        if recorded != calculated:
            raise CausalTraceError("digest_mismatch: research-run-state")

    @staticmethod
    def _trace_record(
        run_id: str,
        sequence: int,
        previous: ArtifactRevision,
        state: ArtifactRevision,
        event: ArtifactRevision,
        divergence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = thaw_json(event.payload)
        if body.get("event_id") != event.id:
            raise CausalTraceError("missing_cause: event identity")
        is_correction = event.kind == CORRECTION_EVENT_KIND
        if not is_correction and (
            body.get("from") != previous.payload.get("state") or body.get("to") != state.payload.get("state")
        ):
            raise CausalTraceError("missing_cause: state edge")
        if is_correction:
            raw_inputs = {
                "correction_event_id": body.get("event_id"),
                "relation": body.get("relation"),
                "reason_digest": hashlib.sha256(str(body.get("reason", "")).encode("utf-8")).hexdigest(),
                "successor_task_id": body.get("successor_task_id"),
                "successor_domain_id": body.get("successor_domain_id"),
                "affected_roles": sorted(body.get("affected", {})),
            }
        else:
            raw_inputs = body.get("payload", {})
            if isinstance(raw_inputs, Mapping) and "confirmation" in raw_inputs:
                raw_inputs = {key: value for key, value in raw_inputs.items() if key != "confirmation"}
                raw_inputs["confirmation_digest"] = hashlib.sha256(
                    str(body.get("payload", {}).get("confirmation", "")).encode("utf-8")
                ).hexdigest()
        inputs = _safe_value(raw_inputs, "transition inputs")
        actor = _safe_code(body.get("actor", "coordinator"), "actor")
        action = "correction" if is_correction else _safe_code(body.get("event", "unknown"), "action")
        host = _safe_code(inputs.get("host", "coordinator"), "host") if isinstance(inputs, Mapping) else "coordinator"
        trace_id = (
            "trace-"
            + hashlib.sha256(
                canonical_json_bytes({"event_hash": event.content_hash, "state_hash": state.content_hash})
            ).hexdigest()[:24]
        )
        record = {
            "schema_version": CAUSAL_TRACE_SCHEMA_VERSION,
            "trace_id": trace_id,
            "run_id": run_id,
            "event_id": event.id,
            "causation_id": event.id,
            "correlation_id": run_id,
            "sequence": sequence,
            "emitted_at": event.created_at,
            "actor": actor,
            "host": host,
            "round_id": run_id,
            "decision_slot_id": inputs.get("decision_slot_id") if isinstance(inputs, Mapping) else None,
            "attempt_id": inputs.get("attempt_id") if isinstance(inputs, Mapping) else None,
            "prior_digest": previous.payload["state_digest"],
            "next_digest": state.payload["state_digest"],
            "action": action,
            "inputs": inputs,
            "score_components": _score_components(
                inputs.get("score_components", {}) if isinstance(inputs, Mapping) else {}
            ),
            "outcome": state.payload.get("state") if is_correction else body.get("to"),
            "reason": "correction"
            if is_correction
            else inputs.get("reason", "transition_accepted")
            if isinstance(inputs, Mapping)
            else "transition_accepted",
            "redaction_class": "allowlisted",
            "retention_class": "canonical-lineage",
            "artifact_refs": [
                ArtifactRef(previous.round_id, previous.id, previous.revision).to_dict(),
                ArtifactRef(event.round_id, event.id, event.revision).to_dict(),
                ArtifactRef(state.round_id, state.id, state.revision).to_dict(),
            ],
        }
        if divergence is not None:
            record["divergence"] = dict(divergence)
        return record

    def _host_traces(self, run_id: str) -> list[dict[str, Any]]:
        records = []
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind != HOST_EVENT_KIND:
                continue
            body = thaw_json(item.payload)
            payload = body.get("payload", {})
            if not isinstance(payload, Mapping):
                raise CausalTraceError("host event diagnostic payload is invalid")
            diagnostic = {}
            for key in sorted(set(payload) & _SAFE_HOST_DIAGNOSTIC_FIELDS):
                value = payload[key]
                diagnostic[key] = normalize_host_path(str(value)) if key == "log_ref" else _safe_value(value, key)
            records.append(
                {
                    "event_id": _safe_code(body.get("event_id", item.id), "event_id"),
                    "kind": _safe_code(body.get("kind", "observation"), "kind"),
                    "action_id": _optional_safe_code(body.get("action_id"), "action_id"),
                    "attempt_id": _safe_code(body.get("attempt_id", "unknown-attempt"), "attempt_id"),
                    "sequence": body.get("sequence", 0),
                    "actor": _safe_code(body.get("actor", "host"), "actor"),
                    "diagnostic": diagnostic,
                    "authoritative": False,
                }
            )
        return sorted(records, key=lambda value: (value["attempt_id"], value["sequence"], value["event_id"]))


def _safe_value(value: Any, label: str, *, depth: int = 0) -> Any:
    if depth > 5:
        raise CausalTraceError(f"{label} is too deeply nested")
    if isinstance(value, Mapping):
        if len(value) > 32:
            raise CausalTraceError(f"{label} has too many fields")
        result = {}
        for key, child in sorted(value.items(), key=lambda item: str(item[0])):
            name = str(key)
            if any(part in name.lower() for part in _SENSITIVE_KEY_PARTS):
                raise CausalTraceError(f"sensitive diagnostic field: {name}")
            if not CODE_RE.fullmatch(name):
                raise CausalTraceError(f"{label} contains an invalid field")
            result[name] = _safe_value(child, label, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        if len(value) > 64:
            raise CausalTraceError(f"{label} has too many values")
        return [_safe_value(item, label, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return _safe_code(value, label)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise CausalTraceError(f"{label} contains an unsupported value")


def _safe_code(value: Any, label: str) -> str:
    text = str(value)
    if not CODE_RE.fullmatch(text):
        raise CausalTraceError(f"{label} must be a bounded diagnostic identifier")
    return text


def _optional_safe_code(value: Any, label: str) -> str | None:
    return None if value is None else _safe_code(value, label)


def _score_components(value: Any) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or len(value) > 32:
        raise CausalTraceError("score components must be a bounded object")
    result: dict[str, float] = {}
    for key, component in value.items():
        name = str(key)
        if not CODE_RE.fullmatch(name) or isinstance(component, bool) or not isinstance(component, (int, float)):
            raise CausalTraceError("score components must contain named numeric values")
        result[name] = float(component)
    return result


def _host_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CausalTraceError("host observation must be an object")
    sensitive = sorted(str(key) for key in value if any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS))
    if sensitive:
        raise CausalTraceError(f"sensitive diagnostic field: {sensitive[0]}")
    unknown = set(value) - _HOST_OBSERVATION_FIELDS
    if unknown:
        raise CausalTraceError(f"unsupported host observation field: {sorted(unknown)[0]}")
    event_id = str(value.get("event_id", ""))
    attempt_id = str(value.get("attempt_id", ""))
    status = str(value.get("status", ""))
    try:
        validate_identifier(event_id, "event_id")
        validate_identifier(attempt_id, "attempt_id")
    except (TypeError, ValueError) as error:
        raise CausalTraceError("host observation identifiers are invalid") from error
    if status not in _HOST_STATUSES:
        raise CausalTraceError("host observation status is invalid")
    result: dict[str, Any] = {"event_id": event_id, "attempt_id": attempt_id, "status": status}
    if "sequence" in value:
        sequence = value["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise CausalTraceError("host observation sequence is invalid")
        result["sequence"] = sequence
    for field in ("category", "code"):
        if field in value:
            item = str(value[field])
            if not CODE_RE.fullmatch(item):
                raise CausalTraceError(f"host observation {field} is invalid")
            result[field] = item
    if "log_ref" in value:
        result["log_ref"] = normalize_host_path(str(value["log_ref"]))
    return result


def find_project_root(start: Path) -> Path:
    """Find the checkout that owns an opt-in debug trace."""
    current = start.resolve(strict=False)
    for candidate in (current, *current.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "packages").is_dir()
            and (candidate / "skill-src").is_dir()
        ):
            return candidate
    raise DebugTraceError("debug tracing must run inside a Research Tree checkout")


def _inside(root: Path, candidate: Path) -> Path:
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise DebugTraceError("debug trace path must remain inside the project") from exc
    return resolved


def _project_root(project_root: Path | None) -> Path:
    root = project_root.resolve(strict=False) if project_root is not None else find_project_root(Path.cwd())
    if not ((root / "pyproject.toml").is_file() and (root / "packages").is_dir() and (root / "skill-src").is_dir()):
        raise DebugTraceError("project root is not a Research Tree checkout")
    return root


def _identifier(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if not IDENTIFIER_RE.fullmatch(value):
        raise DebugTraceError(f"{label} must be a bounded identifier")
    return value


def _codes(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not CODE_RE.fullmatch(value):
            raise DebugTraceError("debug code must be a bounded identifier")
        result.append(value)
    if len(result) > 16:
        raise DebugTraceError("a debug trace accepts at most 16 codes")
    return result


def _write_record(root: Path, record: dict[str, Any]) -> Path:
    destination = _inside(
        root,
        root / TRACE_DIRECTORY,
    )
    destination.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    for _ in range(3):
        prefix = f"{time.time_ns():020d}"
        path = _inside(
            root,
            destination / f"{prefix}-{secrets.token_hex(8)}.json",
        )
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        return path
    raise DebugTraceError("could not allocate a debug trace file")


def emit_trace(
    *,
    host: str,
    phase: str,
    status: str,
    codes: Iterable[str] = (),
    run_id: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Persist one sanitized workflow transition and return its relative path."""
    if host not in HOSTS:
        raise DebugTraceError(f"unsupported debug host: {host}")
    if phase not in PHASES:
        raise DebugTraceError(f"unsupported debug phase: {phase}")
    if status not in STATUSES:
        raise DebugTraceError(f"unsupported debug status: {status}")

    root = _project_root(project_root)
    record: dict[str, Any] = {
        "schema": 1,
        "source": "research-tree-debug",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "host": host,
        "phase": phase,
        "status": status,
        "codes": _codes(codes),
    }
    normalized_run_id = _identifier(run_id, "run id")
    if normalized_run_id is not None:
        record["run_id"] = normalized_run_id
    path = _write_record(root, record)
    return {"status": "recorded", "path": path.relative_to(root).as_posix()}


def summarize_traces(*, project_root: Path | None = None, limit: int = 25) -> dict[str, Any]:
    """Return a bounded, chronological summary of sanitized trace files."""
    if limit < 1 or limit > 200:
        raise DebugTraceError("limit must be between 1 and 200")
    root = _project_root(project_root)
    trace_dir = _inside(root, root / TRACE_DIRECTORY)
    records: list[dict[str, Any]] = []
    if trace_dir.is_dir():
        for path in sorted(trace_dir.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                records.append(value)
    phases = Counter(item["phase"] for item in records if isinstance(item.get("phase"), str))
    statuses = Counter(item["status"] for item in records if isinstance(item.get("status"), str))
    return {
        "schema": 1,
        "trace_directory": trace_dir.relative_to(root).as_posix(),
        "event_count": len(records),
        "by_phase": dict(sorted(phases.items())),
        "by_status": dict(sorted(statuses.items())),
        "recent": records[-limit:],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-tree-debug",
        description="Emit or summarize sanitized Research Tree workflow traces.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    emit = commands.add_parser("emit", help="write one sanitized phase event")
    emit.add_argument("--host", choices=tuple(sorted(HOSTS)), required=True)
    emit.add_argument("--phase", choices=tuple(sorted(PHASES)), required=True)
    emit.add_argument("--status", choices=tuple(sorted(STATUSES)), required=True)
    emit.add_argument("--code", action="append", default=[])
    emit.add_argument("--run-id")
    emit.add_argument("--project-root", type=Path)

    summary = commands.add_parser("summary", help="summarize sanitized phase events")
    summary.add_argument("--project-root", type=Path)
    summary.add_argument("--limit", type=int, default=25)

    for name, help_text in (
        ("explain-run", "explain canonical run state and blockers"),
        ("why-not-complete", "list every canonical completion blocker"),
        ("replay", "verify and replay canonical lifecycle state"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--run-id", required=True)
        command.add_argument("--project-root", type=Path)
    why_action = commands.add_parser("why-action", help="explain one canonical research action")
    why_action.add_argument("--run-id", required=True)
    why_action.add_argument("--action-id", required=True)
    why_action.add_argument("--project-root", type=Path)
    reconcile = commands.add_parser("reconcile-host", help="compare host observations with canonical events")
    reconcile.add_argument("--run-id", required=True)
    reconcile.add_argument("--observations", type=Path, required=True)
    reconcile.add_argument("--project-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "emit":
            result = emit_trace(
                host=arguments.host,
                phase=arguments.phase,
                status=arguments.status,
                codes=arguments.code,
                run_id=arguments.run_id,
                project_root=arguments.project_root,
            )
        elif arguments.command == "summary":
            result = summarize_traces(project_root=arguments.project_root, limit=arguments.limit)
        else:
            service = CausalTraceService(RunLedger(arguments.project_root or Path.cwd()))
            if arguments.command == "explain-run":
                result = service.explain_run(arguments.run_id)
            elif arguments.command == "why-action":
                result = service.why_action(arguments.run_id, arguments.action_id)
            elif arguments.command == "why-not-complete":
                result = service.why_not_complete(arguments.run_id)
            elif arguments.command == "replay":
                result = service.replay(arguments.run_id)
            else:
                observations = json.loads(arguments.observations.read_text(encoding="utf-8"))
                if not isinstance(observations, list):
                    raise CausalTraceError("host observations JSON must be an array")
                result = service.reconcile_host(arguments.run_id, observations)
    except DebugTraceError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
