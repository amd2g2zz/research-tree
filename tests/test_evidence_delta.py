from __future__ import annotations

from research_tree.evidence_delta import EvidenceBaseline, baseline_from_finding_packs, measure_realized_delta


def finding(
    finding_id: str,
    *,
    evidence_class: str = "implementation",
    effect: str = "supports",
    uncertainty: str = "",
) -> dict:
    return {
        "id": finding_id,
        "decision_slot_id": "slot-architecture",
        "observations": [
            {
                "claim": "The run has a replayable state boundary.",
                "evidence_class": evidence_class,
                "anchor": {"kind": "source", "ref": f"source:{finding_id}", "provenance_group": "primary"},
            }
        ],
        "option_effects": [{"option": "replay", "effect": effect}],
        "remaining_uncertainties": [uncertainty] if uncertainty else [],
        "validation_result": {"status": "passed", "oracle": "replay-oracle", "evidence_ref": f"runs/{finding_id}.json"},
        "closure_status": "closed",
    }


def test_repeated_state_returns_zero_six_component_delta() -> None:
    historical = finding("finding-1")
    delta, _ = measure_realized_delta(baseline_from_finding_packs((historical,)), (historical,), transition_index=1)
    assert delta["schema_version"] == 2
    assert set(delta["components"]) == {
        "evidence_class_coverage",
        "provenance_independence",
        "contradiction_state",
        "oracle_state",
        "implementation_uncertainty",
        "slot_closure_change",
    }
    assert delta["realized_delta"] == 0.0 and delta["no_change"] and delta["duplicate_only"]


def test_new_state_delta_attributes_each_changed_component_to_finding() -> None:
    delta, _ = measure_realized_delta(
        EvidenceBaseline(),
        (finding("finding-new", evidence_class="execution", effect="contradicts", uncertainty="deployment"),),
        transition_index=1,
    )
    assert delta["realized_delta"] > 0 and not delta["no_change"]
    assert all(item["references"] and item["contribution"] for item in delta["components"].values())
