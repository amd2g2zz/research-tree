from __future__ import annotations


def finding(
    finding_id: str,
    *,
    anchor_kind: str = "source",
    anchor_ref: str = "source:primary",
    provenance_group: str = "primary",
    validation_status: str = "pending",
    uncertainty: str = "",
    closure_status: str = "open",
):
    return {
        "id": finding_id,
        "decision_slot_id": "slot-architecture",
        "observations": [
            {
                "claim": "The run has a replayable state boundary.",
                "evidence_class": "implementation",
                "anchor": {
                    "kind": anchor_kind,
                    "ref": anchor_ref,
                    "provenance_group": provenance_group,
                },
            }
        ],
        "option_effects": [{"option": "replay", "effect": "supports"}],
        "remaining_uncertainties": [uncertainty] if uncertainty else [],
        "validation_result": {
            "status": validation_status,
            "oracle": "replay-oracle",
            "evidence_ref": f"runs/{finding_id}.json",
        },
        "closure_status": closure_status,
    }


def test_repeated_state_returns_zero_six_component_delta() -> None:
    from research_tree.evidence_delta import baseline_from_finding_packs, measure_realized_delta

    historical = finding("finding-1")
    baseline = baseline_from_finding_packs((historical,))
    delta, next_baseline = measure_realized_delta(
        baseline,
        (historical,),
        transition_index=1,
    )

    assert delta["schema_version"] == 2
    assert set(delta["components"]) == {
        "evidence_class_coverage",
        "provenance_independence",
        "contradiction_state",
        "oracle_state",
        "implementation_uncertainty",
        "slot_closure_change",
    }
    assert delta["realized_delta"] == 0.0
    assert delta["no_change"] is True
    assert delta["duplicate_only"] is True
    assert next_baseline == baseline


def test_new_state_delta_attributes_each_changed_component_to_finding() -> None:
    from research_tree.evidence_delta import EvidenceBaseline, measure_realized_delta

    baseline = EvidenceBaseline()
    delta, _ = measure_realized_delta(
        baseline,
        (
            {
                "id": "finding-new",
                "decision_slot_id": "slot-architecture",
                "observations": [
                    {
                        "claim": "A new implementation boundary is verified.",
                        "evidence_class": "execution",
                        "anchor": {
                            "kind": "experiment",
                            "ref": "runs/replay.json",
                            "provenance_group": "independent-experiment",
                        },
                    }
                ],
                "option_effects": [{"option": "replay", "effect": "contradicts"}],
                "remaining_uncertainties": ["deployment uncertainty"],
                "validation_result": {
                    "status": "passed",
                    "oracle": "replay-oracle",
                    "evidence_ref": "runs/replay.json",
                },
                "closure_status": "closed",
            },
        ),
        transition_index=1,
    )

    assert delta["realized_delta"] > 0
    assert delta["no_change"] is False
    assert all(component["references"] for component in delta["components"].values())
    assert delta["components"]["evidence_class_coverage"]["contribution"]
    assert delta["components"]["slot_closure_change"]["contribution"]
