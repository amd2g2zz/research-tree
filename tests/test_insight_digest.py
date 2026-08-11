from __future__ import annotations

import pytest

from research_tree import synthesize_insights


def pack(finding_id: str, slot_id: str = "slot-architecture") -> dict:
    return {
        "id": finding_id,
        "decision_slot_id": slot_id,
        "observations": [{"claim": "A claim", "anchor": {"kind": "source", "ref": f"source:{finding_id}"}}],
    }


def test_digest_rejects_wrong_slot_and_duplicate_finding_lineage() -> None:
    with pytest.raises(ValueError, match="active Decision Slot"):
        synthesize_insights([pack("finding-duplicate", "slot-other")], active_slot_ids=("slot-architecture",))
    with pytest.raises(ValueError, match="duplicate Finding Pack"):
        synthesize_insights(
            [pack("finding-duplicate"), pack("finding-duplicate")], active_slot_ids=("slot-architecture",)
        )


def test_duplicate_digest_batch_records_zero_change_and_no_growth_trigger() -> None:
    value = pack("finding-stable")
    value["observations"].append({"claim": "A claim", "anchor": {"kind": "repository", "ref": "src/runtime.py:1"}})
    first = synthesize_insights([value], active_slot_ids=("slot-architecture",))
    second = synthesize_insights([value], active_slot_ids=("slot-architecture",), previous_digest=first)
    assert second["realized_delta"]["no_change"] is True
    assert second["realized_delta"]["penalty"] == "no_progress"
    assert second["recommended_actions"]
