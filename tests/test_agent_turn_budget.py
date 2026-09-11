"""Agent turn budget tests (issue #527) — the dual of the user-side cost_cap.

The emitted contract terms carry the agent's own output ceiling (one question
per interactive turn, bounded characters — tier-settable by #526), required
traces queue at most two per turn with the remainder deferred in the terms
and re-emitted next turn, record time verifies the budget as a named
flag-not-block violation stream (structured for the #525 telemetry), and an
exhausted question budget forces a non-question decision until the next turn
resets it. Legacy terms without the budget fields still parse.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from research_tree.alignment_graph import AlignmentGraphStore
from research_tree.turn_contract import (
    DEFAULT_MAX_CHARS_PER_TURN,
    DEFAULT_MAX_QUESTIONS_PER_TURN,
    AgentTurnBudget,
    ContractTerms,
    ContractTermsError,
    CostCap,
)


def _store(tmp_path: Path) -> AlignmentGraphStore:
    store = AlignmentGraphStore(tmp_path / "alignment.db")
    store.initialize("run-527")
    return store


def _merge_gaps(store: AlignmentGraphStore, *specs: tuple[str, int, str]) -> None:
    store.merge(
        {
            "nodes": [
                {
                    "id": gap_id,
                    "type": "unknown",
                    "statement": f"Requester-only dimension {gap_id}.",
                    "status": status,
                    "impact": impact,
                    "human_only": True,
                    "confidence": "low",
                    "source": "agent",
                }
                for gap_id, impact, status in specs
            ]
        }
    )


def _recorded_event_details(database: Path, event_type: str) -> dict:
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT details_json FROM events WHERE event_type=? ORDER BY sequence DESC LIMIT 1",
            (event_type,),
        ).fetchone()
    assert row is not None
    return json.loads(row["details_json"])


# --- Scenario: the budget is emitted with the contract terms -----------------


def test_the_budget_is_emitted_with_the_contract_terms(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"))
    terms = store.plan()["contract_terms"]
    assert terms["agent_turn_budget"] == {
        "max_questions": DEFAULT_MAX_QUESTIONS_PER_TURN,
        "max_chars": DEFAULT_MAX_CHARS_PER_TURN,
    }


# --- Scenario: more than one question names the question dimension -----------


def test_more_than_one_question_flags_the_question_dimension(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"))
    decision = store.plan()
    result = store.record(decision["gap_id"], "unchanged", "fp-1", question_count=2)
    # The violation names the exceeded dimension with limit and observed value.
    assert result["turn_budget_violations"] == [
        {"dimension": "max_questions", "limit": DEFAULT_MAX_QUESTIONS_PER_TURN, "observed": 2}
    ]
    # Flag-not-block: the turn stays valid continuity grounding.
    assert result["turn"] == 1
    # The persisted event carries the same countable stream for #525.
    details = _recorded_event_details(tmp_path / "alignment.db", "response_recorded")
    assert details["turn_budget_violations"] == result["turn_budget_violations"]


# --- Scenario: an over-length turn names the character dimension -------------


def test_an_over_length_turn_flags_the_char_dimension(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"))
    decision = store.plan()
    result = store.record(decision["gap_id"], "unchanged", "fp-1", turn_chars=DEFAULT_MAX_CHARS_PER_TURN + 1)
    assert result["turn_budget_violations"] == [
        {"dimension": "max_chars", "limit": DEFAULT_MAX_CHARS_PER_TURN, "observed": DEFAULT_MAX_CHARS_PER_TURN + 1}
    ]
    # At the limit (or within it) the stream is empty, not absent: the budget
    # was checked.
    result = store.record(
        decision["gap_id"],
        "unchanged",
        "fp-2",
        question_count=DEFAULT_MAX_QUESTIONS_PER_TURN,
        turn_chars=DEFAULT_MAX_CHARS_PER_TURN,
    )
    assert result["turn_budget_violations"] == []


# --- Scenario: a three-trace wishlist defers the remainder -------------------


def test_a_three_trace_wishlist_defers_the_remainder(tmp_path: Path) -> None:
    """Novice posture on a disputed point wants three traces; the turn emits two."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "disputed"))
    terms = store.plan(user_profile="novice")["contract_terms"]
    assert len(terms["required_traces"]) == 2
    # Priority order: the misunderstood-intent floor first, then the survey.
    assert terms["required_traces"] == ["guess-statement", "possibility-survey"]
    # The remainder is deferred in the terms — never silently dropped.
    assert terms["deferred_traces"] == ["option-set"]


# --- Scenario: deferred traces are re-emitted as required next turn ----------


def test_deferred_traces_are_re_emitted_as_required_next_turn(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "disputed"))
    decision = store.plan(user_profile="novice")
    store.record(
        decision["gap_id"],
        "unchanged",
        "fp-1",
        traces=[
            {"type": "guess-statement", "payload": {"guess": "You want the tree to stay conservative."}},
            {"type": "possibility-survey", "payload": {"possibilities": ["assist", "play", "off"]}},
        ],
    )
    next_terms = store.plan(user_profile="novice")["contract_terms"]
    # The deferred name leads the next turn's required traces, ahead of the
    # newly derived names, still within the two-per-turn cap.
    assert next_terms["required_traces"] == ["option-set", "guess-statement"]
    assert next_terms["deferred_traces"] == []


# --- Scenario: budget exhaustion forces a non-question decision --------------


def test_budget_exhaustion_forces_a_non_question_decision(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"), ("gap-b", 4, "candidate"))
    first = store.plan()
    assert first["action"] == "ask_one"
    assert first["question_budget"] == {
        "max_questions": DEFAULT_MAX_QUESTIONS_PER_TURN,
        "asked_this_turn": 1,
        "remaining": 0,
    }
    # A second plan in the same turn must not ask again: one question per
    # interactive turn, composed as a mirror/teach/gather turn instead.
    second = store.plan()
    assert second["action"] == "reconnaissance"
    assert second["question"] is None
    assert second["gap_id"] == "gap-b"
    assert second["question_budget"]["remaining"] == 0
    # The turn stays dialogue-grounded: the terms target the gap, not research.
    assert second["contract_terms"]["target_gap"] == "gap-b"
    assert second["contract_terms"]["agent_turn_budget"] is not None
    # Recording the turn advances and resets the budget: gap-b was never asked.
    store.record("gap-a", "answered", "fp-1")
    third = store.plan()
    assert third["action"] == "ask_one"
    assert third["gap_id"] == "gap-b"
    assert third["question_budget"]["asked_this_turn"] == 1


# --- Scenario: legacy terms without budget fields still parse ----------------


def test_legacy_terms_without_budget_fields_still_parse() -> None:
    legacy = {
        "schema_version": 1,
        "target_gap": "gap-a",
        "required_traces": [],
        "cost_cap": {"response_class": "generation", "max_sentences": None},
        "taboos": [],
    }
    terms = ContractTerms.from_dict(legacy)
    assert terms.agent_turn_budget is None
    assert terms.deferred_traces == ()
    assert ContractTerms.from_dict(terms.to_dict()) == terms
    # The additive fields round-trip through the same schema version.
    budgeted = ContractTerms(
        target_gap="gap-a",
        required_traces=("possibility-survey",),
        cost_cap=CostCap(response_class="generation", max_sentences=None),
        agent_turn_budget=AgentTurnBudget(max_questions=1, max_chars=800),
        deferred_traces=("proportionality_assessment",),
    )
    assert ContractTerms.from_dict(budgeted.to_dict()) == budgeted
    with pytest.raises(ContractTermsError, match="max_questions"):
        AgentTurnBudget(max_questions=0, max_chars=800)
