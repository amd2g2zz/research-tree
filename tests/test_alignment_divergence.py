"""Divergence-aware alignment state — issue #496 scenarios.

The alignment dialogue is 发散 → 局部收敛 → 再发散, not linear convergence:
a user answer that opens a new divergence axis must keep the controller in
dialogue, and stagnation localized in one node must not terminate
exploration of another node's axis.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research_tree.alignment_graph import AlignmentGraphError, AlignmentGraphStore


def _store(tmp_path: Path) -> AlignmentGraphStore:
    store = AlignmentGraphStore(tmp_path / "alignment.db")
    store.initialize("run-496")
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


def test_record_opening_new_divergence_axis_keeps_controller_in_dialogue(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5))
    store.record("gap-a", "unchanged", "fp-same")
    store.record("gap-a", "unchanged", "fp-same")

    result = store.record(
        "gap-a",
        "unchanged",
        "fp-same",
        new_axes=["What about failure modes nobody listed?"],
    )

    assert result["next_action"] == "plan"
    assert result["dialogue_mode"] == "divergent"
    assert len(result["opened_axes"]) == 1

    divergence = store.status()["divergence"]
    axis = divergence["axes"][0]
    assert axis["axis_id"] == result["opened_axes"][0]
    assert axis["axis_id"].startswith("axis-")
    assert axis["node_id"] == "gap-a"
    assert axis["description"] == "What about failure modes nobody listed?"
    assert axis["status"] == "open"
    assert axis["opened_turn"] == result["turn"]
    assert axis["stagnant_turns"] == 0
    assert divergence["node_stagnation"]["gap-a"] == 0
    assert divergence["mode"] == "divergent"


def test_axis_state_survives_persistence_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5), ("gap-b", 4))
    store.record("gap-a", "unchanged", "fp-a")
    store.record("gap-a", "unchanged", "fp-a")
    store.record("gap-a", "unchanged", "fp-a", new_axes=["Explore the cost constraint axis"])
    store.record("gap-a", "unchanged", "fp-a")
    store.record("gap-b", "unchanged", "fp-b")

    before = store.status()["divergence"]
    assert before["axes"]
    assert before["axes"][0]["stagnant_turns"] == 1
    assert before["node_stagnation"]["gap-a"] == 1

    reopened = AlignmentGraphStore(tmp_path / "alignment.db")
    assert reopened.status()["divergence"] == before

    rebuilt = reopened.rebuild_materialized()
    assert rebuilt["divergence"] == before


def test_axis_redeclaration_dedupes_and_cross_node_id_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5), ("gap-b", 4))

    first = store.record("gap-a", "unchanged", "fp", new_axes=["Explore cost constraints"])
    second = store.record("gap-a", "unchanged", "fp", new_axes=["Explore cost constraints"])

    assert first["opened_axes"] == second["opened_axes"]
    assert len(store.status()["divergence"]["axes"]) == 1

    axis_id = first["opened_axes"][0]
    with pytest.raises(AlignmentGraphError, match="belongs to node"):
        store.record("gap-b", "unchanged", "fp", new_axes=[{"id": axis_id, "description": "hijack"}])
    with pytest.raises(AlignmentGraphError, match="unknown fields"):
        store.record("gap-a", "unchanged", "fp", new_axes=[{"description": "x", "priority": 1}])


def test_quiet_turns_stagnate_node_and_axes_while_answered_converges(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5))
    store.record("gap-a", "unchanged", "fp", new_axes=["Explore cost constraints"])
    store.record("gap-a", "unchanged", "fp")

    divergence = store.status()["divergence"]
    assert divergence["node_stagnation"]["gap-a"] == 1
    assert divergence["axes"][0]["stagnant_turns"] == 1

    store.record("gap-a", "answered", "fp-same")
    divergence = store.status()["divergence"]
    assert divergence["axes"][0]["status"] == "converged"

    store.record("gap-a", "reopened", "fp-same")
    divergence = store.status()["divergence"]
    assert divergence["axes"][0]["status"] == "open"
    assert divergence["axes"][0]["stagnant_turns"] == 0
