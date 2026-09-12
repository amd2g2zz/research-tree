"""Score-gated alignment exit policy — issue #491 scenarios.

The turn cap (`MAX_TURNS`) must never silently export alignment to
reconnaissance: on the cap the controller emits an explicit
``alignment_incomplete`` blocked disposition naming the open high-impact
gaps and the exhausted-ask nodes, requiring user extension or an explicit
waive. Exit itself is gated by a deterministic alignment score over the
#496 graph state, not by the turn counter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research_tree.alignment_graph import (
    ALIGNMENT_SCORE_EXIT_THRESHOLD,
    AlignmentGraphError,
    AlignmentGraphStore,
)


def _store(tmp_path: Path) -> AlignmentGraphStore:
    store = AlignmentGraphStore(tmp_path / "alignment.db")
    store.initialize("run-491")
    return store


def _merge_gaps(store: AlignmentGraphStore, *specs: tuple[str, int]) -> None:
    store.merge(
        {
            "nodes": [
                {
                    "id": gap_id,
                    "type": "unknown",
                    "statement": f"Requester-only dimension {gap_id}.",
                    "status": "candidate",
                    "impact": impact,
                    "human_only": True,
                    "confidence": "low",
                    "source": "agent",
                }
                for gap_id, impact in specs
            ]
        }
    )


def _ready_graph() -> dict[str, object]:
    """A structurally handoff-ready graph (no requester-only gap, no axis)."""
    required = {
        "goal": ("outcome", "Produce an implementation-driving technical strategy."),
        "use": ("intended_use", "Use the result to authorize and plan implementation."),
        "scope": ("scope_boundary", "Research and design only; no implementation yet."),
        "delivery": ("delivery", "Deliver a professional evidence-anchored technical package."),
        "authority": ("authority", "The agent owns autonomous research after confirmation."),
        "success": ("success_oracle", "Every P0 decision has evidence and a validation oracle."),
        "feasibility": ("feasibility", "The strategy is technically plausible in the stated environment."),
        "strategy": ("strategy", "Use recursive decision-risk research with independent validation."),
    }
    nodes: list[dict[str, object]] = [
        {
            "id": node_id,
            "type": node_type,
            "statement": statement,
            "status": "supported",
            "impact": 5,
            "human_only": False,
            "confidence": "high",
            "source": "joint",
        }
        for node_id, (node_type, statement) in required.items()
    ]
    nodes.extend(
        [
            {
                "id": "question-architecture",
                "type": "research_question",
                "statement": "Which architecture best satisfies the confirmed strategy?",
                "status": "candidate",
                "impact": 5,
                "human_only": False,
                "confidence": "low",
                "source": "joint",
                "oracle": "The leading architecture survives an independent executable validation.",
            },
            {
                "id": "evidence-recon",
                "type": "evidence",
                "statement": "Initial reconnaissance found a persisted coordinator pattern.",
                "status": "supported",
                "impact": 3,
                "human_only": False,
                "confidence": "medium",
                "source": "reconnaissance",
                "attributes": {"anchor": {"kind": "source", "ref": "https://example.test/coordinator"}},
            },
        ]
    )
    return {
        "nodes": nodes,
        "edges": [
            {
                "id": "edge-recon-supports",
                "source_id": "evidence-recon",
                "target_id": "question-architecture",
                "relation": "supports",
                "status": "active",
                "confidence": "medium",
                "provenance": "alignment reconnaissance turn 1",
            },
            {
                "id": "edge-recon-limits",
                "source_id": "evidence-recon",
                "target_id": "question-architecture",
                "relation": "limits",
                "status": "active",
                "confidence": "low",
                "provenance": "alignment reconnaissance turn 2",
            },
        ],
    }


def test_turn_cap_with_open_high_impact_gaps_names_them_instead_of_reconnaissance(tmp_path: Path) -> None:
    """Issue #491: the cap emits the blocked disposition; reconnaissance is gone."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5))
    # The user keeps answering; each answer opens a new direction (#496 axes
    # keep the node askable past its ask budget), so the dialogue is alive
    # the whole way to the cap.
    for turn in range(6):
        decision = store.plan()
        assert decision["action"] == "ask_one"
        assert decision["node_id"] == "gap-a"
        store.record("gap-a", "unchanged", f"fp-{turn}", new_axes=[f"direction the user opened {turn}"])

    decision = store.plan()
    assert decision["action"] == "alignment_incomplete"
    assert decision["action"] != "reconnaissance"
    assert "gap-a" in [node["node_id"] for node in decision["blocked_nodes"]]
    assert decision["exhausted_ask_nodes"] == ["gap-a"]
    assert decision["alignment_score"] < decision["alignment_exit_threshold"]
    assert decision["alignment_exit_threshold"] == ALIGNMENT_SCORE_EXIT_THRESHOLD
    assert decision["open_axes"]
    assert "waive" in decision["requires"]


def test_exhausted_high_impact_asks_escalate_instead_of_reconnaissance(tmp_path: Path) -> None:
    """Issue #491: MAX_ASKS_PER_NODE must not abandon a high-impact gap silently."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5))
    assert store.plan()["action"] == "ask_one"
    store.record("gap-a", "unchanged", "fp")
    assert store.plan()["action"] == "ask_one"
    store.record("gap-a", "unchanged", "fp")

    decision = store.plan()
    assert decision["action"] == "alignment_incomplete"
    assert decision["action"] != "reconnaissance"
    assert decision["exhausted_ask_nodes"] == ["gap-a"]
    assert "gap-a" in [node["node_id"] for node in decision["blocked_nodes"]]


def test_low_impact_exhausted_gap_keeps_stall_reconnaissance(tmp_path: Path) -> None:
    """The escalation boundary is high impact; a stalled low-impact gap keeps #496 behavior."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-minor", 2))
    assert store.plan()["action"] == "ask_one"
    store.record("gap-minor", "unchanged", "fp")
    assert store.plan()["action"] == "ask_one"
    store.record("gap-minor", "unchanged", "fp")

    decision = store.plan()
    assert decision["action"] == "reconnaissance"


def test_record_next_action_escalates_when_high_impact_asks_are_exhausted(tmp_path: Path) -> None:
    """record() must not advise reconnaissance where plan() would block (#491)."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5))
    store.plan()
    store.record("gap-a", "unchanged", "fp")
    store.plan()
    store.record("gap-a", "unchanged", "fp")

    third = store.record("gap-a", "unchanged", "fp")
    assert third["dialogue_mode"] == "stalled"
    assert third["next_action"] == "alignment_incomplete"


def test_alignment_score_gates_handoff_low_score_blocks_pressure_high_score_allows(tmp_path: Path) -> None:
    """Issue #491: exit follows the score, not the turn counter or user pressure."""
    store = _store(tmp_path)
    store.merge(_ready_graph())

    decision = store.plan()
    assert decision["action"] == "await_human_confirmation"
    assert decision["alignment_score"] == ALIGNMENT_SCORE_EXIT_THRESHOLD

    # The user raises a direction nobody explored, then pressures to proceed.
    store.record("goal", "unchanged", "fp-axis", new_axes=["What about the deployment environment?"])
    pressed = store.plan()
    assert pressed["action"] == "ask_one"
    assert pressed["node_id"] == "goal"
    assert pressed["alignment_score"] < pressed["alignment_exit_threshold"]
    with pytest.raises(AlignmentGraphError, match="below the exit threshold"):
        store.confirm(
            "I confirm the stated strategy and authorize autonomous research.",
            decision["alignment_digest"],
        )


def test_explicit_waive_records_and_proceeds_without_it_blocked(tmp_path: Path) -> None:
    """Issue #491: the explicit waive path — recorded, it proceeds; without it, blocked."""
    store = _store(tmp_path)
    store.merge(_ready_graph())
    store.record("goal", "unchanged", "fp-axis", new_axes=["What about the deployment environment?"])
    assert store.plan()["action"] == "ask_one"
    with pytest.raises(AlignmentGraphError, match="below the exit threshold"):
        store.confirm(
            "I confirm the stated strategy and authorize autonomous research.",
            store.status()["graph_digest"],
        )

    with pytest.raises(AlignmentGraphError, match="generic acknowledgement"):
        store.waive("ok")

    waived = store.waive("Proceed despite the unexplored deployment-environment axis; I accept the risk.")
    assert waived["waived"] is True
    assert waived["alignment_score"] < waived["alignment_exit_threshold"]
    decision = store.plan()
    assert decision["action"] == "await_human_confirmation"
    result = store.confirm(
        "I confirm the stated strategy and authorize autonomous research.",
        decision["alignment_digest"],
    )
    assert result["status"] == "autonomous"
    assert result["phase"] == "research"


def test_waive_expires_when_the_graph_changes_after_it(tmp_path: Path) -> None:
    """A waive is bound to the graph content it named; the gate re-engages on change."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5))
    for turn in range(6):
        store.record("gap-a", "unchanged", "fp-same")
    assert store.plan()["action"] == "alignment_incomplete"

    store.waive("Proceed with the open point; I accept it.")
    assert store.plan()["action"] == "reconnaissance"

    _merge_gaps(store, ("gap-b", 4))
    decision = store.plan()
    assert decision["action"] == "alignment_incomplete"
    assert "gap-b" in [node["node_id"] for node in decision["blocked_nodes"]]


def test_user_response_after_blocked_disposition_extends_then_reblocks(tmp_path: Path) -> None:
    """Issue #491: extension by engagement is real and bounded; each block needs the user."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5))
    for turn in range(6):
        store.record("gap-a", "unchanged", f"fp-{turn}")
    assert store.plan()["action"] == "alignment_incomplete"

    store.record("gap-a", "changed", "fp-extension")
    assert store.plan()["action"] == "ask_one"

    for turn in range(4):
        store.record("gap-a", "changed", f"fp-more-{turn}")
    assert store.plan()["action"] == "alignment_incomplete"

    store.record("gap-a", "changed", "fp-rearm")
    assert store.plan()["action"] == "ask_one"


def test_cli_waive_records_the_waive(tmp_path: Path) -> None:
    """The CLI surfaces the explicit waive path."""
    from research_tree.alignment_graph import main

    base = ["--workspace", str(tmp_path), "--project-id", "waive-run"]
    assert main([*base, "init", "--run-id", "run-491-cli"]) == 0
    assert main([*base, "waive", "--run-id", "run-491-cli", "--reason", "Proceed with the open point; accepted."]) == 0


def test_waive_rejects_generic_acknowledgements(tmp_path: Path) -> None:
    """A waive is an explicit decision; generic acknowledgements are rejected (as in confirm)."""
    store = _store(tmp_path)
    with pytest.raises(AlignmentGraphError, match="generic acknowledgement"):
        store.waive("继续")
