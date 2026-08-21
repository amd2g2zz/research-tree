from __future__ import annotations

from hashlib import sha256

import pytest

from research_tree.domain import canonical_json_bytes


def digest() -> str:
    return sha256(
        canonical_json_bytes({"run_id": "run-a", "technical_revision": "technical-1", "human_revision": "human-1"})
    ).hexdigest()


def feedback(kind: str, statement: str) -> list[dict[str, object]]:
    return [
        {
            "feedback_id": "feedback-1",
            "classification": kind,
            "statement": statement,
            "target_refs": ["technical-1", "human-1"],
        }
    ]


def accept(**kwargs):
    from research_tree.acceptance import DeliveryAcceptance

    return DeliveryAcceptance.create(
        kwargs.pop("acceptance_id", "accept-1"),
        "run-a",
        "technical-1",
        "human-1",
        digest(),
        "a" * 64,
        kwargs.pop("feedback", feedback("presentation", "I accept the displayed conclusions and trade-offs.")),
        **kwargs,
    )


def test_acceptance_binds_pair_and_rejects_generic_or_stale() -> None:
    from research_tree.acceptance import AcceptanceError

    with pytest.raises(AcceptanceError, match="generic"):
        accept(feedback=feedback("presentation", "okay"))
    with pytest.raises(AcceptanceError, match="stale"):
        from research_tree.acceptance import DeliveryAcceptance

        DeliveryAcceptance.create(
            "stale",
            "run-a",
            "technical-1",
            "human-1",
            "0" * 64,
            "a" * 64,
            feedback("presentation", "I accept the displayed conclusions."),
        )
    result = accept()
    assert result.decision == "accepted" and result.lifecycle_action == "complete"
    assert result.to_dict()["technical_revision"] == "technical-1"


@pytest.mark.parametrize(
    ("decision", "kind", "expected"),
    [
        ("needs_deeper_research", "depth", "same_round_research"),
        ("needs_intent_correction", "intended_use", "successor_round"),
        ("partially_accepted", "presentation", "awaiting_acceptance"),
        ("rejected", "withdrawal", "same_round_research"),
    ],
)
def test_feedback_routes_non_terminal_acceptance(decision: str, kind: str, expected: str) -> None:
    result = accept(
        acceptance_id=f"accept-{kind}",
        decision=decision,
        feedback=feedback(kind, "The displayed delivery needs a recorded follow-up."),
    )
    assert result.lifecycle_action == expected
