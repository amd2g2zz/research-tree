from __future__ import annotations


def pack(
    finding_id: str,
    *,
    slot_id: str = "slot-architecture",
    effect: str = "supports",
    anchor_kind: str = "source",
    anchor_ref: str = "source:primary",
    uncertainty: str | None = None,
) -> dict[str, object]:
    return {
        "id": finding_id,
        "decision_slot_id": slot_id,
        "observations": [
            {
                "claim": "The boundary preserves the required invariant.",
                "anchor": {"kind": anchor_kind, "ref": anchor_ref},
            }
        ],
        "option_effects": [{"option": "candidate-a", "effect": effect}],
        "remaining_uncertainties": [] if uncertainty is None else [uncertainty],
    }


def test_insights_detect_uncovered_and_contested_decision_slots() -> None:
    from research_tree import synthesize_insights

    digest = synthesize_insights(
        [
            pack("finding-supports"),
            pack(
                "finding-contradicts",
                effect="contradicts",
                anchor_kind="repository",
                anchor_ref="src/agent.py:run",
            ),
        ],
        active_slot_ids=("slot-architecture", "slot-operations"),
    )

    by_slot = {item["decision_slot_id"]: item for item in digest["insights"]}
    assert by_slot["slot-architecture"]["signal"] == "contested"
    assert by_slot["slot-architecture"]["conflicts"] == [
        {"option": "candidate-a", "effects": ["contradicts", "supports"]}
    ]
    assert by_slot["slot-operations"]["signal"] == "uncovered"
    assert digest["closure"] == "blocked_by_uncovered_or_contested_slots"
    assert {item["action"] for item in digest["next_actions"]} == {
        "dispatch_adversarial_recheck",
        "dispatch_landscape",
    }


def test_insights_require_validation_when_triangulated_findings_remain_qualified() -> None:
    from research_tree import synthesize_insights

    digest = synthesize_insights(
        [
            pack("finding-primary", uncertainty="Version behavior needs an execution check."),
            pack(
                "finding-repository",
                anchor_kind="repository",
                anchor_ref="src/agent.py:run",
                uncertainty="Version behavior needs an execution check.",
            ),
        ],
        active_slot_ids=("slot-architecture",),
    )

    insight = digest["insights"][0]
    assert insight["signal"] == "qualified"
    assert insight["anchor_count"] == 2
    assert insight["repeated_claims"][0]["independent_count"] == 2
    assert digest["next_actions"] == [
        {"decision_slot_id": "slot-architecture", "action": "dispatch_validation"}
    ]
    assert digest["closure"] == "blocked_by_uncovered_or_contested_slots"
