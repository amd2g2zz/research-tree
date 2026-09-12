"""Interview-protocol tests (issue #500).

The engine takes the user profile as a turn-context input and gates the
novice posture structurally (discrimination cap, option-set, possibility-
survey before anything open-ended); profile inference and interview craft
stay in the prompt layer (#501, #500 design ruling).
"""

from __future__ import annotations

import pytest

from research_tree.alignment_graph import AlignmentGraphStore


def _store(tmp_path, *gap_specs: tuple[str, int, str]) -> AlignmentGraphStore:
    store = AlignmentGraphStore(tmp_path / "alignment.db")
    store.initialize("run-500")
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
                for gap_id, impact, status in (gap_specs or (("gap-fresh", 5, "candidate"),))
            ],
            "edges": [],
        }
    )
    return store


def test_unknown_profile_is_rejected(tmp_path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="user_profile"):
        store.plan(user_profile="genius")


def test_absent_profile_keeps_current_behavior(tmp_path) -> None:
    baseline = _store(tmp_path / "a").plan()
    explicit = _store(tmp_path / "b").plan(user_profile="expert")
    novice = _store(tmp_path / "c").plan(user_profile="novice")["contract_terms"]
    # Identical graph state: the expert declaration changes nothing versus an
    # absent profile; the novice gate is the only posture change.
    assert explicit["contract_terms"] == baseline["contract_terms"]
    assert novice["cost_cap"]["response_class"] == "discrimination"
    assert novice["required_traces"] == ["possibility-survey", "option-set"]


def test_first_novice_ask_carries_survey_and_option_set(tmp_path) -> None:
    store = _store(tmp_path)
    decision = store.plan(user_profile="novice")
    terms = decision["contract_terms"]
    assert terms["required_traces"] == ["possibility-survey", "option-set"]
    assert terms["cost_cap"]["response_class"] == "discrimination"
    assert terms["cost_cap"]["max_sentences"] == 1


def test_recorded_survey_relaxes_to_option_set(tmp_path) -> None:
    store = _store(tmp_path)
    terms = store.plan(user_profile="novice")["contract_terms"]
    store.record(
        terms["target_gap"],
        "unchanged",
        "fp-survey",
        traces=[
            {"type": "possibility-survey", "payload": {"possibilities": ["AI plays", "AI assists", "AI generates"]}},
            {"type": "option-set", "payload": {"options": ["AI plays", "AI assists"]}},
        ],
        user_move="generation",
    )
    next_terms = store.plan(user_profile="novice")["contract_terms"]
    assert "possibility-survey" not in next_terms["required_traces"]
    assert "option-set" in next_terms["required_traces"]
    assert next_terms["cost_cap"]["response_class"] == "discrimination"


def test_open_question_without_survey_fails_verification(tmp_path) -> None:
    store = _store(tmp_path)
    terms = store.plan(user_profile="novice")["contract_terms"]
    with pytest.raises(Exception, match="possibility-survey"):
        store.record(
            terms["target_gap"],
            "unchanged",
            "fp-open",
            traces=[{"type": "option-set", "payload": {"options": ["only options"]}}],
            user_move="discrimination",
        )


def test_expert_profile_does_not_force_the_novice_posture(tmp_path) -> None:
    store = _store(tmp_path)
    decision = store.plan(user_profile="expert")
    # Expert turns keep the open-ended generation cap (#498 may still require
    # a survey/proportionality from gap shape — that is not the novice gate).
    assert "option-set" not in decision["contract_terms"]["required_traces"]
    assert decision["contract_terms"]["cost_cap"]["response_class"] == "generation"
