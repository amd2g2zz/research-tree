from __future__ import annotations

import pytest

from research_tree import RecursiveSearchConfig, apply_research_results, initialize_research_state

CLAIM = "The mechanism requires independent corroboration."


def finding(
    finding_id: str,
    slot_id: str = "slot-1",
    *,
    anchors: tuple[tuple[str, str], ...] = (("source", "u1"),),
    continuations: tuple[str, ...] = (),
    claim: str = CLAIM,
    research_node_id: str | None = None,
    contradictions: tuple[str, ...] = (),
    verification: dict[str, object] | None = None,
    search_comparison: dict[str, object] | None = None,
    source_quality: str | None = "high",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": finding_id,
        "decision_slot_id": slot_id,
        "observations": [{"claim": claim, "anchor": {"kind": kind, "ref": ref}} for kind, ref in anchors],
        "research_continuations": [
            {
                "kind": "deep_dive",
                "question": question,
                "evidence_needed": "Corroborating evidence.",
                "oracle": "The question is answered with anchored evidence.",
                "estimated_cost": 1,
            }
            for question in continuations
        ],
    }
    if research_node_id is not None:
        payload["research_node_id"] = research_node_id
    if contradictions:
        payload["contradictions"] = list(contradictions)
    if verification is not None:
        payload["verification"] = verification
    if search_comparison is not None:
        payload["search_comparison"] = search_comparison
    if source_quality is not None:
        payload["source_quality"] = source_quality
    return payload


def slots(*priorities: str) -> dict[str, dict[str, object]]:
    labels = priorities or ("P1",)
    return {
        f"slot-{index}": {
            "status": "open",
            "priority": label,
            "uncertainty": "medium",
            "question": "Which mechanism explains the observed behavior?",
        }
        for index, label in enumerate(labels, 1)
    }


def saturated_flow():
    slot_id = "slot-1"
    state = initialize_research_state(
        round_id="round-saturation",
        tree_id="tree-saturation",
        decision_slots=slots("P1"),
        baseline_findings=(finding("f1", slot_id, anchors=(("source", "u1"),), continuations=("q-deep",)),),
        config=RecursiveSearchConfig(max_depth=5),
    )
    open_node = next(node for node in state["nodes"].values() if node["question"] == "q-deep")
    assert open_node["status"] == "frontier"
    assert open_node["terminal_reason"] is None
    first = apply_research_results(
        state,
        (
            finding(
                "f2",
                slot_id,
                anchors=(("source", "u1"), ("source", "u2")),
                continuations=("q-wide-a", "q-wide-b"),
            ),
        ),
    )
    assert first["delta_history"][-1]["realized_delta"] > 0
    return slot_id, first


def test_saturated_search_stops_before_max_depth() -> None:
    slot_id, state = saturated_flow()

    result = apply_research_results(
        state,
        (finding("f3", slot_id, anchors=(("source", "u1"), ("source", "u2"))),),
    )

    deferred = [node for node in result["nodes"].values() if node["terminal_reason"] == "evidence-saturated"]
    assert len(deferred) == 1
    assert deferred[0]["status"] == "deferred"
    assert deferred[0]["depth"] < 5
    receipt = result["recursion_receipt"]
    assert receipt["terminal_reason_distribution"] == {"evidence-saturated": 1}
    assert result["delta_history"][-1]["duplicate_only"] is True


def test_live_contradictions_continue_to_maximum_depth_guardrail() -> None:
    slot_id = "slot-1"
    state = initialize_research_state(
        round_id="round-guardrail",
        tree_id="tree-guardrail",
        decision_slots=slots("P1"),
        baseline_findings=(finding("f1", slot_id, anchors=(("source", "u1"),), continuations=("q-deep",)),),
        config=RecursiveSearchConfig(max_depth=5),
    )
    current = state
    for index in range(1, 6):
        current = apply_research_results(
            current,
            (
                finding(
                    f"f{index + 1}",
                    slot_id,
                    anchors=(("source", "u1"), ("source", f"u{index + 1}")),
                    continuations=(f"q{index}",),
                    contradictions=(f"contra-{index}",),
                ),
            ),
        )

    guarded = [
        node for node in current["nodes"].values() if node["terminal_reason"] == "maximum depth guardrail reached"
    ]
    assert len(guarded) == 1
    assert guarded[0]["depth"] == 6
    assert "slot-1" in guarded[0]["id"]
    assert current["recursion_receipt"]["terminal_reason_distribution"] == {"maximum depth guardrail reached": 1}
    assert "evidence-saturated" not in current["recursion_receipt"]["terminal_reason_distribution"]


def high_low_quality_state(config: RecursiveSearchConfig):
    decision_slots = slots("P1", "P1")
    return initialize_research_state(
        round_id="round-damping",
        tree_id="tree-damping",
        decision_slots=decision_slots,
        baseline_findings=(
            finding("fh1", "slot-1", anchors=(("source", "h1"),), continuations=("qh-1",)),
            finding("fl1", "slot-2", anchors=(("source", "l1"),), continuations=("ql-1",)),
        ),
        config=config,
    )


def node_by_question(state, question):
    return next(node for node in state["nodes"].values() if node["question"] == question)


def test_confidence_damping_separates_high_and_low_quality_recursions() -> None:
    state = high_low_quality_state(RecursiveSearchConfig(max_depth=5))
    result = apply_research_results(
        state,
        (
            finding("fh2", "slot-1", anchors=(("source", "h1"), ("source", "h2")), continuations=("qh-2",)),
            finding("fl2", "slot-2", anchors=(("source", "l1"),), continuations=("ql-2",)),
        ),
    )

    high = node_by_question(result, "qh-2")
    low = node_by_question(result, "ql-2")

    assert high["depth"] == low["depth"] == 2
    assert high["damping"] == pytest.approx(0.275)
    assert low["damping"] == pytest.approx(0.32)
    assert high["confidence"] == pytest.approx(0.77 * 0.725)
    assert low["confidence"] == pytest.approx(0.77 * 0.68)
    assert high["damping"] < low["damping"]
    assert high["confidence"] > low["confidence"]


def test_confidence_strictly_decreases_within_declared_band() -> None:
    state = high_low_quality_state(RecursiveSearchConfig(max_depth=5))
    result = apply_research_results(
        state,
        (
            finding("fh2", "slot-1", anchors=(("source", "h1"), ("source", "h2")), continuations=("qh-2",)),
            finding("fl2", "slot-2", anchors=(("source", "l1"),), continuations=("ql-2",)),
        ),
    )

    for node in result["nodes"].values():
        parent = result["nodes"].get(node["parent_id"]) if node["parent_id"] else None
        if parent is None:
            continue
        assert node["confidence"] < parent["confidence"]
        assert 0.05 <= node["damping"] <= 0.35

    receipt = result["recursion_receipt"]
    assert receipt["confidence"]["damping_min"] == 0.05
    assert receipt["confidence"]["damping_max"] == 0.35
    assert sum(receipt["confidence"]["quality_weights"].values()) == pytest.approx(1.0)
    assert receipt["confidence"]["low_confidence_threshold"] == 0.35


def quarantine_flow():
    state = initialize_research_state(
        round_id="round-quarantine",
        tree_id="tree-quarantine",
        decision_slots=slots("P1"),
        baseline_findings=(finding("f1", anchors=(("source", "u1"),), continuations=("q1",)),),
        config=RecursiveSearchConfig(max_depth=5, low_confidence_threshold=0.95),
    )
    first = apply_research_results(
        state, (finding("f2", anchors=(("source", "u1"), ("source", "u2")), continuations=("q2",)),)
    )
    assert first["cross_validation"]["f2"]["status"] == "required"
    assert first["decision_slots"]["slot-1"]["quarantined_finding_ids"] == ["f2"]
    assert first["recursion_receipt"]["quarantine_count"] == 1
    return first


def test_below_threshold_findings_are_quarantined_from_satisfied_evidence() -> None:
    first = quarantine_flow()

    second = apply_research_results(
        first, (finding("f3", anchors=(("source", "u1"), ("source", "u2")), research_node_id="q2"),)
    )
    third = apply_research_results(
        second,
        (finding("f4", anchors=(("source", "u1"), ("source", "u2")), research_node_id="root:slot-1"),),
    )
    triangulate_id = next(
        node_id
        for node_id, node in third["nodes"].items()
        if "Triangulate" in node["question"] and node["status"] == "frontier"
    )

    result = apply_research_results(
        third, (finding("f5", anchors=(("source", "u1"), ("source", "u2")), research_node_id=triangulate_id),)
    )

    assert result["status"] == "searching"
    assert any("Triangulate" in result["nodes"][node_id]["question"] for node_id in result["frontier_node_ids"])
    assert len(result["decision_slots"]["slot-1"]["quarantined_finding_ids"]) == 4
    assert result["recursion_receipt"]["quarantine_count"] == 4
    assert result["recursion_receipt"]["cross_validation_records"] == 4


def test_explicit_verification_pass_lifts_quarantine() -> None:
    first = quarantine_flow()

    result = apply_research_results(
        first,
        (
            finding(
                "f3",
                anchors=(("source", "u3"),),
                research_node_id="q2",
                verification={"status": "passed", "target_finding_id": "f2", "reason": "independent-oracle"},
            ),
        ),
    )

    assert result["cross_validation"]["f2"]["status"] == "verified"
    assert "f2" not in result["decision_slots"]["slot-1"]["quarantined_finding_ids"]
    assert "independent evidence is insufficient" not in (result["stop_reason"] or "")
    assert result["recursion_receipt"]["quarantine_count"] == 1
    assert result["recursion_receipt"]["cross_validation_records"] == 2


def test_cross_validation_failure_is_recorded_objectively() -> None:
    first = quarantine_flow()

    result = apply_research_results(
        first,
        (
            finding(
                "f3",
                anchors=(("source", "u3"),),
                research_node_id="q2",
                verification={"status": "failed", "target_finding_id": "f2", "reason": "oracle-mismatch"},
            ),
        ),
    )

    record = result["cross_validation"]["f2"]
    assert record["status"] == "failed"
    assert record["attempts"] == 1
    assert record["reason"] == "oracle-mismatch"
    assert "f2" in result["decision_slots"]["slot-1"]["quarantined_finding_ids"]
    assert result["recursion_receipt"]["cross_validation_failures"] == 1


def test_transition_budget_reports_budget_exhausted() -> None:
    state = initialize_research_state(
        round_id="round-budget",
        tree_id="tree-budget",
        decision_slots=slots("P1"),
        baseline_findings=(finding("f1", anchors=(("source", "u1"),), continuations=("q1",)),),
        config=RecursiveSearchConfig(max_depth=5, transition_budget=1),
    )

    result = apply_research_results(
        state,
        (
            finding(
                "f2",
                anchors=(("source", "u1"), ("source", "u2")),
                continuations=("q2",),
                contradictions=("live-contradiction",),
            ),
        ),
    )

    exhausted = [node for node in result["nodes"].values() if node["terminal_reason"] == "budget-exhausted"]
    assert len(exhausted) == 1
    assert exhausted[0]["status"] == "deferred"
    assert exhausted[0]["depth"] == 2
    assert result["recursion_receipt"]["terminal_reason_distribution"] == {"budget-exhausted": 1}


def test_receipt_aggregates_cross_comparison_signals() -> None:
    state = initialize_research_state(
        round_id="round-receipt",
        tree_id="tree-receipt",
        decision_slots=slots("P1"),
        baseline_findings=(finding("f1", anchors=(("source", "u1"),), continuations=("q1",)),),
        config=RecursiveSearchConfig(max_depth=5),
    )

    result = apply_research_results(
        state,
        (
            finding(
                "f2",
                anchors=(("source", "u1"), ("source", "u2")),
                continuations=("q2",),
                search_comparison={
                    "provider_fanout": 2,
                    "duplicates": 1,
                    "captures": 3,
                    "contradictions": ("cc-1",),
                },
            ),
        ),
    )

    receipt = result["recursion_receipt"]
    assert receipt["provider_fanout"] == 2
    assert receipt["dedup_ratio"] == pytest.approx(1 / 3, rel=1e-4)
    assert result["decision_slots"]["slot-1"]["contradiction_refs"] == ["cc-1"]
    assert receipt["quarantine_count"] == 0
    assert receipt["terminal_reason_distribution"] == {}
    assert set(receipt["confidence"]) >= {"min", "max", "count"}
