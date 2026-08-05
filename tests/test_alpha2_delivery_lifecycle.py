from __future__ import annotations

import pytest


def test_delivery_acceptance_rejects_generic_ack_and_binds_exact_revisions() -> None:
    from research_tree.acceptance import AcceptanceError, DeliveryAcceptance

    with pytest.raises(AcceptanceError, match="generic"):
        DeliveryAcceptance.create("accept-1", "run-a", "tech-1", "human-1", "digest", "okay")
    accepted = DeliveryAcceptance.create("accept-2", "run-a", "tech-1", "human-1", "digest", "I accept the displayed technical and human reports.")
    assert accepted.decision == "accepted"
    assert accepted.to_dict()["technical_revision"] == "tech-1"


def test_lifecycle_projection_is_registry_bounded() -> None:
    from research_tree.lifecycle import LifecycleError, allowed_transition, transition_table

    assert allowed_transition("alignment", "alignment_projection_ready")
    assert not allowed_transition("alignment", "delivery_accepted")
    assert transition_table()
    with pytest.raises(LifecycleError):
        allowed_transition("unknown", "resume")
