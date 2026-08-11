from __future__ import annotations

import pytest


def slot(
    *,
    slot_id: str = "slot-architecture",
    priority: str = "P1",
    missing_dimensions: tuple[str, ...] = ("evidence_class_coverage",),
    required_validation: bool = False,
):
    from research_tree.policy import DecisionSlotDeficit

    return DecisionSlotDeficit(
        slot_id=slot_id,
        question="How should the run preserve a replayable research state?",
        priority=priority,
        missing_dimensions=missing_dimensions,
        closure_oracle="The evidence is independent and the replay oracle passes.",
        evidence_refs=(),
        required_validation=required_validation,
    )


def test_uncovered_slot_gets_bounded_landscape_proposal() -> None:
    from research_tree.policy import AdaptiveResearchPolicy, PolicyConfiguration

    result = AdaptiveResearchPolicy(PolicyConfiguration(version="policy-test-v1"), seed=11).evaluate(
        slots=(slot(priority="P0"),)
    )

    assert [proposal.kind for proposal in result.proposals] == ["landscape"]
    proposal = result.proposals[0]
    assert proposal.slot_id == "slot-architecture"
    assert proposal.missing_dimensions == ("evidence_class_coverage",)
    assert proposal.closure_oracle.startswith("The evidence")
    assert proposal.causal_refs == ("deficit:slot-architecture",)
    assert result.trace.policy_version == "policy-test-v1"
    assert result.trace.seed == 11
    assert result.trace.authority == "coordinator_only"


def test_worker_only_suggestion_is_rejected_without_a_verified_trigger() -> None:
    from research_tree.policy import AdaptiveResearchPolicy

    result = AdaptiveResearchPolicy(seed=3).evaluate(
        slots=(slot(),),
        worker_suggestions=(
            {
                "action_id": "worker-idea",
                "slot_id": "slot-architecture",
                "kind": "deep_dive",
                "question": "Try another branch",
            },
        ),
    )

    assert result.proposals == ()
    assert len(result.dispositions) == 1
    assert result.dispositions[0].disposition == "rejected"
    assert result.dispositions[0].reason == "missing_verified_trigger"


def test_policy_rejects_malformed_slot_deficit() -> None:
    from research_tree.policy import AdaptiveResearchPolicy

    with pytest.raises(ValueError, match="closure_oracle"):
        AdaptiveResearchPolicy().evaluate(
            slots=(
                {
                    "slot_id": "slot-bad",
                    "question": "incomplete",
                    "missing_dimensions": ["coverage"],
                    "evidence_refs": [],
                },
            )
        )
