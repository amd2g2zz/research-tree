from __future__ import annotations

import pytest

from research_tree.policy import AdaptiveResearchPolicy, DecisionSlotDeficit, PolicyConfiguration


def slot(**overrides: object) -> DecisionSlotDeficit:
    values = {
        "slot_id": "slot-architecture",
        "question": "How should the run preserve a replayable research state?",
        "priority": "P1",
        "missing_dimensions": ("evidence_class_coverage",),
        "closure_oracle": "The evidence is independent and the replay oracle passes.",
    }
    values.update(overrides)
    return DecisionSlotDeficit(**values)


def test_uncovered_slot_gets_bounded_landscape_proposal() -> None:
    result = AdaptiveResearchPolicy(PolicyConfiguration(version="policy-test-v1"), seed=11).evaluate(
        slots=(slot(priority="P0"),)
    )
    proposal = result.proposals[0]
    assert [proposal.kind] == ["landscape"]
    assert proposal.slot_id == "slot-architecture"
    assert proposal.missing_dimensions == ("evidence_class_coverage",)
    assert proposal.closure_oracle.startswith("The evidence")
    assert proposal.causal_refs == ("deficit:slot-architecture",)
    assert result.trace.policy_version == "policy-test-v1"
    assert result.trace.seed == 11 and result.trace.authority == "coordinator_only"


def test_worker_only_suggestion_is_rejected_without_a_verified_trigger() -> None:
    result = AdaptiveResearchPolicy(seed=3).evaluate(
        slots=(slot(),),
        worker_suggestions=({"action_id": "worker-idea", "slot_id": "slot-architecture", "kind": "deep_dive"},),
    )
    assert result.proposals == ()
    assert result.dispositions[0].disposition == "rejected"
    assert result.dispositions[0].reason == "missing_verified_trigger"


def test_policy_rejects_malformed_slot_deficit() -> None:
    with pytest.raises(ValueError, match="closure_oracle"):
        AdaptiveResearchPolicy().evaluate(slots=({"slot_id": "slot-bad", "question": "incomplete"},))
