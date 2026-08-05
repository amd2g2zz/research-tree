import pytest

from research_tree import (
    build_insight_digest,
    synthesize_insights,
    validate_canonical_insight_digest,
)
from research_tree.insights import InsightDigestError


def test_canonical_insight_digest_is_deterministic_and_classified():
    finding = {"id": "finding-a", "decision_slot_id": "slot-a", "observations": [{"claim": "The source supports option A.", "anchor": {"kind": "source", "ref": "source-1"}, "confidence": "high"}], "option_effects": [{"option": "a", "effect": "supports"}]}
    first = build_insight_digest([finding], digest_id="digest-a", producer_version="insight-v1", active_slot_ids=["slot-a"])
    second = build_insight_digest([finding], digest_id="digest-a", producer_version="insight-v1", active_slot_ids=["slot-a"])
    assert first == second
    validate_canonical_insight_digest(first)
    assert first["statements"][0]["class"] == "fact"


def test_canonical_insight_digest_rejects_unsupported_fact_and_records_gap():
    with pytest.raises(InsightDigestError):
        build_insight_digest([{"id": "finding-a", "decision_slot_id": "slot-a", "observations": [{"claim": "unverified"}]}], digest_id="digest-a", producer_version="v1", active_slot_ids=["slot-a"])
    digest = build_insight_digest([{"id": "finding-a", "decision_slot_id": "slot-a", "observations": [], "remaining_uncertainties": ["version behavior unknown"]}], digest_id="digest-a", producer_version="v1", active_slot_ids=["slot-a"])
    assert digest["gaps"][0]["next_acquisition_method"] == "validation"


def test_insight_digest_consumes_alpha2_anchors_and_structured_uncertainty():
    finding = {
        "finding_id": "finding-alpha2",
        "decision_slot_id": "slot-a",
        "observations": [
            {
                "observation_id": "observation-alpha2",
                "class": "fact",
                "claim": "The canonical boundary exists.",
                "anchors": [
                    {
                        "artifact_digest": "a" * 64,
                        "artifact_revision": 2,
                    }
                ],
                "confidence": "high",
            }
        ],
        "option_effects": [
            {
                "option": "a",
                "effect": "supports",
                "observation_ids": ["observation-alpha2"],
            }
        ],
        "remaining_uncertainties": [
            {
                "uncertainty_id": "uncertainty-alpha2",
                "statement": "The alternate path remains untested.",
                "next_method": "adversarial",
            }
        ],
    }

    digest = build_insight_digest(
        [finding],
        digest_id="digest-alpha2",
        producer_version="insight-v1",
        active_slot_ids=["slot-a"],
    )

    assert digest["source_refs"] == [f"evidence:{'a' * 64}@2"]
    assert digest["statements"][0]["evidence_refs"] == digest["source_refs"]
    assert digest["gaps"] == [
        {
            "slot_id": "slot-a",
            "reason": "The alternate path remains untested.",
            "next_acquisition_method": "adversarial",
        }
    ]


def test_structured_synthesis_counts_alpha2_anchor_lineage_and_ids():
    findings = []
    for index, digest in enumerate(("a" * 64, "b" * 64), start=1):
        findings.append(
            {
                "finding_id": f"finding-alpha2-{index}",
                "decision_slot_id": "slot-a",
                "observations": [
                    {
                        "claim": "The canonical boundary exists.",
                        "anchors": [
                            {
                                "artifact_digest": digest,
                                "artifact_revision": 1,
                            }
                        ],
                    }
                ],
                "option_effects": [],
                "remaining_uncertainties": [
                    {
                        "uncertainty_id": f"uncertainty-{index}",
                        "statement": "The alternate path remains untested.",
                        "next_method": "adversarial",
                    }
                ],
            }
        )

    digest = synthesize_insights(findings, active_slot_ids=["slot-a"])
    insight = digest["insights"][0]

    assert insight["finding_ids"] == ["finding-alpha2-1", "finding-alpha2-2"]
    assert insight["anchor_count"] == 2
    assert insight["uncertainties"] == ["The alternate path remains untested."]
    assert insight["signal"] == "qualified"


def test_canonical_digest_exposes_every_uncovered_active_slot():
    finding = {
        "id": "finding-a",
        "decision_slot_id": "slot-a",
        "observations": [
            {
                "claim": "Slot A is covered.",
                "anchor": {"kind": "source", "ref": "source-a"},
            }
        ],
        "option_effects": [],
        "remaining_uncertainties": [],
    }

    digest = build_insight_digest(
        [finding],
        digest_id="digest-uncovered",
        producer_version="insight-v1",
        active_slot_ids=["slot-a", "slot-b"],
    )

    assert digest["gaps"] == [
        {
            "slot_id": "slot-b",
            "reason": "No accepted Finding Pack covers this active Decision Slot.",
            "next_acquisition_method": "landscape",
        }
    ]
    assert digest["recommended_actions"] == [
        {
            "slot_id": "slot-b",
            "action": "landscape",
            "trigger": "No accepted Finding Pack covers this active Decision Slot.",
        }
    ]
