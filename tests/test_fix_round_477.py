from __future__ import annotations

import pytest
from canonical_finding_fixture import canonical_context
from test_adaptive_recursion import finding, slots

from research_tree import (
    InvalidFindingPackError,
    RecursiveSearchConfig,
    apply_research_results,
    initialize_research_state,
    validate_tree_state_payload,
)

CLAIM_A = "The mechanism requires independent corroboration."


def test_pack_compile_carries_batch_comparison_end_to_end(tmp_path) -> None:
    ledger, resolver, _record, _model, _brief, _target, work, _a, _b, _evidence, anchor = canonical_context(
        tmp_path, include_decision=False
    )
    from research_tree import CanonicalFindingPackCompiler

    compiled = CanonicalFindingPackCompiler(ledger, resolver).compile(
        round_id="round-canonical",
        finding_id="finding-compared",
        work_item=work,
        observations=[
            {
                "claim_id": "claim-compared",
                "claim": "The compared source supports the boundary.",
                "anchor": anchor.to_dict(),
                "applicability": "the fixture boundary",
                "confidence": "high",
                "limitation": "fixture evidence only",
            }
        ],
        option_effects=[{"option": "isolated-worker", "effect": "supports", "claim_ids": ["claim-compared"]}],
        implementation_implications=["Keep the boundary."],
        remaining_uncertainties=[],
        search_comparison={
            "comparison_id": "comparison-1",
            "provider_fanout": 2,
            "duplicates": 1,
            "captures": 3,
            "coverage_met": 0,
            "contradictions": ["cc-1"],
        },
        expected_revision=ledger.get_revision("round-canonical"),
    )

    assert compiled.payload["comparison_status"] == "measured"
    assert compiled.payload["search_comparison"]["provider_fanout"] == 2
    assert tuple(compiled.payload["search_comparison"]["contradictions"]) == ("cc-1",)

    state = initialize_research_state(
        round_id="round-e2e",
        tree_id="tree-e2e",
        decision_slots={"slot-isolation": {"question": "Q?", "priority": "P1", "uncertainty": "medium"}},
        config=RecursiveSearchConfig(max_depth=5),
    )
    result = apply_research_results(state, (compiled.payload,))
    assert tuple(result["decision_slots"]["slot-isolation"]["contradiction_refs"]) == ("cc-1",)
    assert result["recursion_receipt"]["provider_fanout"] == 2
    assert result["recursion_receipt"]["dedup_ratio"] == pytest.approx(1 / 3)


def test_pack_compile_records_skipped_comparison(tmp_path) -> None:
    ledger, resolver, _record, _model, _brief, _target, work, _a, _b, _evidence, anchor = canonical_context(
        tmp_path, include_decision=False
    )
    from research_tree import CanonicalFindingPackCompiler

    compiled = CanonicalFindingPackCompiler(ledger, resolver).compile(
        round_id="round-canonical",
        finding_id="finding-uncompared",
        work_item=work,
        observations=[
            {
                "claim_id": "claim-uncompared",
                "claim": "The uncompared source supports the boundary.",
                "anchor": anchor.to_dict(),
                "applicability": "the fixture boundary",
                "confidence": "high",
                "limitation": "fixture evidence only",
            }
        ],
        option_effects=[{"option": "isolated-worker", "effect": "supports", "claim_ids": ["claim-uncompared"]}],
        implementation_implications=["Keep the boundary."],
        remaining_uncertainties=[],
        comparison_status="skipped",
        expected_revision=ledger.get_revision("round-canonical"),
    )

    assert compiled.payload["comparison_status"] == "skipped"
    assert "search_comparison" not in compiled.payload


def test_pack_compile_rejects_invalid_comparison_payload(tmp_path) -> None:
    ledger, resolver, _record, _model, _brief, _target, work, _a, _b, _evidence, anchor = canonical_context(
        tmp_path, include_decision=False
    )
    from research_tree import CanonicalFindingPackCompiler

    with pytest.raises(InvalidFindingPackError):
        CanonicalFindingPackCompiler(ledger, resolver).compile(
            round_id="round-canonical",
            finding_id="finding-bad-compare",
            work_item=work,
            observations=[
                {
                    "claim_id": "claim-bad",
                    "claim": "Bad comparison payload.",
                    "anchor": anchor.to_dict(),
                    "applicability": "fixture",
                    "confidence": "high",
                    "limitation": "fixture",
                }
            ],
            option_effects=[{"option": "isolated-worker", "effect": "supports", "claim_ids": ["claim-bad"]}],
            implementation_implications=["Keep the boundary."],
            remaining_uncertainties=[],
            search_comparison={"provider_fanout": -1, "duplicates": 0, "captures": 0, "coverage_met": 0},
            expected_revision=ledger.get_revision("round-canonical"),
        )


def quarantine_chain(config: RecursiveSearchConfig, claim: str = CLAIM_A):
    state = initialize_research_state(
        round_id="round-h2",
        tree_id="tree-h2",
        decision_slots=slots("P1"),
        baseline_findings=(finding("f1", anchors=(("source", "u1"),), continuations=("q1",), claim=claim),),
        config=config,
    )
    first = apply_research_results(
        state,
        (finding("f2", anchors=(("source", "u1"), ("source", "u2")), continuations=("q2",), claim=claim),),
    )
    assert first["cross_validation"]["f2"]["status"] == "required"
    return first


def test_same_source_duplicate_does_not_lift_quarantine() -> None:
    first = quarantine_chain(RecursiveSearchConfig(max_depth=5, low_confidence_threshold=0.7))

    result = apply_research_results(
        first,
        (
            finding(
                "f3",
                anchors=(("source", "u1"), ("source", "u2"), ("source", "u9")),
                contradictions=("c9",),
                claim=CLAIM_A,
                research_node_id="root:slot-1",
            ),
        ),
    )

    assert "f3" not in result["decision_slots"]["slot-1"]["quarantined_finding_ids"]
    assert result["cross_validation"]["f2"]["status"] == "required"
    assert "f2" in result["decision_slots"]["slot-1"]["quarantined_finding_ids"]


def test_distinct_cluster_corroboration_lifts_quarantine() -> None:
    first = quarantine_chain(RecursiveSearchConfig(max_depth=5, low_confidence_threshold=0.7))

    result = apply_research_results(
        first,
        (
            finding(
                "f3",
                anchors=(("source", "u10"), ("source", "u11")),
                contradictions=("c10",),
                claim=CLAIM_A,
                research_node_id="root:slot-1",
            ),
        ),
    )

    assert "f3" not in result["decision_slots"]["slot-1"]["quarantined_finding_ids"]
    assert result["cross_validation"]["f2"]["status"] == "corroborated"
    assert "f2" not in result["decision_slots"]["slot-1"]["quarantined_finding_ids"]


def test_quarantined_findings_keep_residual_risk_positive() -> None:
    state = initialize_research_state(
        round_id="round-h3a",
        tree_id="tree-h3a",
        decision_slots=slots("P1"),
        baseline_findings=(finding("f1", anchors=(("source", "u1"),), continuations=("q1",)),),
        config=RecursiveSearchConfig(max_depth=5, low_confidence_threshold=0.95),
    )
    result = apply_research_results(
        state,
        (finding("f2", anchors=(("source", "u1"), ("source", "u2")), continuations=("q2",)),),
    )

    assert result["decision_slots"]["slot-1"]["quarantined_finding_ids"] == ["f2"]
    assert result["decision_slots"]["slot-1"]["residual_risk"] > 0


def test_zero_signal_completeness_gets_marginal_damping() -> None:
    state = initialize_research_state(
        round_id="round-m4",
        tree_id="tree-m4",
        decision_slots=slots("P1"),
        baseline_findings=(finding("f1", anchors=(("source", "u1"),), continuations=("q1",)),),
        config=RecursiveSearchConfig(max_depth=5),
    )
    first = apply_research_results(
        state, (finding("f2", anchors=(("source", "u1"), ("source", "u2")), continuations=("q2",)),)
    )

    def node(state_, question):
        return [n for n in state_["nodes"].values() if n["question"] == question][0]

    assert node(first, "q2")["damping"] == pytest.approx(0.275)

    result = apply_research_results(
        first, (finding("f3", anchors=(("source", "u1"), ("source", "u2")), continuations=("q3",)),)
    )

    assert node(result, "q3")["damping"] == pytest.approx(0.32)


def test_missing_source_quality_defaults_conservative() -> None:
    state = initialize_research_state(
        round_id="round-m7",
        tree_id="tree-m7",
        decision_slots={"slot-1": {"question": "Q?", "priority": "P1", "uncertainty": "medium"}},
    )

    assert state["nodes"]["root:slot-1"]["confidence"] == 0.5
    assert state["recursion_receipt"]["confidence"]["min"] == 0.5


def per_slot_novelty_state():
    decision_slots = slots("P1", "P1")
    return initialize_research_state(
        round_id="round-m6",
        tree_id="tree-m6",
        decision_slots=decision_slots,
        baseline_findings=(
            finding("fa1", "slot-1", anchors=(("source", "a1"),)),
            finding("fa2", "slot-1", anchors=(("source", "a2"),), continuations=("qa",)),
            finding("fb1", "slot-2", anchors=(("source", "b1"),)),
            finding("fb2", "slot-2", anchors=(("source", "b2"),), continuations=("qb", "qb-stale")),
        ),
        config=RecursiveSearchConfig(max_depth=5),
    )


def test_per_slot_novelty_attribution_gates_saturation() -> None:
    state = per_slot_novelty_state()
    result = apply_research_results(
        state,
        (
            finding("fa3", "slot-1", anchors=(("source", "a1"), ("source", "a3")), continuations=("qa2",)),
            finding("fb3", "slot-2", anchors=(("source", "b1"), ("source", "b2"))),
        ),
    )

    stale = [n for n in result["nodes"].values() if n["question"] == "qb-stale"]
    fresh = [n for n in result["nodes"].values() if n["question"] == "qa2"]
    assert len(stale) == 1 and len(fresh) == 1
    assert stale[0]["status"] == "deferred"
    assert stale[0]["terminal_reason"] == "evidence-saturated"
    assert fresh[0]["status"] == "frontier"
    assert fresh[0]["terminal_reason"] is None
    assert result["recursion_receipt"]["terminal_reason_distribution"] == {"evidence-saturated": 1}


def test_saturation_gates_on_measured_intent_coverage() -> None:
    state = initialize_research_state(
        round_id="round-cov",
        tree_id="tree-cov",
        decision_slots=slots("P1"),
        baseline_findings=(finding("f1", anchors=(("source", "u1"),), continuations=("q1",)),),
        config=RecursiveSearchConfig(max_depth=5),
    )
    comparison = {
        "comparison_id": "comparison-cov-1",
        "provider_fanout": 2,
        "duplicates": 1,
        "captures": 3,
        "coverage_met": 0,
        "contradictions": (),
    }
    first = apply_research_results(
        state,
        (
            finding(
                "f2", anchors=(("source", "u1"), ("source", "u2")), continuations=("q2",), search_comparison=comparison
            ),
        ),
    )
    result = apply_research_results(
        first,
        (
            finding(
                "f3",
                anchors=(("source", "u1"), ("source", "u2")),
                search_comparison=comparison,
                research_node_id="root:slot-1",
            ),
        ),
    )

    assert result["delta_history"][-1]["duplicate_only"] is True
    assert result["recursion_receipt"]["dedup_ratio"] == pytest.approx(1 / 3)
    live = [n for n in result["nodes"].values() if n["question"] == "q2"]
    assert len(live) == 1
    assert live[0]["status"] == "frontier"
    assert live[0]["terminal_reason"] is None


def test_tree_state_schema_bumped_to_two() -> None:
    state = initialize_research_state(
        round_id="round-l8",
        tree_id="tree-l8",
        decision_slots=slots("P1"),
    )

    assert state["schema"] == 2
    with pytest.raises(Exception, match="schema"):
        validate_tree_state_payload({**state, "schema": 1})
