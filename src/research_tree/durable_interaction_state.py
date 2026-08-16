"""Durable storage and recall for the storage-neutral #245 interaction reducer."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Callable, Sequence

from .domain import validate_identifier
from .interaction_state import (
    AgentState,
    InteractionEvent,
    InteractionReducer,
    InteractionState,
    PropositionStance,
    RelationshipState,
    RequesterState,
)
from .project_workspace import ProjectRunWorkspace, initialize_project_run


class DurableInteractionStateError(ValueError):
    """Raised when the durable interaction projection is unsafe or invalid."""


class StaleInteractionRevision(DurableInteractionStateError):
    """Raised when a worker submits against a non-current revision."""


@dataclass(frozen=True, slots=True)
class InteractionPaths:
    root: Path
    state: Path
    durable: Path
    episodes: Path
    checkpoints: Path
    recall_index: Path
    lock: Path


@dataclass(frozen=True, slots=True)
class PersistedInteractionState:
    revision: int
    state: InteractionState
    active_window: tuple[str, ...]
    durable: dict[str, Any]
    factual_beliefs: dict[str, str]
    pending_actions: dict[str, str]
    recovery_cursor: str | None
    state_integrity: str


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DurableInteractionStateError(f"invalid interaction projection: {path}") from error
    if not isinstance(value, dict):
        raise DurableInteractionStateError(f"interaction projection must be an object: {path}")
    return value


def _state_to_dict(state: InteractionState) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "requester": {
            "outcome": state.requester.outcome,
            "intended_use": state.requester.intended_use,
            "uncertainty_signals": list(state.requester.uncertainty_signals),
            "constraints": list(state.requester.constraints),
            "stances": {
                identifier: {
                    "proposition_id": stance.proposition_id,
                    "value": stance.value,
                    "evidence_anchor": stance.evidence_anchor,
                    "confidence": stance.confidence,
                    "expires_after_event": stance.expires_after_event,
                    "correction_path": stance.correction_path,
                }
                for identifier, stance in state.requester.stances.items()
            },
        },
        "agent": {
            "active_objective": state.agent.active_objective,
            "interpretation": state.agent.interpretation,
            "assumptions": dict(state.agent.assumptions),
            "evidence_readiness": state.agent.evidence_readiness,
            "uncertainty": state.agent.uncertainty,
            "error_debt": state.agent.error_debt,
            "plan_stability": state.agent.plan_stability,
            "pending_actions": list(state.agent.pending_actions),
            "pending_action_dependencies": {
                key: list(value) for key, value in state.agent.pending_action_dependencies.items()
            },
            "next_move": state.agent.next_move,
            "recovery_point": state.agent.recovery_point,
        },
        "relationship": {
            "authority": list(state.relationship.authority),
            "success_oracle": state.relationship.success_oracle,
            "unresolved_disagreements": list(state.relationship.unresolved_disagreements),
        },
        "foreground_thread_id": state.foreground_thread_id,
        "suspended_thread_ids": list(state.suspended_thread_ids),
        "superseded_ids": list(state.superseded_ids),
        "event_ids": list(state.event_ids),
    }


def _state_from_dict(payload: dict[str, Any]) -> InteractionState:
    try:
        requester = payload["requester"]
        agent = payload["agent"]
        relationship = payload["relationship"]
        stances = {
            identifier: PropositionStance(**stance) for identifier, stance in requester.get("stances", {}).items()
        }
        return InteractionState(
            run_id=payload["run_id"],
            requester=RequesterState(
                outcome=requester.get("outcome"),
                intended_use=requester.get("intended_use"),
                uncertainty_signals=tuple(requester.get("uncertainty_signals", ())),
                constraints=tuple(requester.get("constraints", ())),
                stances=stances,
            ),
            agent=AgentState(
                active_objective=agent.get("active_objective"),
                interpretation=agent.get("interpretation"),
                assumptions=agent.get("assumptions", {}),
                evidence_readiness=agent.get("evidence_readiness", "unknown"),
                uncertainty=agent.get("uncertainty", 0.0),
                error_debt=agent.get("error_debt", 0),
                plan_stability=agent.get("plan_stability", 1.0),
                pending_actions=tuple(agent.get("pending_actions", ())),
                pending_action_dependencies={
                    key: tuple(value) for key, value in agent.get("pending_action_dependencies", {}).items()
                },
                next_move=agent.get("next_move", "observe"),
                recovery_point=agent.get("recovery_point"),
            ),
            relationship=RelationshipState(
                authority=tuple(relationship.get("authority", ())),
                success_oracle=relationship.get("success_oracle"),
                unresolved_disagreements=tuple(relationship.get("unresolved_disagreements", ())),
            ),
            foreground_thread_id=payload.get("foreground_thread_id"),
            suspended_thread_ids=tuple(payload.get("suspended_thread_ids", ())),
            superseded_ids=tuple(payload.get("superseded_ids", ())),
            event_ids=tuple(payload.get("event_ids", ())),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DurableInteractionStateError("invalid persisted interaction state") from error


def _event_to_dict(event: InteractionEvent) -> dict[str, Any]:
    return {
        name: (list(value) if isinstance(value, tuple) else value)
        for name, value in ((field, getattr(event, field)) for field in event.__dataclass_fields__)
    }


class DurableInteractionController:
    """Single-writer, revisioned controller bound to a #240 project workspace."""

    def __init__(self, workspace: ProjectRunWorkspace, *, window_size: int = 10) -> None:
        if window_size < 1:
            raise DurableInteractionStateError("window_size must be positive")
        root = workspace.project_root / "interaction"
        self.workspace = workspace
        self.window_size = window_size
        self.paths = InteractionPaths(
            root,
            root / "state.yaml",
            root / "durable.yaml",
            root / "episodes",
            root / "checkpoints",
            root / "recall-index",
            root / ".writer.lock",
        )
        self.reducer = InteractionReducer()

    @classmethod
    def initialize(
        cls, repository: Path, *, project_id: str, run_id: str, window_size: int = 10, host: str = "codex"
    ) -> "DurableInteractionController":
        controller = cls(
            initialize_project_run(repository, project_id=project_id, run_id=run_id, host=host), window_size=window_size
        )
        controller.paths.episodes.mkdir(parents=True, exist_ok=True)
        controller.paths.checkpoints.mkdir(parents=True, exist_ok=True)
        controller.paths.recall_index.mkdir(parents=True, exist_ok=True)
        if not controller.paths.state.exists():
            initial = PersistedInteractionState(
                0,
                InteractionState.initial(run_id),
                (),
                {"authority": [], "corrections": {}, "decisions": {}, "facts": {}},
                {},
                {},
                None,
                "healthy",
            )
            controller._publish(initial)
        return controller

    def _lock(self):
        import fcntl

        self.paths.root.mkdir(parents=True, exist_ok=True)
        handle = self.paths.lock.open("a+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def _unlock(self, handle: Any) -> None:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

    def load(self) -> PersistedInteractionState:
        state_payload = _read_object(self.paths.state)
        durable = _read_object(self.paths.durable) if self.paths.durable.exists() else state_payload.get("durable", {})
        if state_payload.get("durable_digest") != sha256(_json_bytes(durable)).hexdigest():
            embedded = state_payload.get("durable")
            if (
                not isinstance(embedded, dict)
                or state_payload.get("durable_digest") != sha256(_json_bytes(embedded)).hexdigest()
            ):
                raise DurableInteractionStateError("durable interaction digest mismatch")
            durable = embedded
            _atomic_write(self.paths.durable, durable)
        return PersistedInteractionState(
            revision=state_payload["revision"],
            state=_state_from_dict(state_payload["state"]),
            active_window=tuple(state_payload.get("active_window", ())),
            durable=durable,
            factual_beliefs=dict(state_payload.get("factual_beliefs", {})),
            pending_actions=dict(state_payload.get("pending_actions", {})),
            recovery_cursor=state_payload.get("recovery_cursor"),
            state_integrity=state_payload.get("state_integrity", "healthy"),
        )

    def _publish(self, current: PersistedInteractionState) -> None:
        durable = dict(current.durable)
        _atomic_write(self.paths.durable, durable)
        payload = {
            "schema": 1,
            "revision": current.revision,
            "state": _state_to_dict(current.state),
            "active_window": list(current.active_window),
            "durable": durable,
            "durable_digest": sha256(_json_bytes(durable)).hexdigest(),
            "factual_beliefs": current.factual_beliefs,
            "pending_actions": current.pending_actions,
            "recovery_cursor": current.recovery_cursor,
            "state_integrity": current.state_integrity,
        }
        _atomic_write(self.paths.state, payload)

    def _change(
        self, expected_revision: int | None, mutate: Callable[[PersistedInteractionState], PersistedInteractionState]
    ) -> PersistedInteractionState:
        handle = self._lock()
        try:
            prior = self.load()
            if expected_revision is not None and expected_revision != prior.revision:
                raise StaleInteractionRevision(
                    f"expected revision {expected_revision}, current revision is {prior.revision}"
                )
            successor = mutate(prior)
            successor = replace(successor, revision=prior.revision + 1)
            self._publish(successor)
            return successor
        finally:
            self._unlock(handle)

    def _episode(self, revision: int, event_id: str, payload: dict[str, Any]) -> None:
        _atomic_write(self.paths.episodes / f"{revision:020d}-{event_id}.yaml", payload)

    @staticmethod
    def _promote(durable: dict[str, Any], state: InteractionState, event: InteractionEvent) -> dict[str, Any]:
        result = json.loads(json.dumps(durable))
        result["authority"] = list(state.relationship.authority)
        if event.kind == "stance" and event.stance_value == "correct":
            result.setdefault("corrections", {})[event.proposition_id] = {
                "value": "correct",
                "source_turn": event.event_id,
            }
        if event.kind == "correction":
            result.setdefault("corrections", {})[event.target_id] = {
                "value": event.replacement,
                "source_turn": event.event_id,
            }
        if event.kind == "delivery":
            result.setdefault("decisions", {})[event.delivery_id] = {"source_turn": event.event_id}
        return result

    def submit(self, event: InteractionEvent, *, expected_revision: int) -> PersistedInteractionState:
        if not isinstance(event, InteractionEvent):
            raise DurableInteractionStateError("controller accepts only reducer events")

        def mutate(prior: PersistedInteractionState) -> PersistedInteractionState:
            reduction = self.reducer.reduce(prior.state, event)
            window = (*prior.active_window, event.event_id)[-self.window_size :]
            successor = replace(
                prior,
                state=reduction.state,
                active_window=window,
                durable=self._promote(prior.durable, reduction.state, event),
            )
            self._episode(
                prior.revision + 1,
                event.event_id,
                {
                    "schema": 1,
                    "event_id": event.event_id,
                    "event": _event_to_dict(event),
                    "superseded": list(reduction.state.superseded_ids),
                },
            )
            return successor

        return self._change(expected_revision, mutate)

    def recall(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        terms = set(query.lower().split())
        current = self.load()
        candidates: list[tuple[int, dict[str, Any]]] = []
        for path in self.paths.episodes.glob("*.yaml"):
            episode = _read_object(path)
            event = episode.get("event", {})
            event_id = episode.get("event_id")
            if event_id in current.state.superseded_ids or event.get("assumption_id") in current.state.superseded_ids:
                continue
            text = " ".join(
                str(event.get(key) or "")
                for key in ("text", "outcome", "statement", "replacement", "target_id", "proposition_id")
            )
            score = len(terms.intersection(text.lower().split())) * 10
            if event_id in current.active_window:
                score += 3
            if event.get("kind") in {"correction", "stance"}:
                score += 4
            if score:
                candidates.append((score, {"event_id": event_id, "event": event, "score": score}))
        return [item for _score, item in sorted(candidates, key=lambda item: (-item[0], item[1]["event_id"]))[:limit]]

    def record_action_started(self, action_id: str, *, expected_revision: int) -> PersistedInteractionState:
        return self._change(
            expected_revision,
            lambda prior: replace(prior, pending_actions={**prior.pending_actions, action_id: "started"}),
        )

    def checkpoint(self, *, expected_revision: int | None = None) -> str:
        handle = self._lock()
        try:
            current = self.load()
            if expected_revision is not None and expected_revision != current.revision:
                raise StaleInteractionRevision(
                    f"expected revision {expected_revision}, current revision is {current.revision}"
                )
            payload = {
                "schema": 1,
                "revision": current.revision,
                "state": _state_to_dict(current.state),
                "active_window": list(current.active_window),
                "pending_actions": current.pending_actions,
                "durable_digest": sha256(_json_bytes(current.durable)).hexdigest(),
            }
            digest = sha256(_json_bytes(payload)).hexdigest()
            _atomic_write(
                self.paths.checkpoints / f"{current.revision:020d}-{digest[:12]}.yaml", {**payload, "digest": digest}
            )
            self._publish(replace(current, recovery_cursor=digest))
            return digest
        finally:
            self._unlock(handle)

    def recover(self, checkpoint_digest: str | None = None) -> PersistedInteractionState:
        paths = sorted(self.paths.checkpoints.glob("*.yaml"))
        if not paths:
            raise DurableInteractionStateError("no interaction checkpoint exists")
        selected = next(
            (
                path
                for path in reversed(paths)
                if checkpoint_digest is None or _read_object(path).get("digest") == checkpoint_digest
            ),
            None,
        )
        if selected is None:
            raise DurableInteractionStateError("requested interaction checkpoint does not exist")
        checkpoint = _read_object(selected)
        digest = checkpoint.pop("digest", None)
        if digest != sha256(_json_bytes(checkpoint)).hexdigest():
            raise DurableInteractionStateError("interaction checkpoint digest mismatch")

        def mutate(prior: PersistedInteractionState) -> PersistedInteractionState:
            pending = {
                key: ("unknown" if value == "started" else value)
                for key, value in checkpoint.get("pending_actions", {}).items()
            }
            state = _state_from_dict(checkpoint["state"])
            if "unknown" in pending.values():
                state = replace(state, agent=replace(state.agent, next_move="repair"))
            return replace(
                prior,
                state=state,
                active_window=tuple(checkpoint.get("active_window", ())),
                pending_actions=pending,
                recovery_cursor=digest,
            )

        return self._change(None, mutate)

    def propose_evidence(
        self, claim_id: str, statement: str, *, admitted: bool, expected_revision: int
    ) -> PersistedInteractionState:
        def mutate(prior: PersistedInteractionState) -> PersistedInteractionState:
            beliefs = dict(prior.factual_beliefs)
            if admitted:
                beliefs[claim_id] = statement
            self._episode(
                prior.revision + 1,
                f"evidence-{claim_id}",
                {
                    "schema": 1,
                    "event_id": f"evidence-{claim_id}",
                    "kind": "evidence",
                    "admitted": admitted,
                    "claim_id": claim_id,
                },
            )
            return replace(prior, factual_beliefs=beliefs)

        return self._change(expected_revision, mutate)

    def contest_evidence(self, claim_id: str, *, expected_revision: int) -> PersistedInteractionState:
        return self.contest_evidence_set((claim_id,), expected_revision=expected_revision)

    def contest_evidence_set(self, claim_ids: Sequence[str], *, expected_revision: int) -> PersistedInteractionState:
        identifiers = tuple(dict.fromkeys(validate_identifier(claim_id, "claim_id") for claim_id in claim_ids))
        if not identifiers:
            raise DurableInteractionStateError("contested evidence requires at least one claim")

        def mutate(prior: PersistedInteractionState) -> PersistedInteractionState:
            state = prior.state
            for index, claim_id in enumerate(identifiers, start=1):
                state = self.reducer.reduce(
                    state,
                    InteractionEvent.correction(
                        event_id=f"contest-{claim_id}-{prior.revision + 1}-{index}",
                        target_id=claim_id,
                        replacement="Canonical evidence is contested pending independent resolution.",
                    ),
                ).state
            remaining = {
                action: status
                for action, status in prior.pending_actions.items()
                if action in state.agent.pending_actions
            }
            self._episode(
                prior.revision + 1,
                "contest-" + "-".join(identifiers),
                {
                    "schema": 1,
                    "event_id": f"contest-{prior.revision + 1}",
                    "kind": "contradiction",
                    "claim_ids": list(identifiers),
                },
            )
            return replace(
                prior,
                state=state,
                factual_beliefs={key: value for key, value in prior.factual_beliefs.items() if key not in identifiers},
                pending_actions=remaining,
            )

        return self._change(expected_revision, mutate)

    def consume_lifecycle_event(self, event: str) -> PersistedInteractionState:
        if event == "PreCompact":
            self.checkpoint()
            return self.load()
        if event in {"SessionStart", "PostCompact", "SessionEnd", "Stop", "delivery_feedback"}:
            return self._change(None, lambda prior: prior)
        return self._change(None, lambda prior: replace(prior, state_integrity="degraded"))

    def consume_recorded_lifecycle_event(self, record: dict[str, Any]) -> PersistedInteractionState:
        if not isinstance(record, dict):
            raise DurableInteractionStateError("lifecycle record must be an object")
        if record.get("project_id") != self.workspace.project_id or record.get("run_id") != self.workspace.run_id:
            raise DurableInteractionStateError("lifecycle record is bound to another project run")
        event = record.get("event")
        if not isinstance(event, str):
            raise DurableInteractionStateError("lifecycle record is missing its event")
        return self.consume_lifecycle_event(event)


__all__ = [
    "DurableInteractionController",
    "DurableInteractionStateError",
    "InteractionPaths",
    "PersistedInteractionState",
    "StaleInteractionRevision",
]
