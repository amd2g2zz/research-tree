from __future__ import annotations

import hashlib
import json

import pytest

from research_tree.decision_frame import (
    ClarificationPolicy,
    DecisionFrame,
    DecisionFrameValidationError,
    IntentHypothesis,
)


def _hypothesis(
    hypothesis_id: str,
    *,
    owner: str = "requester",
    researchable: bool = False,
    disposition: str = "unresolved",
    material: bool = True,
    evidence_ranked: bool = False,
    no_progress: bool = False,
    next_action: str = "ask requester",
) -> IntentHypothesis:
    return IntentHypothesis(
        id=hypothesis_id,
        interpretation=f"Interpretation {hypothesis_id}",
        ambiguity=f"Ambiguity {hypothesis_id}",
        owner=owner,
        researchable=researchable,
        decision_consequence=f"Consequence {hypothesis_id}",
        source_refs=("input-1",),
        disposition=disposition,
        next_action=next_action,
        primary_decision_id="decision-1",
        material=material,
        evidence_ranked=evidence_ranked,
        no_progress=no_progress,
    )


def _frame(*hypotheses: IntentHypothesis, wording: str = "What should this app do?") -> DecisionFrame:
    return DecisionFrame.create(
        frame_id="frame-1",
        run_id="run-1",
        requester_wording=wording,
        primary_decision={
            "id": "decision-1",
            "statement": "Choose the customer decision to validate",
            "success_signal": "A payer and validation signal are explicit",
        },
        hypotheses=hypotheses,
    )


def test_ambiguous_topic_word_preserves_hypotheses_and_never_selects_stack() -> None:
    frame = _frame(
        _hypothesis("business"), _hypothesis("technical", owner="research", researchable=True, material=False)
    )

    assert frame.status == "clarification_required"
    assert frame.policy.action == "ask_user"
    assert frame.policy.question
    assert frame.selected_hypothesis_id is None
    assert frame.primary_decision["id"] == "decision-1"
    assert "stack" not in json.dumps(frame.to_dict()).lower()


def test_hypothesis_validation_requires_material_decision_fields() -> None:
    with pytest.raises(DecisionFrameValidationError, match="owner"):
        IntentHypothesis(
            id="missing-owner",
            interpretation="A",
            ambiguity="B",
            owner="operator",
            researchable=False,
            decision_consequence="C",
            source_refs=("input-1",),
            disposition="unresolved",
            next_action="ask",
            primary_decision_id="decision-1",
        )


def test_researchable_ambiguity_chooses_reconnaissance_without_prompt() -> None:
    frame = _frame(
        _hypothesis("research", owner="research", researchable=True),
        _hypothesis("alternative", owner="research", researchable=True, material=False),
    )

    assert frame.status == "reconnaissance_required"
    assert frame.policy.action == "reconnaissance"
    assert frame.policy.question is None


def test_policy_caps_requester_prompts_and_is_replay_stable() -> None:
    frame = _frame(_hypothesis("a"), _hypothesis("b"), _hypothesis("c"))
    first = ClarificationPolicy().evaluate(frame)
    second = ClarificationPolicy().evaluate(frame)

    assert first == second
    assert first.action == "ask_user"
    assert len(first.hypothesis_ids) >= 2
    assert len(first.question or "") <= 500


def test_no_progress_requires_reframe_or_retained_consequence() -> None:
    frame = _frame(
        _hypothesis("stalled", no_progress=True, next_action="reframe or retain consequence"), _hypothesis("other")
    )

    assert frame.status == "reframe_required"
    assert frame.policy.action == "reframe"


def test_ready_frame_requires_primary_decision_trace_for_enablers() -> None:
    ready = _frame(
        _hypothesis("selected", disposition="selected", evidence_ranked=True),
        _hypothesis("constraint", owner="research", researchable=True, disposition="deferred", material=False),
    )
    assert ready.status == "ready_for_strategy"
    assert ready.selected_hypothesis_id == "selected"

    payload = ready.to_dict()
    assert (
        payload["content_hash"]
        == hashlib.sha256(
            json.dumps(
                {key: value for key, value in payload.items() if key != "content_hash"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )


def test_schema_round_trip_is_cross_host_and_canonical() -> None:
    frame = _frame(_hypothesis("one"), _hypothesis("two"))
    restored = DecisionFrame.from_dict(frame.to_dict())
    assert restored == frame
    assert restored.to_dict() == frame.to_dict()
