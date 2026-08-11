from __future__ import annotations


def _slot(*, priority: str = "P1", required_validation: bool = False):
    from research_tree.policy import DecisionSlotDeficit

    return DecisionSlotDeficit(
        slot_id="slot-replay",
        question="Which method bounds the remaining uncertainty?",
        priority=priority,
        missing_dimensions=("implementation_uncertainty",),
        closure_oracle="The implementation uncertainty is independently bounded.",
        evidence_refs=("finding:baseline",),
        required_validation=required_validation,
    )


def test_identical_policy_inputs_replay_same_trace_and_dispositions() -> None:
    from research_tree.policy import (
        AdaptiveResearchPolicy,
        InsightSignal,
        PolicyConfiguration,
        VerifiedEvidence,
    )

    policy = AdaptiveResearchPolicy(PolicyConfiguration(version="replay-v1", max_frontier=3), seed=19)
    inputs = {
        "slots": (_slot(),),
        "evidence": (
            VerifiedEvidence(
                evidence_id="finding:baseline",
                slot_id="slot-replay",
                evidence_classes=("source",),
                provenance_refs=("source:one",),
            ),
        ),
        "signals": (
            InsightSignal(
                slot_id="slot-replay",
                signal="qualified",
                source_refs=("source:one",),
                gap_refs=("implementation_uncertainty",),
            ),
        ),
    }

    first = policy.evaluate(**inputs)
    replay = policy.evaluate(**inputs)

    assert first == replay
    assert first.trace.canonical_input_digest == replay.trace.canonical_input_digest
    assert first.trace.tie_break_order == replay.trace.tie_break_order
    assert first.trace.selected_ids == replay.trace.selected_ids


def test_calibration_version_isolated_and_mandatory_validation_survives_capacity() -> None:
    from research_tree.policy import AdaptiveResearchPolicy, PolicyConfiguration, InsightSignal

    old = AdaptiveResearchPolicy(PolicyConfiguration(version="calibration-v1", max_frontier=1), seed=5)
    new = AdaptiveResearchPolicy(
        PolicyConfiguration(
            version="calibration-v2",
            max_frontier=1,
            weights={"criticality": 0.01, "expected_delta": 0.01},
        ),
        seed=5,
    )
    inputs = {
        "slots": (_slot(priority="P0", required_validation=True),),
        "signals": (
            InsightSignal(
                slot_id="slot-replay",
                signal="qualified",
                source_refs=("source:one",),
                gap_refs=("validation",),
                mandatory=True,
            ),
        ),
    }

    old_result = old.evaluate(**inputs)
    new_result = new.evaluate(**inputs)

    assert old_result.trace.policy_version == "calibration-v1"
    assert new_result.trace.policy_version == "calibration-v2"
    assert old_result.trace.canonical_input_digest == new_result.trace.canonical_input_digest
    assert any(proposal.kind == "validation" for proposal in new_result.proposals)
    assert all(proposal.mandatory for proposal in new_result.proposals)
