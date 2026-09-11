"""Risk-scaled closure gates (issue #528).

Scenarios map 1:1 to openspec/changes/risk-scaled-gates/specs: closure
blocker subsets scale by slot priority (P0 full set, P1 middle set, P2
minimal set), RecursiveSearchConfig scales by task profile, and the
irreversible/authority gates never scale.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

from research_tree import (
    RecursiveSearchConfig,
    ResearchTreeStateError,
    apply_research_results,
    finalize_research_delivery,
    initialize_research_state,
)
from research_tree.independent_review import (
    IndependentReviewError,
    validate_alignment_verification_payload,
)
from research_tree.recursive_search import register_deliverable_quality_review
from research_tree.tree_state import validate_phase_transition

SOURCE_A = "https://example.test/primary"
SOURCE_B = "https://example.test/corroborating"


def finding(finding_id: str, *, anchor: str, sources: list[dict[str, object]] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": finding_id,
        "decision_slot_id": "slot-quick",
        "observations": [{"claim": "The quick answer holds.", "anchor": {"kind": "source", "ref": anchor}}],
        "option_effects": [],
        "remaining_uncertainties": [],
        "research_continuations": [],
    }
    if sources is not None:
        payload["sources"] = sources
    return payload


def slot_payload(*, priority: str, landscape_gates: bool | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "open",
        "priority": priority,
        "uncertainty": "medium",
        "question": "Which citation best supports the quick answer?",
        "validation": {"oracle": "An independent oracle confirms the quick answer."},
    }
    if landscape_gates is not None:
        payload["landscape_gates"] = landscape_gates
    return payload


def drilldown_nodes(state: dict[str, object], source_ref: str) -> list[dict[str, object]]:
    nodes = state["nodes"]
    assert isinstance(nodes, dict)
    return [
        node
        for node in nodes.values()
        if isinstance(node, dict)
        and node["action_kind"] == "deep_dive"
        and source_ref in str(node["question"])
        and "mechanism" in str(node["oracle"])
    ]


def test_p2_slot_closes_without_selection_grade_blockers() -> None:
    state = initialize_research_state(
        round_id="round-p2-minimal",
        tree_id="research-tree",
        decision_slots={"slot-quick": slot_payload(priority="P2")},
        # Quarantine mechanics are covered by their own suite; this test
        # isolates the blocker-subset selection.
        config=RecursiveSearchConfig(low_confidence_threshold=0.0),
    )
    state["decision_slots"]["slot-quick"]["validation_passed"] = True

    result = apply_research_results(
        state,
        (
            finding("finding-p2-a", anchor=SOURCE_A, sources=[{"ref": SOURCE_A, "depth": "snippet"}]),
            finding("finding-p2-b", anchor=SOURCE_B),
        ),
    )

    slot = result["decision_slots"]["slot-quick"]
    assert slot["closure_blockers"] == []
    # Issue #494/#495 producers stay intact: the drill-down is still scheduled.
    scheduled = drilldown_nodes(result, SOURCE_A)
    assert scheduled and all(node["mandatory"] for node in scheduled)
    assert scheduled[0]["status"] == "frontier"


def test_p0_slot_keeps_full_blocker_set() -> None:
    state = initialize_research_state(
        round_id="round-p0-full",
        tree_id="research-tree",
        decision_slots={"slot-quick": slot_payload(priority="P0")},
        config=RecursiveSearchConfig(low_confidence_threshold=0.0),
    )
    state["decision_slots"]["slot-quick"]["validation_passed"] = True

    result = apply_research_results(
        state,
        (
            finding("finding-p0-a", anchor=SOURCE_A, sources=[{"ref": SOURCE_A, "depth": "snippet"}]),
            finding("finding-p0-b", anchor=SOURCE_B),
        ),
    )

    slot = result["decision_slots"]["slot-quick"]
    assert any(
        "shallow source depth blocks landscape closure" in blocker and SOURCE_A in blocker
        for blocker in slot["closure_blockers"]
    )
    assert any("frontier action(s) remain" in blocker for blocker in slot["closure_blockers"])
    assert all(
        "closure candidate requires coordinator assessment" not in blocker for blocker in slot["closure_blockers"]
    )


def test_p1_slot_runs_middle_blocker_set() -> None:
    state = initialize_research_state(
        round_id="round-p1-middle",
        tree_id="research-tree",
        decision_slots={"slot-quick": slot_payload(priority="P1")},
        config=RecursiveSearchConfig(low_confidence_threshold=0.0),
    )

    slot = state["decision_slots"]["slot-quick"]
    assert slot["closure_blockers"] == [
        "slot-quick: independent evidence is insufficient",
        "slot-quick: validation oracle has not passed",
    ]

    state["decision_slots"]["slot-quick"]["validation_passed"] = True
    ready = apply_research_results(
        state,
        (finding("finding-p1-a", anchor=SOURCE_A), finding("finding-p1-b", anchor=SOURCE_B)),
    )

    slot = ready["decision_slots"]["slot-quick"]
    assert slot["closure_blockers"] == ["slot-quick: closure candidate requires coordinator assessment"]


def test_p1_slot_can_opt_back_into_landscape_gates() -> None:
    state = initialize_research_state(
        round_id="round-p1-opt-in",
        tree_id="research-tree",
        decision_slots={"slot-quick": slot_payload(priority="P1", landscape_gates=True)},
        config=RecursiveSearchConfig(low_confidence_threshold=0.0),
    )
    assert state["decision_slots"]["slot-quick"]["landscape_gates"] is True
    state["decision_slots"]["slot-quick"]["validation_passed"] = True

    result = apply_research_results(
        state,
        (finding("finding-p1-opt", anchor=SOURCE_A, sources=[{"ref": SOURCE_A, "depth": "snippet"}]),),
    )

    slot = result["decision_slots"]["slot-quick"]
    assert any(
        "shallow source depth blocks landscape closure" in blocker and SOURCE_A in blocker
        for blocker in slot["closure_blockers"]
    )
    assert any("frontier action(s) remain" in blocker for blocker in slot["closure_blockers"])


def test_profile_defaults_load_and_explicit_fields_win() -> None:
    standard = RecursiveSearchConfig()
    assert (
        standard.profile,
        standard.minimum_evidence,
        standard.max_depth,
        standard.transition_budget,
    ) == ("standard", 2, 5, 64)
    small = RecursiveSearchConfig(profile="small")
    assert (small.profile, small.minimum_evidence, small.max_depth, small.transition_budget) == ("small", 1, 3, 16)
    deep = RecursiveSearchConfig(profile="deep")
    assert (deep.profile, deep.minimum_evidence, deep.max_depth, deep.transition_budget) == ("deep", 3, 8, 128)
    overridden = RecursiveSearchConfig(profile="small", transition_budget=32)
    assert overridden.transition_budget == 32
    assert overridden.max_depth == 3
    assert RecursiveSearchConfig(**asdict(small)) == small


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown profile"):
        RecursiveSearchConfig(profile="huge")


def test_profile_scales_the_evidence_floor_at_evaluation_time() -> None:
    def floor_blockers(profile: str) -> list[str]:
        state = initialize_research_state(
            round_id=f"round-floor-{profile}",
            tree_id="research-tree",
            decision_slots={"slot-quick": slot_payload(priority="P2")},
            config=RecursiveSearchConfig(profile=profile, low_confidence_threshold=0.0),
        )
        state["decision_slots"]["slot-quick"]["validation_passed"] = True
        fed = apply_research_results(state, (finding(f"finding-floor-{profile}", anchor=SOURCE_A),))
        slot = fed["decision_slots"]["slot-quick"]
        assert isinstance(slot["closure_blockers"], list)
        return list(slot["closure_blockers"])

    small = floor_blockers("small")
    assert "slot-quick: independent evidence is insufficient" not in small
    assert "slot-quick: independent evidence is insufficient" in floor_blockers("standard")


def test_never_scaled_gates_still_fire_on_a_p2_only_tree(tmp_path: Path) -> None:
    """ADR (risk-scaled-gates/design.md): authority fingerprint, phase
    transitions, digest binding, and evidence strict mode never scale with
    slot priority. Strict evidence mode is enforced behind the closure
    assessor and decision ledger (pinned by their own suites); the three
    gates visible at this layer are asserted on a P2-only tree."""

    state = initialize_research_state(
        round_id="round-never-scaled",
        tree_id="research-tree",
        decision_slots={"slot-quick": slot_payload(priority="P2")},
    )
    state["decision_slots"]["slot-quick"]["status"] = "closed"
    technical, human = tmp_path / "technical.md", tmp_path / "human.md"
    technical.write_text("# Technical\n# Evidence\n# Risks\n\n" + "x" * 1100, encoding="utf-8")
    human.write_text("# Human\n# Reasoning\n\n" + "x" * 600, encoding="utf-8")
    delivered = finalize_research_delivery(state, technical_report=technical, human_report=human)

    # Digest binding: a stale review cannot pass, even for a P2-only tree.
    stale = {
        "schema": 1,
        "id": "dqr-p2",
        "round_id": delivered["round_id"],
        "verifier_identity": "subagent-session-1",
        "session_context": "main-session-1",
        "manifest_digests": {kind: "0" * 64 for kind in ("technical_research_package", "human_research_report")},
        "per_oracle": {"quick-oracle": {"verdict": "satisfied", "basis": "Looks fine."}},
        "named_gaps": [],
    }
    with pytest.raises(ValueError, match="stale"):
        register_deliverable_quality_review(delivered, stale)

    # Authority fingerprint: a malformed fingerprint is rejected regardless
    # of any slot priority.
    with pytest.raises(IndependentReviewError, match="authority_fingerprint"):
        validate_alignment_verification_payload(
            {
                "schema": 1,
                "id": "av-1",
                "round_id": "round-never-scaled",
                "projection_ref": {
                    "round_id": "round-never-scaled",
                    "artifact_id": "alignment-projection",
                    "revision": 1,
                },
                "authority_fingerprint": "0" * 63,
                "verifier_identity": "verifier-1",
                "session_context": "main-1",
                "understood": {
                    "outcome": "The strategy outcome.",
                    "scope": "The strategy scope.",
                    "authority": "The strategy authority.",
                    "success_oracles": [{"id": "o1", "understanding": "Understood."}],
                },
                "discrepancies": [],
            }
        )

    # Phase transitions: the tree phase graph ignores priority entirely.
    with pytest.raises(ResearchTreeStateError, match="illegal tree phase transition"):
        validate_phase_transition("research", "delivery")
