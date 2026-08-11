"""Single SQLite-backed authority for canonical research-run lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .domain import ArtifactRef, ArtifactRevision, RuntimeStoreError, canonical_json_bytes, thaw_json, validate_identifier
from .run_ledger import LedgerConflictError, RunLedger


LIFECYCLE_STATES = (
    "alignment", "handoff_pending", "autonomous_research", "synthesis", "readiness",
    "delivery_pending", "awaiting_acceptance", "completed", "paused", "blocked",
    "superseded", "authority_blocked", "failed",
)
RESEARCH_RUN_STATE_KIND = "research-run-state"
LIFECYCLE_EVENT_KIND = "lifecycle-event"
REJECTED_TRANSITION_KIND = "lifecycle-rejection"
HOST_EVENT_KIND = "host-event"
LEASE_KIND = "attempt-lease"
COMPLETION_RECORD_KIND = "completion-record"


class CoordinatorError(RuntimeStoreError):
    """Base coordinator boundary error."""


class CoordinatorConflictError(CoordinatorError):
    """Raised for stale revisions, invalid lineage, or unverifiable work."""


class CoordinatorEventConflictError(CoordinatorConflictError):
    """Raised when one event id is reused with a changed payload."""


class IllegalTransitionError(CoordinatorError):
    """Raised when a requested lifecycle edge or actor is not allowed."""


class CompletionBlockedError(CoordinatorError):
    """Raised when canonical completion obligations remain unresolved."""

    def __init__(self, unmet_obligations: Sequence[str]) -> None:
        self.unmet_obligations = tuple(unmet_obligations)
        super().__init__("completion_blocked: " + ", ".join(self.unmet_obligations))


@dataclass(frozen=True, slots=True)
class CoordinatorResult:
    code: int
    category: str
    retryability: str
    run_id: str
    safe_message: str
    unmet_obligations: tuple[str, ...] = ()
    evidence_refs: tuple[ArtifactRef, ...] = ()
    next_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "retryability": self.retryability,
            "run_id": self.run_id,
            "safe_message": self.safe_message,
            "unmet_obligations": list(self.unmet_obligations),
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "next_action": self.next_action,
        }


# This is the checked-in lifecycle matrix reduced to executable edges. Guards
# are evaluated by the operation that owns the relevant obligation set.
_TRANSITIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("alignment", "alignment_projection_ready"): ("handoff_pending", "coordinator"),
    ("alignment", "authority_impossible"): ("authority_blocked", "coordinator"),
    ("handoff_pending", "handoff_confirmed"): ("autonomous_research", "human"),
    ("handoff_pending", "alignment_feedback"): ("alignment", "human"),
    ("autonomous_research", "batch_checkpoint"): ("synthesis", "coordinator"),
    ("autonomous_research", "operational_limit"): ("paused", "coordinator"),
    ("synthesis", "closure_deficit"): ("autonomous_research", "coordinator"),
    ("synthesis", "all_slots_closed"): ("readiness", "coordinator"),
    ("readiness", "readiness_passed"): ("delivery_pending", "coordinator"),
    ("readiness", "readiness_deficit"): ("autonomous_research", "coordinator"),
    ("delivery_pending", "deliveries_compiled"): ("awaiting_acceptance", "coordinator"),
    ("awaiting_acceptance", "delivery_accepted"): ("completed", "human"),
    ("awaiting_acceptance", "needs_deeper_research"): ("autonomous_research", "human"),
    ("awaiting_acceptance", "intent_correction"): ("superseded", "coordinator"),
    ("paused", "resume"): ("autonomous_research", "coordinator"),
    ("blocked", "blocker_resolved"): ("autonomous_research", "coordinator"),
    ("alignment", "supersede"): ("superseded", "coordinator"),
    ("autonomous_research", "cancel_requested"): ("superseded", "human_or_operator"),
    ("autonomous_research", "fatal_failure"): ("failed", "coordinator"),
}


def _load_lifecycle_transitions() -> dict[tuple[str, str], tuple[str, str]]:
    """Load the repository's matrix so code and governance share one edge set."""

    matrix = (
        Path(__file__).resolve().parents[2]
        / "openspec"
        / "changes"
        / "unify-research-runtime-alpha2"
        / "registries"
        / "lifecycle-matrix-v1.json"
    )
    try:
        payload = json.loads(matrix.read_text(encoding="utf-8"))
        transitions = payload["transitions"]
        loaded = {
            (str(item["from"]), str(item["event"])): (str(item["to"]), str(item["actor"]))
            for item in transitions
        }
        if loaded:
            return loaded
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        pass
    return _TRANSITIONS


_TRANSITIONS = _load_lifecycle_transitions()


def _ref(value: ArtifactRef | Mapping[str, Any], label: str) -> ArtifactRef:
    if isinstance(value, ArtifactRef):
        return value
    try:
        return ArtifactRef.from_dict(value)
    except (TypeError, ValueError, RuntimeStoreError) as error:
        raise CoordinatorConflictError(f"{label} must be an exact artifact reference") from error


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _same_payload(existing: ArtifactRevision, payload: Mapping[str, Any]) -> bool:
    return canonical_json_bytes(thaw_json(existing.payload)) == canonical_json_bytes(payload)


class ResearchRunCoordinator:
    """The sole writer of lifecycle and completion state for one RunLedger."""

    def __init__(self, ledger: RunLedger, *, actor_id: str = "coordinator") -> None:
        if not isinstance(ledger, RunLedger):
            raise CoordinatorConflictError("ResearchRunCoordinator requires a RunLedger")
        self.ledger = ledger
        self.actor_id = validate_identifier(actor_id, "actor_id")

    def _load(self, reference: ArtifactRef, kind: str) -> ArtifactRevision:
        try:
            item = self.ledger.get_artifact(reference)
        except RuntimeStoreError as error:
            raise CoordinatorConflictError(f"unresolved {kind} reference") from error
        if item.kind != kind:
            raise CoordinatorConflictError(f"reference must identify {kind}")
        return item

    def _resolve_current(self, item: ArtifactRevision, kind: str, run_id: str) -> ArtifactRef:
        if not isinstance(item, ArtifactRevision) or item.kind != kind or item.round_id != run_id:
            raise CoordinatorConflictError(f"{kind} must belong to run {run_id}")
        reference = ArtifactRef(item.round_id, item.id, item.revision)
        stored = self._load(reference, kind)
        if stored != item or not self.ledger.is_latest_artifact(reference):
            raise CoordinatorConflictError(f"stale {kind} lineage")
        return reference

    def _states(self, run_id: str) -> tuple[ArtifactRevision, ...]:
        return tuple(item for item in self.ledger.load_run(run_id).artifacts if item.kind == RESEARCH_RUN_STATE_KIND)

    def _latest_state(self, run_id: str) -> ArtifactRevision:
        states = self._states(run_id)
        if not states:
            raise CoordinatorConflictError("run is not initialized")
        return max(states, key=lambda item: item.revision)

    def state(self, run_id: str) -> ArtifactRevision:
        validate_identifier(run_id, "run_id")
        return self._latest_state(run_id)

    def initialize(self, *, run_id: str, alignment_handoff: ArtifactRevision, blueprint_target: ArtifactRevision, expected_revision: int, idempotency_key: str | None = None) -> ArtifactRevision:
        validate_identifier(run_id, "run_id")
        try:
            existing = self._latest_state(run_id)
        except CoordinatorConflictError:
            existing = None
        if existing is not None:
            if idempotency_key is None or existing.payload.get("idempotency_key") == idempotency_key:
                return existing
            raise CoordinatorConflictError("run is already initialized")
        handoff_ref = self._resolve_current(alignment_handoff, "alignment-handoff", run_id)
        target_ref = self._resolve_current(blueprint_target, "blueprint-target", run_id)
        if handoff_ref not in blueprint_target.parent_refs:
            raise CoordinatorConflictError("blueprint-target lineage does not include alignment-handoff")
        payload = self._state_payload(
            state="alignment",
            lifecycle_revision=0,
            obligations=(),
            legal_actions=("alignment_projection_ready", "authority_impossible", "supersede"),
            idempotency_key=idempotency_key,
        )
        try:
            return self.ledger.append_artifact(
                run_id, "run-state", RESEARCH_RUN_STATE_KIND, payload,
                parent_refs=(handoff_ref, target_ref), expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    @staticmethod
    def _state_payload(*, state: str, lifecycle_revision: int, obligations: Sequence[str], legal_actions: Sequence[str], idempotency_key: str | None = None, reason: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "state": state,
            "lifecycle_revision": lifecycle_revision,
            "unmet_obligations": sorted(set(obligations)),
            "legal_next_actions": list(legal_actions),
        }
        body["state_digest"] = _digest(body)
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        if reason is not None:
            body["reason"] = reason
        return body

    @staticmethod
    def _next_actions(state: str) -> tuple[str, ...]:
        actions = sorted(event for (source, event), _ in _TRANSITIONS.items() if source == state)
        return tuple(actions)

    def _find_event_key(self, run_id: str, key: str) -> ArtifactRevision | None:
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind in {LIFECYCLE_EVENT_KIND, HOST_EVENT_KIND, REJECTED_TRANSITION_KIND} and item.payload.get("idempotency_key") == key:
                return item
        return None

    def _append_transition(self, *, run_id: str, current: ArtifactRevision, event: str, actor: str, target_state: str, expected_revision: int, idempotency_key: str | None, payload: Mapping[str, Any]) -> ArtifactRevision:
        key = idempotency_key or f"{event}:{current.revision}:{_digest(payload)[:16]}"
        prior = self._find_event_key(run_id, key)
        if prior is not None:
            if not _same_payload(prior, {**dict(payload), "event": event, "from": current.payload["state"], "to": target_state, "actor": actor, "idempotency_key": key}):
                raise CoordinatorEventConflictError("event_id_conflict")
            return self._latest_state(run_id)
        event_id = "event-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        event_payload = {
            "event_id": event_id, "idempotency_key": key, "event": event,
            "from": current.payload["state"], "to": target_state, "actor": actor,
            "payload": dict(payload),
        }
        event_ref = ArtifactRef(run_id, event_id, 1)
        state_payload = self._state_payload(
            state=target_state,
            lifecycle_revision=int(current.payload.get("lifecycle_revision", 0)) + 1,
            obligations=payload.get("unmet_obligations", current.payload.get("unmet_obligations", ())),
            legal_actions=self._next_actions(target_state),
            idempotency_key=key,
        )
        state_payload["transition_payload"] = dict(payload)
        state_payload["previous_state_ref"] = ArtifactRef(run_id, current.id, current.revision).to_dict()
        state_payload["state_digest"] = _digest({key: value for key, value in state_payload.items() if key != "state_digest"})
        try:
            created = self.ledger.append_artifact_batch(
                run_id,
                (
                    (event_id, LIFECYCLE_EVENT_KIND, event_payload, (ArtifactRef(run_id, current.id, current.revision),)),
                    ("run-state", RESEARCH_RUN_STATE_KIND, state_payload, (ArtifactRef(run_id, current.id, current.revision), event_ref)),
                ),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        return created[-1]

    def record_same_round_replan(
        self,
        run_id: str,
        *,
        reason: str,
        expected_revision: int,
        replan_id: str | None = None,
        affected_refs: Sequence[ArtifactRef] = (),
    ) -> ArtifactRevision:
        """Record a method/depth/evidence correction without changing run identity."""

        current = self._latest_state(run_id)
        if not isinstance(reason, str) or not reason.strip():
            raise CoordinatorConflictError("replan reason is required")
        refs = tuple(affected_refs)
        if any(not isinstance(ref, ArtifactRef) or ref.round_id != run_id for ref in refs):
            raise CoordinatorConflictError("replan references must belong to the run")
        artifact_id = replan_id or "same-round-replan-" + hashlib.sha256(reason.encode("utf-8")).hexdigest()[:20]
        payload = {
            "classification": "same_round_replan",
            "reason": reason.strip(),
            "affected_refs": [ref.to_dict() for ref in refs],
            "source_state_ref": ArtifactRef(run_id, current.id, current.revision).to_dict(),
        }
        try:
            return self.ledger.append_artifact(
                run_id,
                artifact_id,
                "same-round-replan",
                payload,
                parent_refs=(ArtifactRef(run_id, current.id, current.revision), *refs),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def create_successor(
        self,
        run_id: str,
        *,
        successor_run_id: str,
        reason: str,
        expected_revision: int,
        actor: str = "coordinator",
    ) -> ArtifactRevision:
        """Create and link a successor before superseding this run."""

        current = self._latest_state(run_id)
        validate_identifier(successor_run_id, "successor_run_id")
        if successor_run_id == run_id or not isinstance(reason, str) or not reason.strip():
            raise CoordinatorConflictError("successor identity and reason are required")
        source_ref = ArtifactRef(run_id, current.id, current.revision)
        try:
            self.ledger.create_run(successor_run_id, parent_run_id=run_id)
        except LedgerConflictError:
            existing = self.ledger.load_run(successor_run_id)
            if existing.record.parent_round_id != run_id:
                raise CoordinatorConflictError("successor already belongs to another run")
        link_payload = {
            "status": "superseded",
            "successor_run_id": successor_run_id,
            "reason": reason.strip(),
            "actor": actor,
        }
        try:
            link = self.ledger.append_artifact(
                run_id,
                "successor-link-" + successor_run_id,
                "round-supersession",
                link_payload,
                parent_refs=(source_ref,),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        return self.transition(
            run_id,
            "supersede" if current.payload["state"] == "alignment" else "intent_correction",
            actor,
            expected_revision=expected_revision + 1,
            payload={"successor_ref": ArtifactRef(run_id, link.id, link.revision).to_dict()},
        )

    def _record_rejection(self, *, run_id: str, current: ArtifactRevision, event: str, actor: str, reason: str, expected_revision: int) -> None:
        key = "rejection:" + _digest({"state": current.payload["state"], "event": event, "actor": actor, "reason": reason})[:24]
        if self._find_event_key(run_id, key) is not None:
            return
        payload = {
            "idempotency_key": key,
            "event": event,
            "actor": actor,
            "from": current.payload["state"],
            "reason": reason,
            "state_digest": current.payload["state_digest"],
        }
        try:
            self.ledger.append_artifact(
                run_id,
                "rejection-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24],
                REJECTED_TRANSITION_KIND,
                payload,
                parent_refs=(ArtifactRef(run_id, current.id, current.revision),),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def _guard_passes(self, run_id: str, event: str) -> bool:
        inputs = self._completion_inputs(run_id)
        if event == "handoff_confirmed":
            initial = min(self._states(run_id), key=lambda item: item.revision)
            handoff = next(
                (self.ledger.get_artifact(ref) for ref in initial.parent_refs if self.ledger.get_artifact(ref).kind == "alignment-handoff"),
                None,
            )
            return bool(handoff and handoff.payload.get("confirmed") is True)
        if event == "all_slots_closed":
            return "p0_closure_tokens" not in self._completion_obligations(run_id)
        if event == "readiness_passed":
            return bool(
                inputs.get("readiness_ref")
                and inputs["readiness_ref"].payload.get("status") in {"ready", "passed"}
                and inputs.get("evaluation_ref")
                and inputs["evaluation_ref"].payload.get("status") in {"passed", "pass"}
            )
        if event == "deliveries_compiled":
            return inputs.get("technical_delivery_ref") is not None and inputs.get("human_delivery_ref") is not None
        return True

    def transition(self, run_id: str, event: str, actor: str, *, expected_revision: int, idempotency_key: str | None = None, payload: Mapping[str, Any] | None = None) -> ArtifactRevision:
        current = self._latest_state(run_id)
        if idempotency_key is not None:
            prior = self._find_event_key(run_id, idempotency_key)
            if prior is not None:
                prior_payload = thaw_json(prior.payload)
                if (
                    prior.kind != LIFECYCLE_EVENT_KIND
                    or prior_payload.get("event") != event
                    or prior_payload.get("actor") != actor
                    or prior_payload.get("payload") != dict(payload or {})
                ):
                    raise CoordinatorEventConflictError("event_id_conflict")
                return self._latest_state(run_id)
        edge = _TRANSITIONS.get((str(current.payload["state"]), event))
        if edge is None:
            self._record_rejection(run_id=run_id, current=current, event=event, actor=actor, reason="illegal_transition", expected_revision=expected_revision)
            raise IllegalTransitionError("illegal_transition")
        target_state, required_actor = edge
        if required_actor == "human_or_operator":
            allowed = actor in {"human", "operator"}
        else:
            allowed = actor == required_actor
        if not allowed:
            self._record_rejection(run_id=run_id, current=current, event=event, actor=actor, reason="actor_not_allowed", expected_revision=expected_revision)
            raise IllegalTransitionError("actor_not_allowed")
        if not self._guard_passes(run_id, event):
            self._record_rejection(run_id=run_id, current=current, event=event, actor=actor, reason="guard_failed", expected_revision=expected_revision)
            raise IllegalTransitionError("guard_failed")
        if event == "delivery_accepted":
            return self.complete(
                run_id,
                actor=actor,
                expected_revision=expected_revision,
                requirements=payload,
            )
        return self._append_transition(
            run_id=run_id, current=current, event=event, actor=actor,
            target_state=target_state, expected_revision=expected_revision,
            idempotency_key=idempotency_key, payload=payload or {},
        )

    def ingest_event(self, *, run_id: str, event_id: str, attempt_id: str, payload: Mapping[str, Any], expected_revision: int) -> ArtifactRevision:
        validate_identifier(event_id, "event_id")
        event_digest = _digest(payload)
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind == HOST_EVENT_KIND and item.payload.get("event_id") == event_id:
                if item.payload.get("payload_digest") != event_digest:
                    raise CoordinatorEventConflictError("event_id_conflict")
                return item
        current = self._latest_state(run_id)
        event_payload = {
            "event_id": event_id, "attempt_id": _text(attempt_id, "attempt_id"),
            "payload_digest": event_digest, "payload": dict(payload),
        }
        try:
            return self.ledger.append_artifact(
                run_id, event_id, HOST_EVENT_KIND, event_payload,
                parent_refs=(ArtifactRef(run_id, current.id, current.revision),),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def dispatch(self, *, run_id: str, work_item: Mapping[str, Any], worker_id: str, expected_revision: int, attempt_id: str | None = None) -> ArtifactRevision:
        if not isinstance(work_item, Mapping) or not work_item.get("success_oracle") and not work_item.get("completion_evidence"):
            raise CoordinatorConflictError("unverifiable_work_item")
        current = self._latest_state(run_id)
        selected_attempt = attempt_id or "attempt-" + hashlib.sha256(canonical_json_bytes(work_item)).hexdigest()[:24]
        validate_identifier(selected_attempt, "attempt_id")
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind == LEASE_KIND and item.id == selected_attempt:
                return item
        payload = {
            "attempt_id": selected_attempt,
            "work_item": dict(work_item),
            "worker_id": _text(worker_id, "worker_id"),
            "status": "active",
            "retry_ordinal": 0,
            "idempotency_key": selected_attempt,
            "lease_revision": 1,
        }
        try:
            return self.ledger.append_artifact(
                run_id, selected_attempt, LEASE_KIND, payload,
                parent_refs=(ArtifactRef(run_id, current.id, current.revision),),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    @staticmethod
    def _artifact_ref(item: ArtifactRevision) -> ArtifactRef:
        return ArtifactRef(item.round_id, item.id, item.revision)

    def _latest_kind(self, run_id: str, kind: str) -> ArtifactRevision | None:
        """Return the current revision for a singleton coordinator input kind."""

        candidates = [
            item for item in self.ledger.load_run(run_id).artifacts
            if item.kind == kind and self.ledger.is_latest_artifact(self._artifact_ref(item))
        ]
        return max(candidates, key=lambda item: (item.revision, item.id)) if candidates else None

    def _target(self, run_id: str) -> ArtifactRevision | None:
        states = self._states(run_id)
        if not states:
            return None
        initial = min(states, key=lambda item: item.revision)
        for reference in initial.parent_refs:
            candidate = self.ledger.get_artifact(reference)
            if candidate.kind == "blueprint-target" and self.ledger.is_latest_artifact(reference):
                return candidate
        return None

    def _completion_inputs(self, run_id: str) -> dict[str, ArtifactRevision]:
        result: dict[str, ArtifactRevision] = {}
        for key, kind in (
            ("insight_ref", "insight-digest"),
            ("readiness_ref", "readiness-record"),
            ("evaluation_ref", "blueprint-evaluation"),
            ("technical_delivery_ref", "technical-research-package"),
            ("human_delivery_ref", "human-research-report"),
            ("acceptance_ref", "delivery-acceptance"),
        ):
            item = self._latest_kind(run_id, kind)
            if item is not None:
                result[key] = item
        return result

    def _completion_obligations(self, run_id: str) -> tuple[str, ...]:
        """Evaluate completion from ledger evidence, never host supplied claims."""

        missing: list[str] = []
        target = self._target(run_id)
        p0_slots = {
            str(slot.get("id"))
            for slot in target.payload.get("decision_slots", ())
            if isinstance(slot, Mapping) and slot.get("priority") == "P0" and slot.get("id")
        } if target is not None else set()
        assessments = [
            item for item in self.ledger.load_run(run_id).artifacts
            if item.kind == "slot-closure-assessment"
            and self.ledger.is_latest_artifact(self._artifact_ref(item))
            and item.payload.get("status") == "passed"
            and item.payload.get("closure_token")
            and (target is None or self._artifact_ref(target) in item.parent_refs)
        ]
        closed_slots = {str(item.payload.get("slot_id")) for item in assessments}
        if not p0_slots or not p0_slots <= closed_slots:
            missing.append("p0_closure_tokens")

        inputs = self._completion_inputs(run_id)
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
        if not self._acceptance_matches(acceptance, technical, human):
            missing.append("acceptance_ref")
        return tuple(dict.fromkeys(missing))

    def _acceptance_matches(self, acceptance: ArtifactRevision | None, technical: ArtifactRevision | None, human: ArtifactRevision | None) -> bool:
        if acceptance is None or technical is None or human is None:
            return False
        if acceptance.payload.get("decision", acceptance.payload.get("status")) not in {"accepted", "passed"}:
            return False
        technical_ref = self._artifact_ref(technical)
        human_ref = self._artifact_ref(human)
        if not {technical_ref, human_ref} <= set(acceptance.parent_refs):
            return False
        return True

    def why_not_complete(self, run_id: str) -> dict[str, Any]:
        current = self._latest_state(run_id)
        missing = self._completion_obligations(run_id)
        if not missing and current.payload.get("state") == "completed":
            missing = ()
        return {
            "run_id": run_id,
            "state": current.payload["state"],
            "unmet_obligations": missing,
            "next_actions": ["resolve:" + item for item in missing],
            "state_digest": current.payload["state_digest"],
        }

    def complete(self, run_id: str, *, actor: str, expected_revision: int, requirements: Mapping[str, Any] | None = None) -> ArtifactRevision:
        current = self._latest_state(run_id)
        if current.payload["state"] in {"completed", "superseded"}:
            return current
        if current.payload["state"] != "awaiting_acceptance":
            raise IllegalTransitionError("illegal_transition")
        if actor != "human":
            raise IllegalTransitionError("actor_not_allowed")
        missing = self._completion_obligations(run_id)
        if missing:
            raise CompletionBlockedError(missing)
        inputs = self._completion_inputs(run_id)
        event_key = "completion:" + _digest({key: self._artifact_ref(item).to_dict() for key, item in sorted(inputs.items())})[:24]
        existing = self._find_event_key(run_id, event_key)
        if existing is not None:
            return self._latest_state(run_id)
        event_id = "event-" + hashlib.sha256(event_key.encode()).hexdigest()[:24]
        event_payload = {"event_id": event_id, "idempotency_key": event_key, "event": "delivery_accepted", "actor": actor, "from": current.payload["state"], "to": "completed"}
        event_ref = ArtifactRef(run_id, event_id, 1)
        completion_payload = {
            "status": "completed",
            "requirements": {key: self._artifact_ref(item).to_dict() for key, item in inputs.items()},
            "source_state_ref": ArtifactRef(run_id, current.id, current.revision).to_dict(),
        }
        completion_ref = ArtifactRef(run_id, "completion-record", 1)
        state_payload = self._state_payload(
            state="completed", lifecycle_revision=int(current.payload.get("lifecycle_revision", 0)) + 1,
            obligations=(), legal_actions=("export_audit",), idempotency_key=event_key,
        )
        state_payload["completion_requirements"] = completion_payload["requirements"]
        state_payload["previous_state_ref"] = ArtifactRef(run_id, current.id, current.revision).to_dict()
        state_payload["state_digest"] = _digest({key: value for key, value in state_payload.items() if key != "state_digest"})
        try:
            created = self.ledger.append_artifact_batch(
                run_id,
                (
                    (event_id, LIFECYCLE_EVENT_KIND, event_payload, (ArtifactRef(run_id, current.id, current.revision),)),
                    ("completion-record", COMPLETION_RECORD_KIND, completion_payload, (ArtifactRef(run_id, current.id, current.revision), event_ref, *(self._artifact_ref(item) for item in inputs.values()))),
                    ("run-state", RESEARCH_RUN_STATE_KIND, state_payload, (ArtifactRef(run_id, current.id, current.revision), event_ref, completion_ref)),
                ),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        return created[-1]

    def recover(self, run_id: str) -> dict[str, Any]:
        reconciled: list[str] = []
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind != LEASE_KIND or item.payload.get("status") != "active":
                continue
            latest = max((candidate for candidate in self.ledger.load_run(run_id).artifacts if candidate.id == item.id and candidate.kind == LEASE_KIND), key=lambda candidate: candidate.revision)
            if latest != item:
                continue
            payload = {**dict(item.payload), "status": "unknown", "recovery_reason": "process_restart"}
            try:
                self.ledger.append_artifact(
                    run_id, item.id, LEASE_KIND, payload,
                    parent_refs=(ArtifactRef(run_id, item.id, item.revision),),
                    expected_revision=self.ledger.get_revision(run_id),
                )
            except LedgerConflictError as error:
                raise CoordinatorConflictError("stale_revision") from error
            reconciled.append(str(item.payload["attempt_id"]))
        return {"run_id": run_id, "reconciled_attempts": sorted(reconciled), "state_digest": self._latest_state(run_id).payload["state_digest"]}


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoordinatorConflictError(f"{label} must be a non-empty string")
    return value


__all__ = [
    "COMPLETION_RECORD_KIND", "CoordinatorConflictError", "CoordinatorError", "CoordinatorEventConflictError",
    "CoordinatorResult", "CompletionBlockedError", "HOST_EVENT_KIND", "IllegalTransitionError", "LEASE_KIND",
    "LIFECYCLE_EVENT_KIND", "LIFECYCLE_STATES", "RESEARCH_RUN_STATE_KIND", "ResearchRunCoordinator",
]
