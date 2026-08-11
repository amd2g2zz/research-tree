from __future__ import annotations

import pytest


def test_digest_rejects_wrong_slot_and_duplicate_finding_lineage() -> None:
    from research_tree import synthesize_insights

    pack = {
        "id": "finding-duplicate",
        "decision_slot_id": "slot-other",
        "observations": [
            {
                "claim": "A claim",
                "anchor": {"kind": "source", "ref": "source:one"},
            }
        ],
    }

    with pytest.raises(ValueError, match="active Decision Slot"):
        synthesize_insights(
            [pack],
            active_slot_ids=("slot-architecture",),
        )

    with pytest.raises(ValueError, match="duplicate Finding Pack"):
        synthesize_insights(
            [
                {**pack, "decision_slot_id": "slot-architecture"},
                {**pack, "decision_slot_id": "slot-architecture"},
            ],
            active_slot_ids=("slot-architecture",),
        )


def test_duplicate_digest_batch_records_zero_change_and_no_growth_trigger() -> None:
    from research_tree import synthesize_insights

    pack = {
        "id": "finding-stable",
        "decision_slot_id": "slot-architecture",
        "observations": [
            {
                "claim": "The invariant is preserved.",
                "anchor": {"kind": "source", "ref": "source:stable"},
            },
            {
                "claim": "The invariant is preserved.",
                "anchor": {"kind": "repository", "ref": "src/runtime.py:1"},
            },
        ],
    }
    first = synthesize_insights([pack], active_slot_ids=("slot-architecture",))
    second = synthesize_insights(
        [pack],
        active_slot_ids=("slot-architecture",),
        previous_digest=first,
    )

    assert second["realized_delta"]["no_change"] is True
    assert second["realized_delta"]["penalty"] == "no_progress"
    assert second["recommended_actions"] == first["recommended_actions"]
