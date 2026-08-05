import pytest

from research_tree import build_insight_digest, validate_canonical_insight_digest
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
