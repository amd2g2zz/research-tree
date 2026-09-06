"""Deliverable-quality gate tests (issue #495).

Scenarios map 1:1 to openspec/changes/deliverable-quality-gate/specs:
delivery-pending requires a passing, digest-bound, independent quality
review; failed reviews reopen named remediation work; pruned work stays
queryable; saturation requires measured coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research_tree import (
    finalize_research_delivery,
    initialize_research_state,
    prune_research_state,
)
from research_tree.independent_review import (
    DELIVERABLE_QUALITY_REVIEW_KIND,
    IndependentReviewError,
    validate_deliverable_quality_review_payload,
)
from research_tree.recursive_search import register_deliverable_quality_review


def slots() -> dict[str, dict[str, object]]:
    return {
        "slot-depth": {
            "status": "open",
            "priority": "P0",
            "uncertainty": "high",
            "question": "How does the mechanism under research actually work?",
            "validation": {"oracle": "The mechanism is explained beyond the README."},
        }
    }


def closed_state(round_id: str):
    state = initialize_research_state(round_id=round_id, tree_id="research-tree", decision_slots=slots())
    state["decision_slots"]["slot-depth"]["status"] = "closed"
    return state


def write_reports(tmp_path: Path) -> tuple[Path, Path]:
    technical, human = tmp_path / "technical.md", tmp_path / "human.md"
    technical.write_text("# Technical\n# Evidence\n# Risks\n\n" + "x" * 1100, encoding="utf-8")
    human.write_text("# Human\n# Reasoning\n\n" + "x" * 600, encoding="utf-8")
    return technical, human


def manifest_digests(state) -> dict[str, str]:
    return {
        kind: manifest["sha256"]
        for kind, manifest in state["deliverables"].items()
        if isinstance(manifest, dict) and manifest.get("sha256")
    }


def review_payload(
    state,
    *,
    verdicts: dict[str, str] | None = None,
    gaps: list[dict[str, object]] | None = None,
    identity: bool = True,
) -> dict[str, object]:
    verdicts = verdicts or {"mechanism-oracle": {"verdict": "satisfied", "basis": "Deliverable explains it."}}
    payload: dict[str, object] = {
        "schema": 1,
        "id": "dqr-1",
        "round_id": state["round_id"],
        "manifest_digests": manifest_digests(state),
        "per_oracle": verdicts,
        "named_gaps": list(gaps or ()),
    }
    if identity:
        payload["verifier_identity"] = "subagent-session-1"
        payload["session_context"] = "main-session-1"
    return payload


def test_manifests_without_quality_review_stay_blocked(tmp_path: Path) -> None:
    technical, human = write_reports(tmp_path)
    state = finalize_research_delivery(
        closed_state("round-gate-blocked"), technical_report=technical, human_report=human
    )
    assert state["status"] == "blocked"
    assert "deliverable-quality" in state["stop_reason"]
    assert "coordinator" in state["stop_reason"]


def test_passing_quality_review_flips_delivery_pending(tmp_path: Path) -> None:
    technical, human = write_reports(tmp_path)
    state = finalize_research_delivery(
        closed_state("round-gate-pass"), technical_report=technical, human_report=human
    )
    gated = register_deliverable_quality_review(state, review_payload(state))
    assert gated["deliverable_quality_gate"]["status"] == "passed"
    assert gated["status"] == "delivery_pending"
    assert "coordinator" in gated["stop_reason"]


def test_stale_quality_review_is_rejected(tmp_path: Path) -> None:
    technical, human = write_reports(tmp_path)
    state = finalize_research_delivery(
        closed_state("round-gate-stale"), technical_report=technical, human_report=human
    )
    payload = review_payload(state)
    payload["manifest_digests"] = {kind: "0" * 64 for kind in payload["manifest_digests"]}
    with pytest.raises(ValueError, match="stale"):
        register_deliverable_quality_review(state, payload)


def test_non_independent_review_is_rejected(tmp_path: Path) -> None:
    technical, human = write_reports(tmp_path)
    state = finalize_research_delivery(
        closed_state("round-gate-identity"), technical_report=technical, human_report=human
    )
    with pytest.raises(IndependentReviewError):
        validate_deliverable_quality_review_payload(review_payload(state, identity=False))


def test_failed_review_creates_remediation_work(tmp_path: Path) -> None:
    technical, human = write_reports(tmp_path)
    state = finalize_research_delivery(
        closed_state("round-gate-fail"), technical_report=technical, human_report=human
    )
    failed = register_deliverable_quality_review(
        state,
        review_payload(
            state,
            verdicts={"mechanism-oracle": {"verdict": "unmet", "basis": "README restated, no mechanism."}},
            gaps=[
                {
                    "description": "Explain the mechanism beyond the README",
                    "target_slot_id": "slot-depth",
                    "oracle": "The mechanism is explained with code-level evidence.",
                }
            ],
        ),
    )
    assert failed["deliverable_quality_gate"]["status"] == "failed"
    assert failed["status"] == "searching"
    assert "1 named gap" in failed["stop_reason"]
    slot = failed["decision_slots"]["slot-depth"]
    assert slot["status"] == "researching"
    remediation = [n for n in failed["nodes"].values() if n["action_kind"] == "remediation"]
    assert len(remediation) == 1
    node = remediation[0]
    assert node["mandatory"] is True
    assert "mechanism" in node["question"]
    assert failed["frontier_node_ids"] == [node["id"]]
    assert failed["deliverable_quality_gate"]["remediation_node_ids"] == [node["id"]]


def test_gap_can_revive_discarded_node(tmp_path: Path) -> None:
    state = initialize_research_state(round_id="round-gate-revive", tree_id="research-tree", decision_slots=slots())
    root = state["nodes"][state["frontier_node_ids"][0]]
    victim = dict(root, id="node:slot-depth:reviveme", mandatory=False, selection_value=0.05, depth=1)
    state["nodes"][victim["id"]] = victim
    state["frontier_node_ids"].append(victim["id"])
    pruned = prune_research_state(state)
    assert pruned["nodes"][victim["id"]]["status"] == "deferred"
    entry = next(e for e in pruned["discarded_evidence"] if e["node_id"] == victim["id"])

    technical, human = write_reports(tmp_path)
    gated_state = finalize_research_delivery(
        {**pruned, "decision_slots": {**pruned["decision_slots"], "slot-depth": {**pruned["decision_slots"]["slot-depth"], "status": "closed"}}},
        technical_report=technical,
        human_report=human,
    )
    revived = register_deliverable_quality_review(
        gated_state,
        review_payload(
            gated_state,
            verdicts={"mechanism-oracle": {"verdict": "unmet", "basis": "Depth was discarded too early."}},
            gaps=[
                {
                    "description": "Re-run the discarded drill-down",
                    "target_slot_id": "slot-depth",
                    "oracle": victim["oracle"],
                    "revive_node_id": victim["id"],
                }
            ],
        ),
    )
    node = revived["nodes"][victim["id"]]
    assert node["status"] == "frontier"
    assert node["terminal_reason"] is None
    assert node["mandatory"] is True
    assert victim["id"] in revived["frontier_node_ids"]
    assert any(e["node_id"] == victim["id"] for e in revived["discarded_evidence"])


def test_pruned_nodes_are_recorded_as_discarded_evidence() -> None:
    state = initialize_research_state(round_id="round-gate-discard", tree_id="research-tree", decision_slots=slots())
    root = state["nodes"][state["frontier_node_ids"][0]]
    weak = dict(root, id="node:slot-depth:weak", mandatory=False, selection_value=0.05, depth=1)
    state["nodes"][weak["id"]] = weak
    state["frontier_node_ids"].append(weak["id"])
    pruned = prune_research_state(state)
    entries = [e for e in pruned["discarded_evidence"] if e["node_id"] == weak["id"]]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["terminal_reason"] == "selection value below threshold"
    assert entry["decision_slot_id"] == "slot-depth"
    assert entry["decision_oracle"]
    assert entry["evidence_needed"]
    assert entry["selection_value"] == 0.05
    pruned["nodes"][weak["id"]]["status"] = "frontier"
    pruned["frontier_node_ids"].append(weak["id"])
    repruned = prune_research_state(pruned)
    assert len([e for e in repruned["discarded_evidence"] if e["node_id"] == weak["id"]]) == 1


def test_saturation_requires_measured_coverage() -> None:
    state = initialize_research_state(round_id="round-gate-cov", tree_id="research-tree", decision_slots=slots())
    slot = state["decision_slots"]["slot-depth"]
    slot["marginal_novelty"] = 0.0
    root = state["nodes"][state["frontier_node_ids"][0]]
    extra = dict(root, id="node:slot-depth:coverage", mandatory=False, selection_value=0.5, depth=1)
    state["nodes"][extra["id"]] = extra
    state["frontier_node_ids"].append(extra["id"])
    unmeasured = prune_research_state(state)
    assert unmeasured["nodes"][extra["id"]]["status"] == "frontier"
    slot["search_comparison"]["batches"] = {"b1": {"captures": 3, "duplicates": 0, "coverage_met": 1}}
    slot["search_comparison"]["coverage_met"] = 1
    measured = prune_research_state(unmeasured)
    assert measured["nodes"][extra["id"]]["status"] == "deferred"
    assert measured["nodes"][extra["id"]]["terminal_reason"] == "evidence-saturated"
    slot["search_comparison"]["coverage_met"] = 0
    unmet = prune_research_state(measured)
    fresh = dict(unmet["nodes"][extra["id"]], status="frontier")
    unmet["nodes"][extra["id"]] = fresh
    unmet["frontier_node_ids"].append(extra["id"])
    still_open = prune_research_state(unmet)
    assert still_open["nodes"][extra["id"]]["status"] == "frontier"


def test_review_kind_is_declared() -> None:
    assert DELIVERABLE_QUALITY_REVIEW_KIND == "deliverable-quality-review"
