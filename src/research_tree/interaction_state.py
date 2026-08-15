"""Deterministic, always-on interaction-state reduction.

The reducer is deliberately storage-neutral.  It turns one authoritative event
and its predecessor state into the next state; #246 owns cross-session storage
and lifecycle-hook delivery of those events.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping, Sequence

from .domain import RuntimeStoreError, validate_identifier


InteractionDispositionKind = Literal[
    "execute", "decompose", "reconnaissance", "request_decision", "repair", "teach", "blocked", "observe"
]
StanceValue = Literal["agree", "reject", "uncertain", "correct"]


class InteractionStateError(RuntimeStoreError):
    """Raised when a state event cannot safely be reduced."""


def _text(value: str | None, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InteractionStateError(f"{label} must be a non-empty string")
    return value.strip()


def _strings(value: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise InteractionStateError(f"{label} must be a sequence")
    values = tuple(_text(item, f"{label} item") for item in value)
    if len(set(values)) != len(values):
        raise InteractionStateError(f"{label} must not contain duplicates")
    return values


@dataclass(frozen=True, slots=True)
class PropositionStance:
    proposition_id: str
    value: StanceValue
    evidence_anchor: str
    confidence: float = 1.0
    expires_after_event: str | None = None
    correction_path: str = "user_message"

    def __post_init__(self) -> None:
        validate_identifier(self.proposition_id, "proposition_id")
        if self.value not in {"agree", "reject", "uncertain", "correct"}:
            raise InteractionStateError("unsupported proposition stance")
        _text(self.evidence_anchor, "evidence_anchor")
        if not 0.0 <= self.confidence <= 1.0:
            raise InteractionStateError("stance confidence must be between 0 and 1")
        _text(self.correction_path, "correction_path")


@dataclass(frozen=True, slots=True)
class RequesterState:
    outcome: str | None = None
    intended_use: str | None = None
    uncertainty_signals: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    stances: Mapping[str, PropositionStance] | None = None

    def __post_init__(self) -> None:
        if self.outcome is not None:
            _text(self.outcome, "outcome")
        if self.intended_use is not None:
            _text(self.intended_use, "intended_use")
        object.__setattr__(self, "uncertainty_signals", _strings(self.uncertainty_signals, "uncertainty_signals"))
        object.__setattr__(self, "constraints", _strings(self.constraints, "constraints"))
        stances = dict(self.stances or {})
        for proposition_id, stance in stances.items():
            validate_identifier(proposition_id, "proposition_id")
            if not isinstance(stance, PropositionStance) or stance.proposition_id != proposition_id:
                raise InteractionStateError("stances must be keyed by their proposition id")
        object.__setattr__(self, "stances", stances)


@dataclass(frozen=True, slots=True)
class AgentState:
    active_objective: str | None = None
    interpretation: str | None = None
    assumptions: Mapping[str, str] | None = None
    evidence_readiness: str = "unknown"
    uncertainty: float = 0.0
    error_debt: int = 0
    plan_stability: float = 1.0
    pending_actions: tuple[str, ...] = ()
    pending_action_dependencies: Mapping[str, tuple[str, ...]] | None = None
    next_move: str = "observe"
    recovery_point: str | None = None

    def __post_init__(self) -> None:
        if self.active_objective is not None:
            _text(self.active_objective, "active_objective")
        if self.interpretation is not None:
            _text(self.interpretation, "interpretation")
        assumptions = dict(self.assumptions or {})
        for assumption_id, statement in assumptions.items():
            validate_identifier(assumption_id, "assumption_id")
            _text(statement, "assumption statement")
        object.__setattr__(self, "assumptions", assumptions)
        if not 0.0 <= self.uncertainty <= 1.0 or not 0.0 <= self.plan_stability <= 1.0:
            raise InteractionStateError("agent uncertainty and plan stability must be between 0 and 1")
        if self.error_debt < 0:
            raise InteractionStateError("error_debt must not be negative")
        object.__setattr__(self, "pending_actions", _strings(self.pending_actions, "pending_actions"))
        dependencies = {action: tuple(targets) for action, targets in (self.pending_action_dependencies or {}).items()}
        if set(dependencies).difference(self.pending_actions):
            raise InteractionStateError("pending action dependencies must reference pending actions")
        for action, targets in dependencies.items():
            _text(action, "pending action")
            for target in _strings(targets, "pending action dependencies"):
                validate_identifier(target, "dependency target")
        object.__setattr__(self, "pending_action_dependencies", dependencies)
        _text(self.next_move, "next_move")


@dataclass(frozen=True, slots=True)
class RelationshipState:
    authority: tuple[str, ...] = ()
    success_oracle: str | None = None
    unresolved_disagreements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "authority", _strings(self.authority, "authority"))
        object.__setattr__(
            self, "unresolved_disagreements", _strings(self.unresolved_disagreements, "unresolved_disagreements")
        )
        if self.success_oracle is not None:
            _text(self.success_oracle, "success_oracle")


@dataclass(frozen=True, slots=True)
class InteractionState:
    run_id: str
    requester: RequesterState
    agent: AgentState
    relationship: RelationshipState
    foreground_thread_id: str | None = None
    suspended_thread_ids: tuple[str, ...] = ()
    superseded_ids: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()

    @classmethod
    def initial(cls, run_id: str) -> "InteractionState":
        return cls(
            run_id=validate_identifier(run_id, "run_id"),
            requester=RequesterState(),
            agent=AgentState(),
            relationship=RelationshipState(),
        )

    def __post_init__(self) -> None:
        validate_identifier(self.run_id, "run_id")
        if self.foreground_thread_id is not None:
            validate_identifier(self.foreground_thread_id, "foreground_thread_id")
        object.__setattr__(self, "suspended_thread_ids", _strings(self.suspended_thread_ids, "suspended_thread_ids"))
        object.__setattr__(self, "superseded_ids", _strings(self.superseded_ids, "superseded_ids"))
        object.__setattr__(self, "event_ids", _strings(self.event_ids, "event_ids"))
        if self.foreground_thread_id in self.suspended_thread_ids:
            raise InteractionStateError("foreground thread cannot also be suspended")


@dataclass(frozen=True, slots=True)
class InteractionDisposition:
    kind: InteractionDispositionKind
    question: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {
            "execute",
            "decompose",
            "reconnaissance",
            "request_decision",
            "repair",
            "teach",
            "blocked",
            "observe",
        }:
            raise InteractionStateError("unsupported interaction disposition")
        if self.question is not None:
            _text(self.question, "question")


@dataclass(frozen=True, slots=True)
class InteractionReduction:
    state: InteractionState
    disposition: InteractionDisposition


@dataclass(frozen=True, slots=True)
class InteractionEvent:
    event_id: str
    kind: str
    text: str | None = None
    outcome: str | None = None
    consequence: str = "low"
    reversible: bool = False
    authority: tuple[str, ...] = ()
    side_thread: bool = False
    proposition_id: str | None = None
    stance_value: StanceValue | None = None
    evidence_anchor: str | None = None
    assumption_id: str | None = None
    statement: str | None = None
    pending_actions: tuple[str, ...] = ()
    target_id: str | None = None
    replacement: str | None = None
    delivery_id: str | None = None
    inferred_authority: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_identifier(self.event_id, "event_id")
        if self.kind not in {
            "user_message",
            "stance",
            "agent_assumption",
            "correction",
            "continue",
            "delivery",
            "reconnaissance",
        }:
            raise InteractionStateError("unsupported interaction event kind")
        if self.consequence not in {"low", "high"}:
            raise InteractionStateError("consequence must be low or high")
        object.__setattr__(self, "authority", _strings(self.authority, "authority"))
        object.__setattr__(self, "pending_actions", _strings(self.pending_actions, "pending_actions"))
        object.__setattr__(self, "inferred_authority", _strings(self.inferred_authority, "inferred_authority"))

    @classmethod
    def user_message(
        cls,
        *,
        event_id: str,
        text: str,
        outcome: str | None,
        consequence: str,
        reversible: bool = False,
        authority: Sequence[str] = (),
        side_thread: bool = False,
    ) -> "InteractionEvent":
        return cls(
            event_id=event_id,
            kind="user_message",
            text=text,
            outcome=outcome,
            consequence=consequence,
            reversible=reversible,
            authority=tuple(authority),
            side_thread=side_thread,
        )

    @classmethod
    def stance(
        cls, *, event_id: str, proposition_id: str, stance: StanceValue, evidence_anchor: str
    ) -> "InteractionEvent":
        return cls(
            event_id=event_id,
            kind="stance",
            proposition_id=proposition_id,
            stance_value=stance,
            evidence_anchor=evidence_anchor,
        )

    @classmethod
    def agent_assumption(
        cls, *, event_id: str, assumption_id: str, statement: str, pending_actions: Sequence[str] = ()
    ) -> "InteractionEvent":
        return cls(
            event_id=event_id,
            kind="agent_assumption",
            assumption_id=assumption_id,
            statement=statement,
            pending_actions=tuple(pending_actions),
        )

    @classmethod
    def correction(cls, *, event_id: str, target_id: str, replacement: str) -> "InteractionEvent":
        return cls(event_id=event_id, kind="correction", target_id=target_id, replacement=replacement)

    @classmethod
    def continue_message(cls, *, event_id: str) -> "InteractionEvent":
        return cls(event_id=event_id, kind="continue")

    @classmethod
    def delivery(cls, *, event_id: str, delivery_id: str) -> "InteractionEvent":
        return cls(event_id=event_id, kind="delivery", delivery_id=delivery_id)

    @classmethod
    def reconnaissance(
        cls, *, event_id: str, summary: str, inferred_authority: Sequence[str] = ()
    ) -> "InteractionEvent":
        return cls(event_id=event_id, kind="reconnaissance", text=summary, inferred_authority=tuple(inferred_authority))


class InteractionReducer:
    """Reduce semantic interaction events without granting inferred authority."""

    def reduce(self, prior: InteractionState, event: InteractionEvent) -> InteractionReduction:
        if not isinstance(prior, InteractionState) or not isinstance(event, InteractionEvent):
            raise InteractionStateError("reducer requires interaction state and event")
        if event.event_id in prior.event_ids:
            return InteractionReduction(prior, InteractionDisposition("observe"))
        state = replace(prior, event_ids=(*prior.event_ids, event.event_id))
        if event.kind == "user_message":
            return self._user_message(state, event)
        if event.kind == "stance":
            return self._stance(state, event)
        if event.kind == "agent_assumption":
            return self._assumption(state, event)
        if event.kind == "correction":
            return self._correction(state, event)
        if event.kind == "continue":
            return self._continue(state)
        if event.kind == "delivery":
            return self._delivery(state, event)
        return InteractionReduction(state, InteractionDisposition("observe"))

    def _user_message(self, state: InteractionState, event: InteractionEvent) -> InteractionReduction:
        text = _text(event.text, "user message")
        outcome = event.outcome.strip() if isinstance(event.outcome, str) and event.outcome.strip() else None
        if outcome is None and text.lower().startswith(("what is the current status", "status?", "status update")):
            return InteractionReduction(state, InteractionDisposition("observe"))
        thread_id = f"thread-{event.event_id}"
        if event.side_thread and state.foreground_thread_id is not None:
            suspended = (*state.suspended_thread_ids, thread_id)
            return InteractionReduction(
                replace(state, suspended_thread_ids=suspended), InteractionDisposition("observe")
            )
        suspended = state.suspended_thread_ids
        if state.foreground_thread_id is not None and state.foreground_thread_id != thread_id:
            suspended = (*suspended, state.foreground_thread_id)
        requester = replace(state.requester, outcome=outcome or state.requester.outcome)
        authority = tuple(sorted(set(state.relationship.authority).union(event.authority)))
        relationship = replace(state.relationship, authority=authority)
        if event.consequence == "high" and not event.reversible:
            missing_slots = self._missing_decision_slots(requester, relationship)
            requester = replace(
                requester,
                uncertainty_signals=tuple(
                    dict.fromkeys((*requester.uncertainty_signals, *(f"missing:{slot}" for slot in missing_slots)))
                ),
            )
            agent = replace(
                state.agent,
                active_objective=outcome,
                interpretation=text,
                uncertainty=1.0,
                next_move="request_decision",
            )
            return InteractionReduction(
                replace(
                    state,
                    requester=requester,
                    agent=agent,
                    relationship=relationship,
                    foreground_thread_id=thread_id,
                    suspended_thread_ids=suspended,
                ),
                InteractionDisposition("request_decision", self._decision_question(outcome or text, missing_slots)),
            )
        action = outcome or text
        agent = replace(
            state.agent,
            active_objective=action,
            interpretation=text,
            pending_actions=(action,),
            uncertainty=0.2,
            next_move="execute",
        )
        return InteractionReduction(
            replace(
                state,
                requester=requester,
                agent=agent,
                relationship=relationship,
                foreground_thread_id=thread_id,
                suspended_thread_ids=suspended,
            ),
            InteractionDisposition("execute"),
        )

    @staticmethod
    def _missing_decision_slots(requester: RequesterState, relationship: RelationshipState) -> tuple[str, ...]:
        slots: list[str] = []
        if requester.intended_use is None:
            slots.append("intended use")
        if not requester.constraints:
            slots.append("constraints")
        if not relationship.authority:
            slots.append("authority")
        return tuple(slots)

    @staticmethod
    def _decision_question(subject: str, missing_slots: Sequence[str]) -> str:
        slot_text = ", ".join(missing_slots) if missing_slots else "decision boundary"
        return f"Before proceeding with {subject!r}, what {slot_text} should govern it?"

    def _stance(self, state: InteractionState, event: InteractionEvent) -> InteractionReduction:
        proposition_id = validate_identifier(event.proposition_id, "proposition_id")
        if event.stance_value is None or event.evidence_anchor is None:
            raise InteractionStateError("stance requires value and evidence anchor")
        stances = dict(state.requester.stances)
        stances[proposition_id] = PropositionStance(proposition_id, event.stance_value, event.evidence_anchor)
        return InteractionReduction(
            replace(state, requester=replace(state.requester, stances=stances)), InteractionDisposition("observe")
        )

    def _assumption(self, state: InteractionState, event: InteractionEvent) -> InteractionReduction:
        assumption_id = validate_identifier(event.assumption_id, "assumption_id")
        statement = _text(event.statement, "assumption statement")
        assumptions = dict(state.agent.assumptions)
        assumptions[assumption_id] = statement
        pending_actions = tuple(dict.fromkeys((*state.agent.pending_actions, *event.pending_actions)))
        dependencies = dict(state.agent.pending_action_dependencies)
        dependencies.update({action: (assumption_id,) for action in event.pending_actions})
        return InteractionReduction(
            replace(
                state,
                agent=replace(
                    state.agent,
                    assumptions=assumptions,
                    pending_actions=pending_actions,
                    pending_action_dependencies=dependencies,
                ),
            ),
            InteractionDisposition("observe"),
        )

    def _correction(self, state: InteractionState, event: InteractionEvent) -> InteractionReduction:
        target_id = validate_identifier(event.target_id, "target_id")
        replacement = _text(event.replacement, "correction replacement")
        assumptions = dict(state.agent.assumptions)
        assumptions.pop(target_id, None)
        invalidated = {target_id}
        dependencies = dict(state.agent.pending_action_dependencies)
        while True:
            newly_invalidated = {
                action
                for action, dependency_targets in dependencies.items()
                if action not in invalidated and invalidated.intersection(dependency_targets)
            }
            if not newly_invalidated:
                break
            invalidated.update(newly_invalidated)
        remaining_actions = tuple(action for action in state.agent.pending_actions if action not in invalidated)
        remaining_dependencies = {
            action: dependency_targets
            for action, dependency_targets in dependencies.items()
            if action in remaining_actions
        }
        stances = dict(state.requester.stances)
        stances[target_id] = PropositionStance(
            target_id, "correct", event.event_id, correction_path="explicit_correction"
        )
        agent = replace(
            state.agent,
            assumptions=assumptions,
            pending_actions=remaining_actions,
            pending_action_dependencies=remaining_dependencies,
            error_debt=state.agent.error_debt + 1,
            plan_stability=max(0.0, state.agent.plan_stability - 0.35),
            interpretation=replacement,
            next_move="repair",
        )
        relationship = replace(
            state.relationship,
            unresolved_disagreements=tuple(dict.fromkeys((*state.relationship.unresolved_disagreements, target_id))),
        )
        return InteractionReduction(
            replace(
                state,
                requester=replace(state.requester, stances=stances),
                agent=agent,
                relationship=relationship,
                superseded_ids=tuple(dict.fromkeys((*state.superseded_ids, target_id))),
            ),
            InteractionDisposition("repair"),
        )

    def _continue(self, state: InteractionState) -> InteractionReduction:
        if state.foreground_thread_id is None and state.suspended_thread_ids:
            foreground, *suspended = state.suspended_thread_ids
            return InteractionReduction(
                replace(state, foreground_thread_id=foreground, suspended_thread_ids=tuple(suspended)),
                InteractionDisposition("observe"),
            )
        if state.foreground_thread_id is not None and state.suspended_thread_ids:
            resumed = state.suspended_thread_ids[0]
            suspended = (*state.suspended_thread_ids[1:], resumed)
            return InteractionReduction(
                replace(state, suspended_thread_ids=suspended), InteractionDisposition("observe")
            )
        return InteractionReduction(state, InteractionDisposition("observe"))

    def _delivery(self, state: InteractionState, event: InteractionEvent) -> InteractionReduction:
        delivery_id = validate_identifier(event.delivery_id, "delivery_id")
        return InteractionReduction(
            replace(
                state,
                agent=replace(state.agent, pending_actions=(), next_move="await_feedback"),
                superseded_ids=tuple(dict.fromkeys((*state.superseded_ids, delivery_id))),
            ),
            InteractionDisposition("observe"),
        )


__all__ = [
    "AgentState",
    "InteractionDisposition",
    "InteractionEvent",
    "InteractionReducer",
    "InteractionReduction",
    "InteractionState",
    "InteractionStateError",
    "PropositionStance",
    "RelationshipState",
    "RequesterState",
]
