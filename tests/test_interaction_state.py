from __future__ import annotations

import pytest


def _state():
    from research_tree.interaction_state import InteractionState

    return InteractionState.initial("run-interaction")


def test_vague_high_consequence_request_requests_one_decision_before_execution() -> None:
    from research_tree.interaction_state import InteractionEvent, InteractionReducer

    result = InteractionReducer().reduce(
        _state(),
        InteractionEvent.user_message(
            event_id="request-crawler",
            text="Build a distributed crawler.",
            outcome="distributed crawler",
            consequence="high",
        ),
    )

    assert result.state.foreground_thread_id == "thread-request-crawler"
    assert result.state.requester.outcome == "distributed crawler"
    assert result.disposition.kind == "request_decision"
    assert result.disposition.question == (
        "Before proceeding with 'distributed crawler', what intended use, constraints, authority should govern it?"
    )
    assert result.state.agent.pending_actions == ()


def test_high_consequence_request_derives_its_question_from_missing_slots() -> None:
    from research_tree.interaction_state import InteractionEvent, InteractionReducer

    result = InteractionReducer().reduce(
        _state(),
        InteractionEvent.user_message(
            event_id="deploy-production",
            text="Deploy the payment service to production.",
            outcome="deploy payment service",
            consequence="high",
        ),
    )

    assert result.disposition.kind == "request_decision"
    assert result.disposition.question == (
        "Before proceeding with 'deploy payment service', what intended use, constraints, authority should govern it?"
    )
    assert "crawler" not in result.disposition.question.lower()


def test_clear_reversible_request_can_execute_with_explicit_assumption() -> None:
    from research_tree.interaction_state import InteractionEvent, InteractionReducer

    result = InteractionReducer().reduce(
        _state(),
        InteractionEvent.user_message(
            event_id="format-readme",
            text="Format the README headings.",
            outcome="format README headings",
            consequence="low",
            reversible=True,
            authority=("repository_write",),
        ),
    )

    assert result.disposition.kind == "execute"
    assert result.state.agent.pending_actions == ("format README headings",)
    assert result.state.relationship.authority == ("repository_write",)


def test_stances_are_proposition_scoped_and_can_coexist() -> None:
    from research_tree.interaction_state import InteractionEvent, InteractionReducer

    reducer = InteractionReducer()
    state = _state()
    for event_id, proposition_id, stance in (
        ("agree-a", "claim-a", "agree"),
        ("reject-b", "claim-b", "reject"),
        ("uncertain-c", "claim-c", "uncertain"),
    ):
        state = reducer.reduce(
            state,
            InteractionEvent.stance(
                event_id=event_id,
                proposition_id=proposition_id,
                stance=stance,
                evidence_anchor="user-message",
            ),
        ).state

    assert state.requester.stances["claim-a"].value == "agree"
    assert state.requester.stances["claim-b"].value == "reject"
    assert state.requester.stances["claim-c"].value == "uncertain"


def test_correction_invalidates_dependent_pending_action_and_reduces_plan_stability() -> None:
    from research_tree.interaction_state import InteractionEvent, InteractionReducer

    reducer = InteractionReducer()
    initial = reducer.reduce(
        _state(),
        InteractionEvent.user_message(
            event_id="initial-plan",
            text="Use PostgreSQL for the prototype.",
            outcome="prototype with PostgreSQL",
            consequence="low",
            reversible=True,
            authority=("repository_write",),
        ),
    ).state
    with_assumption = reducer.reduce(
        initial,
        InteractionEvent.agent_assumption(
            event_id="database-assumption",
            assumption_id="database-choice",
            statement="PostgreSQL is the requested database.",
            pending_actions=("create PostgreSQL schema",),
        ),
    ).state

    result = reducer.reduce(
        with_assumption,
        InteractionEvent.correction(
            event_id="correct-database",
            target_id="database-choice",
            replacement="Use SQLite instead.",
        ),
    )

    assert "database-choice" in result.state.superseded_ids
    assert result.state.agent.pending_actions == ("prototype with PostgreSQL",)
    assert result.state.agent.plan_stability < with_assumption.agent.plan_stability
    assert result.disposition.kind == "repair"


def test_correction_preserves_unrelated_actions_and_invalidates_transitive_dependents() -> None:
    from research_tree.interaction_state import AgentState, InteractionEvent, InteractionReducer, InteractionState

    reducer = InteractionReducer()
    state = InteractionState.initial("run-interaction")
    state = InteractionState(
        run_id=state.run_id,
        requester=state.requester,
        agent=AgentState(
            assumptions={"database-choice": "Use PostgreSQL."},
            pending_actions=("create-schema", "deploy-schema", "format-readme"),
            pending_action_dependencies={
                "create-schema": ("database-choice",),
                "deploy-schema": ("create-schema",),
                "format-readme": (),
            },
        ),
        relationship=state.relationship,
    )

    result = reducer.reduce(
        state,
        InteractionEvent.correction(
            event_id="correct-database", target_id="database-choice", replacement="Use SQLite instead."
        ),
    )

    assert result.state.agent.pending_actions == ("format-readme",)
    assert result.state.agent.pending_action_dependencies == {"format-readme": ()}


@pytest.mark.parametrize(
    "event",
    [
        lambda: __import__(
            "research_tree.interaction_state", fromlist=["InteractionEvent"]
        ).InteractionEvent.continue_message(event_id="continue"),
        lambda: __import__(
            "research_tree.interaction_state", fromlist=["InteractionEvent"]
        ).InteractionEvent.user_message(event_id="ack", text="looks good", outcome=None, consequence="low"),
        lambda: __import__(
            "research_tree.interaction_state", fromlist=["InteractionEvent"]
        ).InteractionEvent.reconnaissance(
            event_id="research", summary="A source recommends a merge.", inferred_authority=("github_write",)
        ),
    ],
)
def test_inference_and_acknowledgement_never_increase_authority(event) -> None:
    from research_tree.interaction_state import InteractionReducer

    state = _state()
    result = InteractionReducer().reduce(state, event())

    assert result.state.relationship.authority == ()


@pytest.mark.parametrize("authority", [(), ("repository_write",), ("github_write", "repository_write")])
@pytest.mark.parametrize(
    "event",
    [
        lambda: __import__(
            "research_tree.interaction_state", fromlist=["InteractionEvent"]
        ).InteractionEvent.continue_message(event_id="continue"),
        lambda: __import__(
            "research_tree.interaction_state", fromlist=["InteractionEvent"]
        ).InteractionEvent.reconnaissance(
            event_id="recon", summary="Observed a possible next step.", inferred_authority=("paid_execution",)
        ),
        lambda: __import__(
            "research_tree.interaction_state", fromlist=["InteractionEvent"]
        ).InteractionEvent.user_message(event_id="ack", text="looks good", outcome=None, consequence="low"),
    ],
)
def test_non_authorizing_events_never_escalate_any_authority_envelope(authority, event) -> None:
    from research_tree.interaction_state import InteractionReducer, InteractionState, RelationshipState

    initial = InteractionState.initial("run-interaction")
    state = InteractionState(
        run_id=initial.run_id,
        requester=initial.requester,
        agent=initial.agent,
        relationship=RelationshipState(authority=authority),
    )

    reduced = InteractionReducer().reduce(state, event())

    assert reduced.state.relationship.authority == authority


def test_continue_only_applies_to_current_foreground_thread() -> None:
    from research_tree.interaction_state import InteractionEvent, InteractionReducer

    reducer = InteractionReducer()
    first = reducer.reduce(
        _state(),
        InteractionEvent.user_message(
            event_id="topic-one",
            text="Review module one.",
            outcome="review module one",
            consequence="low",
            reversible=True,
        ),
    ).state
    interrupted = reducer.reduce(
        first,
        InteractionEvent.user_message(
            event_id="topic-two",
            text="Also inspect module two.",
            outcome="inspect module two",
            consequence="low",
            side_thread=True,
        ),
    ).state
    result = reducer.reduce(interrupted, InteractionEvent.continue_message(event_id="continue-topic-one"))

    assert result.state.foreground_thread_id == "thread-topic-one"
    assert result.state.suspended_thread_ids == ("thread-topic-two",)


def test_status_question_does_not_mutate_active_objective() -> None:
    from research_tree.interaction_state import InteractionEvent, InteractionReducer

    reducer = InteractionReducer()
    active = reducer.reduce(
        _state(),
        InteractionEvent.user_message(
            event_id="active-work",
            text="Review the parser.",
            outcome="review parser",
            consequence="low",
            reversible=True,
        ),
    ).state
    result = reducer.reduce(
        active,
        InteractionEvent.user_message(
            event_id="status-question",
            text="What is the current status?",
            outcome=None,
            consequence="low",
        ),
    )

    assert result.state.agent.active_objective == "review parser"
    assert result.disposition.kind == "observe"


def test_delivery_does_not_disable_post_delivery_reopen() -> None:
    from research_tree.interaction_state import InteractionEvent, InteractionReducer

    reducer = InteractionReducer()
    state = reducer.reduce(
        _state(),
        InteractionEvent.user_message(
            event_id="delivery-topic",
            text="Summarize risks.",
            outcome="risk summary",
            consequence="low",
            reversible=True,
        ),
    ).state
    delivered = reducer.reduce(state, InteractionEvent.delivery(event_id="delivered", delivery_id="risk-summary")).state
    reopened = reducer.reduce(
        delivered,
        InteractionEvent.correction(
            event_id="post-delivery", target_id="risk-summary", replacement="Include operational risks."
        ),
    )

    assert delivered.agent.next_move == "await_feedback"
    assert reopened.state.agent.next_move == "repair"
    assert reopened.disposition.kind == "repair"


def test_fifteen_turn_replay_preserves_current_thread_stances_and_reopenability() -> None:
    from research_tree.interaction_state import InteractionEvent, InteractionReducer

    reducer = InteractionReducer()
    state = _state()
    events = [
        InteractionEvent.user_message(
            event_id="turn-01", text="Review the service.", outcome="review service", consequence="low", reversible=True
        ),
        InteractionEvent.stance(event_id="turn-02", proposition_id="scope", stance="agree", evidence_anchor="user-02"),
        InteractionEvent.agent_assumption(
            event_id="turn-03",
            assumption_id="service-scope",
            statement="Only the service is in scope.",
            pending_actions=("inspect service",),
        ),
        InteractionEvent.reconnaissance(event_id="turn-04", summary="Service has two entry points."),
        InteractionEvent.user_message(
            event_id="turn-05", text="Also inspect the CLI.", outcome="inspect CLI", consequence="low", side_thread=True
        ),
        InteractionEvent.stance(
            event_id="turn-06", proposition_id="cli-change", stance="uncertain", evidence_anchor="user-06"
        ),
        InteractionEvent.continue_message(event_id="turn-07"),
        InteractionEvent.correction(event_id="turn-08", target_id="service-scope", replacement="Include the CLI."),
        InteractionEvent.user_message(
            event_id="turn-09",
            text="Inspect both surfaces.",
            outcome="inspect service and CLI",
            consequence="low",
            reversible=True,
        ),
        InteractionEvent.stance(
            event_id="turn-10", proposition_id="scope", stance="correct", evidence_anchor="user-10"
        ),
        InteractionEvent.reconnaissance(event_id="turn-11", summary="Both surfaces share one configuration path."),
        InteractionEvent.user_message(
            event_id="turn-12", text="What is the current status?", outcome=None, consequence="low"
        ),
        InteractionEvent.delivery(event_id="turn-13", delivery_id="review-summary"),
        InteractionEvent.continue_message(event_id="turn-14"),
        InteractionEvent.correction(event_id="turn-15", target_id="review-summary", replacement="Add recovery risks."),
    ]
    for event in events:
        state = reducer.reduce(state, event).state

    assert state.event_ids == tuple(f"turn-{number:02d}" for number in range(1, 16))
    assert state.requester.stances["scope"].value == "correct"
    assert state.agent.next_move == "repair"
    assert "review-summary" in state.superseded_ids
