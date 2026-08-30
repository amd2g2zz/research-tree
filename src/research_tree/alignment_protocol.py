"""Canonical, replayable alignment actions over the SQLite run ledger."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    RuntimeStoreError,
    canonical_json_bytes,
    thaw_json,
    validate_identifier,
)
from .feedback import CORRECTION_EVENT_KIND, STALE_STATE_QUARANTINE_KIND
from .growth import BranchState, compute_readiness_delta
from .interaction_state import InteractionEvent, InteractionReducer, InteractionReduction, InteractionState
from .run_ledger import LedgerConflictError, RunLedger

ALIGNMENT_ACTION_KIND = "alignment-action"
ALIGNMENT_ATTEMPT_KIND = "alignment-attempt"
ALIGNMENT_BELIEF_KIND = "alignment-belief"
ALIGNMENT_FEEDBACK_KIND = "alignment-feedback"
ALIGNMENT_HANDOFF_KIND = "alignment-handoff"
ALIGNMENT_MESSAGE_KIND = "alignment-message"
ALIGNMENT_READINESS_KIND = "alignment-readiness"
ALIGNMENT_RESPONSE_KIND = "alignment-response"
ACTION_KINDS = frozenset({"reconnaissance", "question", "disagreement", "confirmation"})
ATTEMPT_STATUSES = frozenset({"pending", "consumed", "unknown", "deferred"})
BELIEF_ACTORS = frozenset({"human", "agent", "joint"})
CONFIDENCES = frozenset({"low", "medium", "high"})
DISAGREEMENT_DISPOSITIONS = frozenset({"supported", "refuted", "not_enough_information"})
MATERIAL_FEEDBACK_KINDS = frozenset(
    {"target_change", "priority_change", "authority_change", "success_change", "scope_change"}
)
REQUIRED_READINESS_FIELDS = (
    "outcome",
    "intended_use",
    "scope",
    "non_goals",
    "delivery",
    "authority",
    "safety",
    "success_oracle",
    "feasibility",
    "strategy",
)


class AlignmentProtocolError(RuntimeStoreError):
    """Raised when an alignment operation lacks durable semantic authority."""


class AlignmentConflictError(AlignmentProtocolError):
    """Raised for stale revisions, conflicting identities, or wrong responses."""


class AlignmentReadinessError(AlignmentProtocolError):
    """Raised when a handoff cannot meet all field-level obligations."""


class AlignmentMessageError(AlignmentProtocolError):
    """Raised when a user-facing message is unbounded or stale."""


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _payload(item: ArtifactRevision) -> dict[str, Any]:
    return thaw_json(item.payload)


def _same_payload(item: ArtifactRevision, payload: Mapping[str, Any]) -> bool:
    return canonical_json_bytes(_payload(item)) == canonical_json_bytes(payload)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AlignmentProtocolError(f"{label} must be a non-empty string")
    return value.strip()


_LEGACY_BELIEF_STATUSES = frozenset({"answered", "supported", "accepted", "disputed", "deferred", "unknown", "refuted"})


def _is_legacy_status(status: str) -> bool:
    """Return True for statuses kept for backward compatibility with existing beliefs."""

    return status in _LEGACY_BELIEF_STATUSES


def _number(value: Any, label: str, *, minimum: float = 0.0, maximum: float = 10.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AlignmentProtocolError(f"{label} must be numeric")
    number = float(value)
    if number < minimum or number > maximum:
        raise AlignmentProtocolError(f"{label} must be between {minimum:g} and {maximum:g}")
    return number


def _reference(value: Any, label: str) -> ArtifactRef:
    if isinstance(value, ArtifactRef):
        return value
    try:
        return ArtifactRef.from_dict(value)
    except (TypeError, ValueError, RuntimeStoreError) as error:
        raise AlignmentProtocolError(f"{label} must be an exact artifact reference") from error


def _refs(value: Any, label: str) -> tuple[ArtifactRef, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AlignmentProtocolError(f"{label} must be a sequence")
    result = tuple(_reference(item, f"{label}[{index}]") for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise AlignmentProtocolError(f"{label} must not contain duplicate references")
    return result


def _strings(value: Any, label: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if value is None and allow_empty:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AlignmentProtocolError(f"{label} must be a sequence")
    result = tuple(_text(item, f"{label}[{index}]") for index, item in enumerate(value))
    if not result and not allow_empty:
        raise AlignmentProtocolError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise AlignmentProtocolError(f"{label} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class AlignmentCandidate:
    """A host-neutral candidate that can be chosen for one alignment turn."""

    action_id: str
    kind: str
    field: str
    objective: str
    trigger_refs: tuple[str, ...]
    closure_oracle: str
    method_boundary: str
    belief_refs: tuple[ArtifactRef, ...] = ()
    evidence_refs: tuple[ArtifactRef, ...] = ()
    impact: float = 0.0
    human_exclusive: bool = False
    researchable: bool = True
    expected_ambiguity_reduction: float = 0.0
    decision_consequence: float = 0.0
    cognitive_load: float = 0.0
    repetition: float = 0.0

    def __post_init__(self) -> None:
        validate_identifier(self.action_id, "action_id")
        if self.kind not in ACTION_KINDS:
            raise AlignmentProtocolError(f"unsupported alignment action kind: {self.kind}")
        _text(self.field, "field")
        _text(self.objective, "objective")
        if not self.trigger_refs:
            raise AlignmentProtocolError("trigger_refs must identify an evidence or belief deficit")
        _text(self.closure_oracle, "closure_oracle")
        _text(self.method_boundary, "method_boundary")
        _number(self.impact, "impact")
        _number(self.expected_ambiguity_reduction, "expected_ambiguity_reduction", maximum=1.0)
        _number(self.decision_consequence, "decision_consequence")
        _number(self.cognitive_load, "cognitive_load")
        _number(self.repetition, "repetition")
        if self.human_exclusive and self.researchable:
            raise AlignmentProtocolError("human-exclusive candidate cannot be researchable")

    @classmethod
    def from_value(cls, value: "AlignmentCandidate | Mapping[str, Any]") -> "AlignmentCandidate":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise AlignmentProtocolError("candidate must be an AlignmentCandidate or mapping")
        try:
            action_id = validate_identifier(value.get("action_id"), "action_id")
        except (TypeError, ValueError, RuntimeStoreError) as error:
            raise AlignmentProtocolError("action_id must be a valid identifier") from error
        kind = str(value.get("kind", "reconnaissance"))
        field = _text(value.get("field", "unknown"), "field")
        objective = _text(value.get("objective"), "objective")
        trigger_refs = _strings(value.get("trigger_refs"), "trigger_refs", allow_empty=False)
        closure_oracle = _text(value.get("closure_oracle"), "closure_oracle")
        method_boundary = _text(value.get("method_boundary"), "method_boundary")
        human_exclusive = bool(value.get("human_exclusive", False))
        researchable = bool(value.get("researchable", not human_exclusive))
        return cls(
            action_id=action_id,
            kind=kind,
            field=field,
            objective=objective,
            trigger_refs=trigger_refs,
            closure_oracle=closure_oracle,
            method_boundary=method_boundary,
            belief_refs=_refs(value.get("belief_refs"), "belief_refs"),
            evidence_refs=_refs(value.get("evidence_refs"), "evidence_refs"),
            impact=_number(value.get("impact", 0), "impact"),
            human_exclusive=human_exclusive,
            researchable=researchable,
            expected_ambiguity_reduction=_number(
                value.get("expected_ambiguity_reduction", 0),
                "expected_ambiguity_reduction",
                maximum=1.0,
            ),
            decision_consequence=_number(value.get("decision_consequence", 0), "decision_consequence"),
            cognitive_load=_number(value.get("cognitive_load", 0), "cognitive_load"),
            repetition=_number(value.get("repetition", 0), "repetition"),
        )

    def score(self, *, state_digest: str, seed: int, policy_version: str) -> tuple[float, dict[str, float]]:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise AlignmentProtocolError("seed must be an integer")
        _text(policy_version, "policy_version")
        tie_digest = _digest({"action_id": self.action_id, "seed": seed, "state_digest": state_digest})
        tie_break = int(tie_digest[:12], 16) / float(16**12)
        factors = {
            "impact": self.impact,
            "human_exclusivity": 1.0 if self.human_exclusive else 0.0,
            "researchability": 1.0 if self.researchable else 0.0,
            "ambiguity_reduction": self.expected_ambiguity_reduction,
            "consequence": self.decision_consequence,
            "cognitive_load": self.cognitive_load,
            "repetition": self.repetition,
            "tie_break": tie_break,
        }
        score = (
            (self.impact * 4.0)
            + (self.expected_ambiguity_reduction * 5.0)
            + (self.decision_consequence * 2.0)
            + (2.0 if self.human_exclusive else 0.0)
            + (1.0 if self.researchable else 0.0)
            - self.cognitive_load
            - (self.repetition * 2.0)
        )
        return score, factors

    def to_payload(self, *, state_digest: str, seed: int, policy_version: str) -> dict[str, Any]:
        score, factors = self.score(state_digest=state_digest, seed=seed, policy_version=policy_version)
        return {
            "action_id": self.action_id,
            "kind": self.kind,
            "field": self.field,
            "objective": self.objective,
            "trigger_refs": list(self.trigger_refs),
            "belief_refs": [reference.to_dict() for reference in self.belief_refs],
            "evidence_refs": [reference.to_dict() for reference in self.evidence_refs],
            "impact": self.impact,
            "human_exclusive": self.human_exclusive,
            "researchable": self.researchable,
            "expected_ambiguity_reduction": self.expected_ambiguity_reduction,
            "decision_consequence": self.decision_consequence,
            "cognitive_load": self.cognitive_load,
            "repetition": self.repetition,
            "closure_oracle": self.closure_oracle,
            "method_boundary": self.method_boundary,
            "score": score,
            "score_factors": factors,
            "state_digest": state_digest,
            "policy_version": policy_version,
            "seed": seed,
            "status": "selected",
        }


AlignmentAction = AlignmentCandidate


class AlignmentProtocol:
    """Append-only alignment semantics; it never owns a lifecycle transition."""

    def __init__(self, ledger: RunLedger, run_id: str, *, coordinator: Any | None = None) -> None:
        if not isinstance(ledger, RunLedger):
            raise AlignmentProtocolError("AlignmentProtocol requires a RunLedger")
        self.ledger = ledger
        self.run_id = validate_identifier(run_id, "run_id")
        self.coordinator = coordinator
        try:
            ledger.get_revision(self.run_id)
        except RuntimeStoreError as error:
            raise AlignmentProtocolError(f"run does not exist: {self.run_id}") from error

    def _artifacts(self) -> tuple[ArtifactRevision, ...]:
        return self.ledger.load_run(self.run_id).artifacts

    def _latest(self, kind: str, artifact_id: str | None = None) -> tuple[ArtifactRevision, ...]:
        current: dict[str, ArtifactRevision] = {}
        for item in self._artifacts():
            if item.kind != kind or (artifact_id is not None and item.id != artifact_id):
                continue
            previous = current.get(item.id)
            if previous is None or item.revision > previous.revision:
                current[item.id] = item
        return tuple(sorted(current.values(), key=lambda item: (item.id, item.revision)))

    def _latest_one(self, kind: str, artifact_id: str) -> ArtifactRevision | None:
        values = self._latest(kind, artifact_id)
        return values[-1] if values else None

    def _append(
        self,
        artifact_id: str,
        kind: str,
        payload: Mapping[str, Any],
        *,
        parents: Sequence[ArtifactRef] = (),
    ) -> ArtifactRevision:
        validate_identifier(artifact_id, "artifact_id")
        existing = self._latest_one(kind, artifact_id)
        if existing is not None:
            if _same_payload(existing, payload):
                return existing
            raise AlignmentConflictError(f"artifact id payload conflict: {artifact_id}")
        try:
            return self.ledger.append_artifact(
                self.run_id,
                artifact_id,
                kind,
                dict(payload),
                parent_refs=tuple(parents),
                expected_revision=self.ledger.get_revision(self.run_id),
            )
        except LedgerConflictError as error:
            raise AlignmentConflictError("stale_revision") from error

    def _pending_attempt(self) -> ArtifactRevision | None:
        pending = [item for item in self._latest(ALIGNMENT_ATTEMPT_KIND) if _payload(item).get("status") == "pending"]
        if len(pending) > 1:
            raise AlignmentConflictError("multiple pending alignment attempts")
        return pending[0] if pending else None

    @staticmethod
    def _view(item: ArtifactRevision) -> dict[str, Any]:
        result = _payload(item)
        result["artifact_ref"] = ArtifactRef(item.round_id, item.id, item.revision).to_dict()
        return result

    def state_digest(self) -> str:
        records = [
            {
                "kind": item.kind,
                "id": item.id,
                "revision": item.revision,
                "payload": _payload(item),
            }
            for item in self._artifacts()
            if item.kind
            in {
                ALIGNMENT_ACTION_KIND,
                ALIGNMENT_ATTEMPT_KIND,
                ALIGNMENT_BELIEF_KIND,
                ALIGNMENT_FEEDBACK_KIND,
                ALIGNMENT_RESPONSE_KIND,
                CORRECTION_EVENT_KIND,
                STALE_STATE_QUARANTINE_KIND,
            }
        ]
        return _digest(records)

    def reduce_interaction(self, state: InteractionState, event: InteractionEvent) -> InteractionReduction:
        """Reduce a live interaction event without mutating lifecycle authority.

        Alignment remains an append-only evidence surface.  The caller owns
        persistence and lifecycle delivery of the resulting state; this narrow
        bridge ensures alignment and feedback use the same semantic reducer.
        """

        if state.run_id != self.run_id:
            raise AlignmentProtocolError("interaction state must belong to this run")
        try:
            return InteractionReducer().reduce(state, event)
        except RuntimeStoreError as error:
            raise AlignmentProtocolError(str(error)) from error

    def record_belief(
        self,
        *,
        belief_id: str,
        actor: str,
        field: str,
        statement: str,
        confidence: str,
        human_only: bool = False,
        basis_refs: Sequence[ArtifactRef | Mapping[str, Any]] = (),
        supersedes: Sequence[ArtifactRef | Mapping[str, Any]] = (),
        disagreement: str | None = None,
        consequence: str | None = None,
        status: str | None = None,
        speech_act: Any | None = None,
    ) -> dict[str, Any]:
        validate_identifier(belief_id, "belief_id")
        if actor not in BELIEF_ACTORS:
            raise AlignmentProtocolError("belief actor is unsupported")
        if confidence not in CONFIDENCES:
            raise AlignmentProtocolError("belief confidence is unsupported")
        if status is not None and status not in {
            "candidate",
            "supported",
            "refuted",
            "unknown",
            "isolated",
            "corroborated",
            "rejected",
            "superseded",
            "contested",
            "unasserted",
            "resolved",
        }:
            raise AlignmentProtocolError("belief status is unsupported")
        if human_only and actor != "human":
            raise AlignmentProtocolError("human-only fields require a human belief")
        if disagreement is not None and disagreement not in DISAGREEMENT_DISPOSITIONS:
            raise AlignmentProtocolError("disagreement disposition is unsupported")
        basis = _refs(basis_refs, "basis_refs")
        superseded = _refs(supersedes, "supersedes")
        if status is None:
            from .speech_acts import SpeechAct

            if speech_act is not None:
                if not isinstance(speech_act, SpeechAct):
                    raise AlignmentProtocolError("speech_act must be a SpeechAct when provided")
                try:
                    from .speech_acts import transition

                    status = transition("candidate", speech_act)
                except Exception as error:  # noqa: BLE001 - propagate as AlignmentProtocolError
                    raise AlignmentProtocolError(str(error)) from error
            else:
                status = "supported" if basis else "candidate"
        payload = {
            "belief_id": belief_id,
            "actor": actor,
            "field": _text(field, "field"),
            "statement": _text(statement, "statement"),
            "confidence": confidence,
            "human_only": bool(human_only),
            "basis_refs": [reference.to_dict() for reference in basis],
            "supersedes": [reference.to_dict() for reference in superseded],
            "disagreement": disagreement,
            "consequence": None if consequence is None else _text(consequence, "consequence"),
            "status": status,
        }
        if speech_act is not None:
            payload["speech_act"] = speech_act.to_dict()
        item = self._append(belief_id, ALIGNMENT_BELIEF_KIND, payload, parents=(*basis, *superseded))
        return self._view(item)

    def plan(
        self,
        candidates: Sequence[AlignmentCandidate | Mapping[str, Any]],
        *,
        seed: int = 0,
        policy_version: str = "alignment-v1",
    ) -> dict[str, Any]:
        pending = self._pending_attempt()
        if pending is not None:
            pending_payload = _payload(pending)
            action = self._latest_one(ALIGNMENT_ACTION_KIND, str(pending_payload["action_id"]))
            if action is None:
                raise AlignmentConflictError("pending attempt has no selected action")
            return {"action": self._view(action), "attempt": self._view(pending), "waiting": False}
        if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence) or not candidates:
            raise AlignmentProtocolError("candidates must be a non-empty sequence")
        normalized = tuple(AlignmentCandidate.from_value(item) for item in candidates)
        if len({item.action_id for item in normalized}) != len(normalized):
            raise AlignmentProtocolError("candidates must have unique action ids")
        digest = self.state_digest()
        scored = []
        for candidate in normalized:
            score, factors = candidate.score(state_digest=digest, seed=seed, policy_version=policy_version)
            scored.append((score, factors["tie_break"], candidate.action_id, candidate))
        selected = max(scored, key=lambda item: (item[0], item[1], item[2]))[-1]
        action_payload = selected.to_payload(state_digest=digest, seed=seed, policy_version=policy_version)
        action_parents = (*selected.belief_refs, *selected.evidence_refs)
        attempt_id = "attempt-" + _digest({"action_id": selected.action_id, "digest": digest, "seed": seed})[:24]
        attempt_payload = {
            "attempt_id": attempt_id,
            "action_id": selected.action_id,
            "status": "pending",
            "idempotency_key": _digest({"digest": digest, "policy_version": policy_version, "seed": seed}),
            "state_digest": digest,
            "outcome": None,
        }
        existing_action = self._latest_one(ALIGNMENT_ACTION_KIND, selected.action_id)
        if existing_action is not None and not _same_payload(existing_action, action_payload):
            raise AlignmentConflictError("selected action id conflicts with a different candidate")
        try:
            if existing_action is None:
                action, attempt = self.ledger.append_artifact_batch(
                    self.run_id,
                    (
                        (selected.action_id, ALIGNMENT_ACTION_KIND, action_payload, action_parents),
                        (
                            attempt_id,
                            ALIGNMENT_ATTEMPT_KIND,
                            attempt_payload,
                            (ArtifactRef(self.run_id, selected.action_id, 1),),
                        ),
                    ),
                    expected_revision=self.ledger.get_revision(self.run_id),
                )
            else:
                attempt = self._append(
                    attempt_id,
                    ALIGNMENT_ATTEMPT_KIND,
                    attempt_payload,
                    parents=(ArtifactRef(existing_action.round_id, existing_action.id, existing_action.revision),),
                )
                action = existing_action
        except LedgerConflictError as error:
            raise AlignmentConflictError("stale_revision") from error
        return {"action": self._view(action), "attempt": self._view(attempt), "waiting": False}

    def respond(
        self,
        *,
        response_id: str,
        action_id: str,
        attempt_id: str,
        outcome: str,
        evidence_refs: Sequence[str] = (),
        response_digest: str | None = None,
    ) -> dict[str, Any]:
        validate_identifier(response_id, "response_id")
        validate_identifier(action_id, "action_id")
        validate_identifier(attempt_id, "attempt_id")
        if outcome not in {
            "answered",
            "supported",
            "refuted",
            "not_enough_information",
            "unknown",
            "accepted",
            "rejected",
        }:
            raise AlignmentProtocolError("response outcome is unsupported")
        pending = self._pending_attempt()
        existing_response = self._latest_one(ALIGNMENT_RESPONSE_KIND, response_id)
        evidence = _strings(evidence_refs, "evidence_refs")
        payload = {
            "response_id": response_id,
            "action_id": action_id,
            "attempt_id": attempt_id,
            "outcome": outcome,
            "evidence_refs": list(evidence),
            "response_digest": response_digest
            or _digest(
                {"action_id": action_id, "attempt_id": attempt_id, "outcome": outcome, "evidence_refs": evidence}
            ),
        }
        if existing_response is not None:
            if not _same_payload(existing_response, payload):
                raise AlignmentConflictError(f"response id payload conflict: {response_id}")
            latest_attempt = self._latest_one(ALIGNMENT_ATTEMPT_KIND, attempt_id)
            if latest_attempt is None:
                raise AlignmentConflictError("response has no attempt")
            return {"response": self._view(existing_response), "attempt": self._view(latest_attempt)}
        if pending is None:
            raise AlignmentConflictError("no pending action accepts a response")
        pending_payload = _payload(pending)
        if pending.id != attempt_id or pending_payload["action_id"] != action_id:
            raise AlignmentConflictError("response must bind to the current pending action")
        updated_attempt = {
            **pending_payload,
            "status": "unknown" if outcome == "unknown" else "consumed",
            "outcome": outcome,
            "response_ref": ArtifactRef(self.run_id, response_id, 1).to_dict(),
        }
        try:
            response, attempt = self.ledger.append_artifact_batch(
                self.run_id,
                (
                    (
                        response_id,
                        ALIGNMENT_RESPONSE_KIND,
                        payload,
                        (ArtifactRef(pending.round_id, pending.id, pending.revision),),
                    ),
                    (
                        attempt_id,
                        ALIGNMENT_ATTEMPT_KIND,
                        updated_attempt,
                        (
                            ArtifactRef(pending.round_id, pending.id, pending.revision),
                            ArtifactRef(self.run_id, response_id, 1),
                        ),
                    ),
                ),
                expected_revision=self.ledger.get_revision(self.run_id),
            )
        except LedgerConflictError as error:
            raise AlignmentConflictError("stale_revision") from error
        return {"response": self._view(response), "attempt": self._view(attempt)}

    def message(
        self,
        *,
        mirror: str,
        evidence_refs: Sequence[str],
        consequence: str,
        prompt: str | Sequence[str] | None,
        action_id: str | None = None,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        pending = self._pending_attempt()
        if pending is None:
            raise AlignmentMessageError("a message requires a pending alignment action")
        pending_payload = _payload(pending)
        selected_action_id = action_id or str(pending_payload["action_id"])
        if selected_action_id != pending_payload["action_id"]:
            raise AlignmentMessageError("message must bind to the current pending action")
        if isinstance(prompt, Sequence) and not isinstance(prompt, str):
            values = _strings(prompt, "prompt")
            if len(values) > 1:
                raise AlignmentMessageError("message may contain at most one open prompt")
            prompt_value = values[0] if values else None
        elif prompt is None:
            prompt_value = None
        else:
            prompt_value = _text(prompt, "prompt")
        mirror_value = _text(mirror, "mirror")
        consequence_value = _text(consequence, "consequence")
        references = _strings(evidence_refs, "evidence_refs")
        if len(mirror_value) > 240:
            raise AlignmentMessageError("mirror exceeds 240 characters")
        if prompt_value is not None and len(prompt_value) > 400:
            raise AlignmentMessageError("prompt exceeds 400 characters")
        if len(consequence_value) > 240:
            raise AlignmentMessageError("consequence exceeds 240 characters")
        if len(references) > 8:
            raise AlignmentMessageError("evidence_refs must contain at most 8 references")
        action = self._latest_one(ALIGNMENT_ACTION_KIND, selected_action_id)
        if action is None:
            raise AlignmentMessageError("selected action does not exist")
        belief_digest = _digest(
            {
                "state_digest": self.state_digest(),
                "action_id": selected_action_id,
                "mirror": mirror_value,
                "consequence": consequence_value,
                "prompt": prompt_value,
            }
        )
        artifact_id = message_id or "message-" + belief_digest[:24]
        validate_identifier(artifact_id, "message_id")
        payload = {
            "message_id": artifact_id,
            "run_id": self.run_id,
            "belief_digest": belief_digest,
            "selected_action_id": selected_action_id,
            "mirror": mirror_value,
            "prompt": prompt_value,
            "evidence_refs": list(references),
            "consequence": consequence_value,
            "response_binding": {"expected_digest": belief_digest, "status": "pending"},
        }
        item = self._append(
            artifact_id,
            ALIGNMENT_MESSAGE_KIND,
            payload,
            parents=(
                ArtifactRef(action.round_id, action.id, action.revision),
                ArtifactRef(pending.round_id, pending.id, pending.revision),
            ),
        )
        return self._view(item)

    def readiness(self) -> dict[str, Any]:
        beliefs = self._latest(ALIGNMENT_BELIEF_KIND)
        by_field: dict[str, list[ArtifactRevision]] = {}
        for belief in beliefs:
            by_field.setdefault(str(_payload(belief)["field"]), []).append(belief)
        fields: dict[str, str] = {}
        refs: list[ArtifactRef] = []
        for field in REQUIRED_READINESS_FIELDS:
            values = by_field.get(field, [])
            if not values:
                fields[field] = "unknown"
                continue
            latest = max(values, key=lambda item: item.revision)
            payload = _payload(latest)
            if payload["human_only"] and payload["actor"] != "human":
                fields[field] = "fail"
            elif payload["status"] in {
                "supported",
                "accepted",
                "corroborated",
                "resolved",
            }:
                fields[field] = "pass"
                refs.append(ArtifactRef(latest.round_id, latest.id, latest.revision))
            else:
                fields[field] = "unknown"
        disagreements = [item for item in beliefs if _payload(item).get("disagreement") is not None]
        if any(_payload(item)["disagreement"] == "not_enough_information" for item in disagreements):
            fields["disagreements"] = "unknown"
        elif disagreements:
            fields["disagreements"] = "pass"
            refs.extend(ArtifactRef(item.round_id, item.id, item.revision) for item in disagreements)
        else:
            fields["disagreements"] = "pass"
        ready = all(value == "pass" for value in fields.values())
        reasons = tuple(sorted(key for key, value in fields.items() if value != "pass"))
        digest = _digest({"fields": fields, "belief_refs": [reference.to_dict() for reference in refs]})
        return {
            "ready": ready,
            "fields": fields,
            "reasons": list(reasons),
            "digest": digest,
            "belief_refs": [reference.to_dict() for reference in refs],
        }

    def growth_aware_readiness(
        self,
        *,
        branches_before: Sequence[BranchState] = (),
        branches_after: Sequence[BranchState] = (),
        evidence_deltas: Mapping[str, Sequence[str]] | None = None,
    ) -> dict[str, Any]:
        """Opt-in readiness view: the canonical fields plus the growth delta.

        Callers that do not opt in keep the exact ``readiness()`` payload.
        """

        delta = compute_readiness_delta(branches_before, branches_after, evidence_deltas or {})
        result = self.readiness()
        result["growth_aware"] = True
        result["readiness_delta"] = delta.to_dict()
        result["branches"] = [branch.to_dict() for branch in branches_after]
        return result

    def confirm(
        self,
        confirmation: str,
        *,
        expected_digest: str,
        blueprint_target: ArtifactRevision | None = None,
    ) -> dict[str, Any]:
        statement = " ".join(_text(confirmation, "confirmation").split())
        if statement.casefold() in {"ok", "okay", "yes", "continue", "go ahead", "approved"}:
            raise AlignmentProtocolError("generic acknowledgement is not handoff confirmation")
        messages = self._latest(ALIGNMENT_MESSAGE_KIND)
        if not messages:
            raise AlignmentMessageError("no displayed alignment message can be confirmed")
        message = max(messages, key=lambda item: item.revision)
        message_payload = _payload(message)
        if expected_digest != message_payload["belief_digest"]:
            raise AlignmentMessageError("stale displayed alignment digest")
        current_digest = _digest(
            {
                "state_digest": self.state_digest(),
                "action_id": message_payload["selected_action_id"],
                "mirror": message_payload["mirror"],
                "consequence": message_payload["consequence"],
                "prompt": message_payload["prompt"],
            }
        )
        if current_digest != expected_digest:
            raise AlignmentMessageError("stale displayed alignment digest")
        readiness = self.readiness()
        if not readiness["ready"]:
            raise AlignmentReadinessError("alignment is not ready: " + ", ".join(readiness["reasons"]))
        action = self._latest_one(ALIGNMENT_ACTION_KIND, str(message_payload["selected_action_id"]))
        if action is None:
            raise AlignmentConflictError("displayed message has no selected action")
        readiness_id = "readiness-" + readiness["digest"][:24]
        handoff_id = "handoff-" + expected_digest[:24]
        readiness_payload = {
            "readiness_id": readiness_id,
            "run_id": self.run_id,
            "digest": readiness["digest"],
            "fields": readiness["fields"],
            "reasons": readiness["reasons"],
        }
        handoff_payload = {
            "handoff_id": handoff_id,
            "run_id": self.run_id,
            "status": "confirmed",
            "confirmed": True,
            "confirmation_digest": _digest(statement),
            "displayed_digest": expected_digest,
            "message_ref": ArtifactRef(message.round_id, message.id, message.revision).to_dict(),
            "action_ref": ArtifactRef(action.round_id, action.id, action.revision).to_dict(),
            "readiness_digest": readiness["digest"],
            "belief_refs": readiness["belief_refs"],
            "evidence_refs": list(message_payload.get("evidence_refs", ())),
        }
        if blueprint_target is not None:
            if not isinstance(blueprint_target, ArtifactRevision) or blueprint_target.round_id != self.run_id:
                raise AlignmentConflictError("blueprint_target must be an exact current run artifact")
            if blueprint_target.kind != "blueprint-target" or not self.ledger.is_latest_artifact(
                ArtifactRef(blueprint_target.round_id, blueprint_target.id, blueprint_target.revision)
            ):
                raise AlignmentConflictError("blueprint_target must be a current Blueprint Target revision")
            if not any(
                reference.id == handoff_id and reference.kind == ALIGNMENT_HANDOFF_KIND
                for reference in blueprint_target.parent_refs
            ):
                raise AlignmentConflictError("blueprint_target must retain the exact alignment handoff")
            handoff_payload["blueprint_target_ref"] = ArtifactRef(
                blueprint_target.round_id, blueprint_target.id, blueprint_target.revision
            ).to_dict()
        existing = self._latest_one(ALIGNMENT_HANDOFF_KIND, handoff_id)
        if existing is not None:
            if _same_payload(existing, handoff_payload):
                return self._view(existing)
            raise AlignmentConflictError("confirmation conflicts with the existing handoff")
        belief_refs = tuple(_reference(item, "belief_refs") for item in readiness["belief_refs"])
        try:
            _, handoff = self.ledger.append_artifact_batch(
                self.run_id,
                (
                    (readiness_id, ALIGNMENT_READINESS_KIND, readiness_payload, belief_refs),
                    (
                        handoff_id,
                        ALIGNMENT_HANDOFF_KIND,
                        handoff_payload,
                        (
                            ArtifactRef(message.round_id, message.id, message.revision),
                            ArtifactRef(action.round_id, action.id, action.revision),
                            ArtifactRef(self.run_id, readiness_id, 1),
                            *belief_refs,
                        ),
                    ),
                ),
                expected_revision=self.ledger.get_revision(self.run_id),
            )
        except LedgerConflictError as error:
            raise AlignmentConflictError("stale_revision") from error
        result = self._view(handoff)
        if self.coordinator is not None and blueprint_target is not None:
            state = self.coordinator.initialize(
                run_id=self.run_id,
                alignment_handoff=handoff,
                blueprint_target=blueprint_target,
                expected_revision=self.ledger.get_revision(self.run_id),
                idempotency_key=handoff_id,
            )
            result["coordinator_state"] = state.to_dict()
            result["coordinator_ref"] = ArtifactRef(state.round_id, state.id, state.revision).to_dict()
        return result

    def record_feedback(
        self,
        *,
        feedback_id: str,
        kind: str,
        message: str,
        materiality: str,
        affected_fields: Sequence[str],
        successor_run_id: str | None = None,
    ) -> dict[str, Any]:
        validate_identifier(feedback_id, "feedback_id")
        if materiality not in {"informational", "material", "terminal"}:
            raise AlignmentProtocolError("feedback materiality is unsupported")
        fields = _strings(affected_fields, "affected_fields", allow_empty=False)
        material = materiality in {"material", "terminal"} or kind in MATERIAL_FEEDBACK_KINDS
        classification = "successor_request" if material else "same_round_replan"
        payload = {
            "feedback_id": feedback_id,
            "run_id": self.run_id,
            "kind": _text(kind, "feedback kind"),
            "message": _text(message, "feedback message"),
            "materiality": materiality,
            "affected_fields": list(fields),
            "classification": classification,
            "successor_run_id": successor_run_id,
        }
        item = self._append(feedback_id, ALIGNMENT_FEEDBACK_KIND, payload)
        result = self._view(item)
        if self.coordinator is not None and successor_run_id is not None:
            expected_revision = self.ledger.get_revision(self.run_id)
            if material:
                result["coordinator_ref"] = self.coordinator.create_successor(
                    self.run_id,
                    successor_run_id=successor_run_id,
                    reason=payload["message"],
                    expected_revision=expected_revision,
                ).to_dict()
            else:
                result["coordinator_ref"] = self.coordinator.record_same_round_replan(
                    self.run_id,
                    reason=payload["message"],
                    expected_revision=expected_revision,
                    affected_refs=(ArtifactRef(item.round_id, item.id, item.revision),),
                ).to_dict()
        return result


AlignmentController = AlignmentProtocol


__all__ = [
    "ACTION_KINDS",
    "ALIGNMENT_ACTION_KIND",
    "ALIGNMENT_ATTEMPT_KIND",
    "ALIGNMENT_BELIEF_KIND",
    "ALIGNMENT_FEEDBACK_KIND",
    "ALIGNMENT_HANDOFF_KIND",
    "ALIGNMENT_MESSAGE_KIND",
    "ALIGNMENT_READINESS_KIND",
    "ALIGNMENT_RESPONSE_KIND",
    "AlignmentAction",
    "AlignmentCandidate",
    "AlignmentConflictError",
    "AlignmentController",
    "AlignmentMessageError",
    "AlignmentProtocol",
    "AlignmentProtocolError",
    "AlignmentReadinessError",
    "DISAGREEMENT_DISPOSITIONS",
    "REQUIRED_READINESS_FIELDS",
]
