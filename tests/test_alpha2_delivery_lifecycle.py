from __future__ import annotations

from hashlib import sha256

import pytest

from research_tree.domain import canonical_json_bytes


def _pair_digest(run_id: str, technical: str, human: str) -> str:
    return sha256(
        canonical_json_bytes({"run_id": run_id, "technical_revision": technical, "human_revision": human})
    ).hexdigest()


def _feedback(classification: str, statement: str) -> list[dict[str, object]]:
    return [
        {
            "feedback_id": "feedback-1",
            "classification": classification,
            "statement": statement,
            "target_refs": ["technical-1", "human-1"],
        }
    ]


def test_delivery_acceptance_rejects_generic_ack_and_binds_exact_revisions() -> None:
    from research_tree.acceptance import AcceptanceError, DeliveryAcceptance

    digest = _pair_digest("run-a", "technical-1", "human-1")
    with pytest.raises(AcceptanceError, match="generic"):
        DeliveryAcceptance.create(
            "accept-1",
            "run-a",
            "technical-1",
            "human-1",
            digest,
            "a" * 64,
            _feedback("presentation", "okay"),
        )
    with pytest.raises(AcceptanceError, match="stale"):
        DeliveryAcceptance.create(
            "accept-2",
            "run-a",
            "technical-1",
            "human-1",
            "0" * 64,
            "a" * 64,
            _feedback("presentation", "I accept the displayed conclusions and trade-offs."),
        )
    accepted = DeliveryAcceptance.create(
        "accept-3",
        "run-a",
        "technical-1",
        "human-1",
        digest,
        "a" * 64,
        _feedback("presentation", "I accept the displayed conclusions and trade-offs."),
    )
    assert accepted.decision == "accepted"
    assert accepted.lifecycle_action == "complete"
    assert accepted.to_dict()["technical_revision"] == "technical-1"


def test_rejection_routes_depth_to_same_round_and_intent_to_successor() -> None:
    from research_tree.acceptance import DeliveryAcceptance

    digest = _pair_digest("run-a", "technical-1", "human-1")
    depth = DeliveryAcceptance.create(
        "accept-depth",
        "run-a",
        "technical-1",
        "human-1",
        digest,
        "b" * 64,
        _feedback("depth", "The evidence chain is too shallow to support implementation."),
        decision="needs_deeper_research",
    )
    intent = DeliveryAcceptance.create(
        "accept-intent",
        "run-a",
        "technical-1",
        "human-1",
        digest,
        "b" * 64,
        _feedback("intended_use", "The report must support an investment decision, not implementation."),
        decision="needs_intent_correction",
    )
    assert depth.lifecycle_action == "same_round_research"
    assert intent.lifecycle_action == "successor_round"


def test_partial_acceptance_and_withdrawal_remain_non_terminal() -> None:
    from research_tree.acceptance import DeliveryAcceptance

    digest = _pair_digest("run-a", "technical-1", "human-1")
    partial = DeliveryAcceptance.create(
        "accept-partial",
        "run-a",
        "technical-1",
        "human-1",
        digest,
        "c" * 64,
        _feedback("presentation", "The technical package is accepted; revise the report."),
        decision="partially_accepted",
    )
    withdrawn = DeliveryAcceptance.create(
        "accept-withdrawn",
        "run-a",
        "technical-1",
        "human-1",
        digest,
        "c" * 64,
        _feedback("withdrawal", "Withdraw the earlier acceptance pending new evidence."),
        decision="rejected",
    )
    assert partial.lifecycle_action == "awaiting_acceptance"
    assert withdrawn.lifecycle_action == "same_round_research"
