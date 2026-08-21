from __future__ import annotations

from research_tree.policy import (
    AdaptiveResearchPolicy,
    DecisionSlotDeficit,
    InsightSignal,
    PolicyConfiguration,
    VerifiedEvidence,
)


def _slot(**values: object) -> DecisionSlotDeficit:
    defaults = dict(
        slot_id="slot-replay",
        question="Which method bounds the remaining uncertainty?",
        priority="P1",
        missing_dimensions=("implementation_uncertainty",),
        closure_oracle="The implementation uncertainty is independently bounded.",
        evidence_refs=("finding:baseline",),
    )
    defaults.update(values)
    return DecisionSlotDeficit(**defaults)


def test_identical_policy_inputs_replay_same_trace_and_dispositions() -> None:
    policy = AdaptiveResearchPolicy(PolicyConfiguration(version="replay-v1", max_frontier=3), seed=19)
    inputs = {
        "slots": (_slot(),),
        "evidence": (VerifiedEvidence("finding:baseline", "slot-replay", ("source",), ("source:one",)),),
        "signals": (InsightSignal("slot-replay", "qualified", ("source:one",), ("implementation_uncertainty",)),),
    }
    first, replay = policy.evaluate(**inputs), policy.evaluate(**inputs)
    assert first == replay
    assert (first.trace.canonical_input_digest, first.trace.tie_break_order, first.trace.selected_ids) == (
        replay.trace.canonical_input_digest,
        replay.trace.tie_break_order,
        replay.trace.selected_ids,
    )


def test_calibration_version_isolated_and_mandatory_validation_survives_capacity() -> None:
    old = AdaptiveResearchPolicy(PolicyConfiguration(version="calibration-v1", max_frontier=1), seed=5)
    new = AdaptiveResearchPolicy(
        PolicyConfiguration(
            version="calibration-v2", max_frontier=1, weights={"criticality": 0.01, "expected_delta": 0.01}
        ),
        seed=5,
    )
    inputs = {
        "slots": (_slot(priority="P0", required_validation=True),),
        "signals": (InsightSignal("slot-replay", "qualified", ("source:one",), ("validation",), mandatory=True),),
    }
    old_result, new_result = old.evaluate(**inputs), new.evaluate(**inputs)
    assert (old_result.trace.policy_version, new_result.trace.policy_version) == ("calibration-v1", "calibration-v2")
    assert old_result.trace.canonical_input_digest == new_result.trace.canonical_input_digest
    assert any(item.kind == "validation" and item.mandatory for item in new_result.proposals)
