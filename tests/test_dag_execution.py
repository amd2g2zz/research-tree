"""Issue #531 — DAG-driven execution: the compiled graph becomes the scheduler.

Scenario-named tests: node-level ``depends_on`` edges gate dispatch,
dependency conclusions propagate into the worker's execution context, and
slot-level dependencies block downstream slot roots.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest


def decision_slots() -> dict[str, dict[str, Any]]:
    return {
        "slot-architecture": {
            "status": "open",
            "priority": "P0",
            "uncertainty": "high",
            "question": "How should recursive research state be maintained?",
            "validation": {"oracle": "restart and replay preserves the active frontier"},
        }
    }


def dependent_slots() -> dict[str, dict[str, Any]]:
    return {
        "slot-upstream": {
            "status": "open",
            "priority": "P0",
            "uncertainty": "high",
            "question": "Resolve the shared platform constraint.",
            "validation": {"oracle": "The platform constraint is resolved with anchored evidence."},
        },
        "slot-downstream": {
            "status": "open",
            "priority": "P0",
            "uncertainty": "high",
            "question": "Design the downstream component on the resolved constraint.",
            "validation": {"oracle": "The downstream design cites the resolved constraint."},
            "depends_on": ["slot-upstream"],
        },
    }


def baseline_tree(
    *,
    round_id: str = "round-dag",
    slots: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from research_tree import initialize_research_state

    return initialize_research_state(
        round_id=round_id,
        tree_id=f"tree-{round_id}",
        decision_slots=slots or decision_slots(),
    )


def grafted_node(
    base: dict[str, Any],
    *,
    node_id: str,
    question: str,
    depends_on: list[str] | None = None,
    parent_id: str | None = "root:slot-architecture",
) -> dict[str, Any]:
    node = copy.deepcopy(base)
    node["id"] = node_id
    node["question"] = question
    node["parent_id"] = parent_id
    node["identity_namespace"] = "question"
    node["trigger_ref"] = "issue-531:test-graft"
    node["status"] = "frontier"
    node["terminal_reason"] = None
    node["mandatory"] = False
    node["depends_on"] = list(depends_on or ())
    node["selection_value"] = 0.0
    return node


def graft(state: dict[str, Any], *nodes: dict[str, Any], order: list[str]) -> None:
    for node in nodes:
        state["nodes"][node["id"]] = node
    state["frontier_node_ids"] = [
        node_id for node_id in order if state["nodes"][node_id]["status"] == "frontier"
    ]


def selected_ids(state: dict[str, Any], *, max_parallelism: int) -> list[str]:
    from research_tree import select_research_actions

    return [str(action["id"]) for action in select_research_actions(state, max_parallelism=max_parallelism)]


def close(state: dict[str, Any], node_id: str) -> None:
    node = state["nodes"][node_id]
    node["status"] = "completed"
    node["terminal_reason"] = "Finding Pack ingested"
    state["frontier_node_ids"] = [
        candidate for candidate in state["frontier_node_ids"] if state["nodes"][candidate]["status"] == "frontier"
    ]


def test_open_dependency_blocks_high_value_node_from_dispatch() -> None:
    state = baseline_tree()
    root = state["nodes"]["root:slot-architecture"]
    dependency = grafted_node(root, node_id="node:dep-1", question="Resolve the platform constraint first.")
    dependent = grafted_node(
        root,
        node_id="node:dependent",
        question="Design on top of the resolved constraint.",
        depends_on=["node:dep-1"],
    )
    dependent["selection_value"] = 9.0
    dependency["selection_value"] = 1.0
    root["selection_value"] = 0.5
    graft(state, dependency, dependent, order=["node:dependent", "node:dep-1", "root:slot-architecture"])

    # The pinned inversion of the greedy cut: the highest-value node is
    # unready, so the two ready nodes dispatch instead — even with room to
    # spare under max_parallelism.
    assert selected_ids(state, max_parallelism=2) == ["node:dep-1", "root:slot-architecture"]


def test_closing_last_dependency_makes_dependent_dispatchable_in_same_pass() -> None:
    state = baseline_tree()
    root = state["nodes"]["root:slot-architecture"]
    dependency = grafted_node(root, node_id="node:dep-1", question="Resolve the platform constraint first.")
    dependent = grafted_node(
        root,
        node_id="node:dependent",
        question="Design on top of the resolved constraint.",
        depends_on=["node:dep-1"],
    )
    dependent["selection_value"] = 9.0
    dependency["selection_value"] = 1.0
    root["selection_value"] = 0.5
    graft(state, dependency, dependent, order=["node:dependent", "node:dep-1", "root:slot-architecture"])
    assert "node:dependent" not in selected_ids(state, max_parallelism=3)

    close(state, "node:dep-1")

    assert selected_ids(state, max_parallelism=3)[0] == "node:dependent"


def test_dispatched_node_carries_dependency_conclusion_digests_in_context() -> None:
    from research_tree import select_research_actions

    state = baseline_tree()
    root = state["nodes"]["root:slot-architecture"]
    dependency = grafted_node(root, node_id="node:dep-1", question="Resolve the platform constraint first.")
    dependent = grafted_node(
        root,
        node_id="node:dependent",
        question="Design on top of the resolved constraint.",
        depends_on=["node:dep-1"],
    )
    dependency["selection_value"] = 1.0
    dependent["selection_value"] = 9.0
    root["selection_value"] = 0.5
    graft(state, dependency, dependent, order=["node:dependent", "node:dep-1", "root:slot-architecture"])
    close(state, "node:dep-1")

    actions = select_research_actions(state, max_parallelism=1)
    entries = actions[0]["execution_context"]["dependency_context"]
    assert [entry["node_id"] for entry in entries] == ["node:dep-1"]
    entry = entries[0]
    assert entry["question"] == "Resolve the platform constraint first."
    assert entry["status"] == "completed"
    assert len(entry["conclusion_digest"]) == 16
    assert all(character in "0123456789abcdef" for character in entry["conclusion_digest"])

    # The digest tracks the dependency's conclusion, not just its identity.
    state["nodes"]["node:dep-1"]["terminal_reason"] = "superseded by a decisive counter-finding"
    again = select_research_actions(state, max_parallelism=1)
    assert again[0]["execution_context"]["dependency_context"][0]["conclusion_digest"] != entry["conclusion_digest"]


def test_multi_dependency_node_converges_only_when_all_dependencies_close() -> None:
    state = baseline_tree()
    root = state["nodes"]["root:slot-architecture"]
    first = grafted_node(root, node_id="node:dep-1", question="Resolve the platform constraint first.")
    second = grafted_node(root, node_id="node:dep-2", question="Resolve the migration constraint second.")
    dependent = grafted_node(
        root,
        node_id="node:dependent",
        question="Design on top of both resolved constraints.",
        depends_on=["node:dep-1", "node:dep-2"],
    )
    first["selection_value"] = 2.0
    second["selection_value"] = 1.5
    dependent["selection_value"] = 9.0
    root["selection_value"] = 0.5
    graft(
        state,
        first,
        second,
        dependent,
        order=["node:dependent", "node:dep-1", "node:dep-2", "root:slot-architecture"],
    )
    close(state, "node:dep-1")

    assert "node:dependent" not in selected_ids(state, max_parallelism=4)

    close(state, "node:dep-2")
    actions = selected_ids(state, max_parallelism=4)
    assert actions[0] == "node:dependent"
    assert "node:dependent" in actions


def test_slot_dependency_blocks_downstream_slot_roots_until_upstream_closes() -> None:
    state = baseline_tree(round_id="round-slot-dag", slots=dependent_slots())
    assert "root:slot-upstream" in state["nodes"]
    assert "root:slot-downstream" in state["nodes"]
    assert state["decision_slots"]["slot-downstream"]["depends_on"] == ["slot-upstream"]

    selected = selected_ids(state, max_parallelism=8)
    assert "root:slot-upstream" in selected
    assert "root:slot-downstream" not in selected

    state["decision_slots"]["slot-upstream"]["status"] = "closed"
    assert "root:slot-downstream" in selected_ids(state, max_parallelism=8)


def test_cycle_in_depends_on_rejected_at_ingest() -> None:
    from research_tree import NodeDependencyError, apply_research_results

    state = baseline_tree()
    root = state["nodes"]["root:slot-architecture"]
    first = grafted_node(root, node_id="node:a", question="Question A.", depends_on=["node:b"])
    second = grafted_node(root, node_id="node:b", question="Question B.", depends_on=["node:a"])
    graft(state, first, second, order=["node:a", "node:b", "root:slot-architecture"])
    fresh = {
        "id": "finding-fresh",
        "decision_slot_id": "slot-architecture",
        "observations": [{"claim": "A fresh observation.", "anchor": {"kind": "source", "ref": "ref-1"}}],
        "option_effects": [],
        "remaining_uncertainties": [],
        "research_continuations": [],
    }

    with pytest.raises(NodeDependencyError) as excinfo:
        apply_research_results(state, [fresh])
    assert "cycle" in str(excinfo.value).lower()


def test_unknown_dependency_rejected_at_ingest() -> None:
    from research_tree import NodeDependencyError, apply_research_results

    state = baseline_tree()
    root = state["nodes"]["root:slot-architecture"]
    orphan = grafted_node(root, node_id="node:orphan", question="Design on a ghost.", depends_on=["node:ghost"])
    graft(state, orphan, order=["node:orphan", "root:slot-architecture"])
    fresh = {
        "id": "finding-fresh-2",
        "decision_slot_id": "slot-architecture",
        "observations": [{"claim": "Another fresh observation.", "anchor": {"kind": "source", "ref": "ref-2"}}],
        "option_effects": [],
        "remaining_uncertainties": [],
        "research_continuations": [],
    }

    with pytest.raises(NodeDependencyError) as excinfo:
        apply_research_results(state, [fresh])
    assert "node:ghost" in str(excinfo.value)


def test_legacy_nodes_without_depends_on_behave_as_today() -> None:
    from research_tree import select_research_actions

    state = baseline_tree()
    # Simulate a schema-1 persisted tree: no node carries a depends_on key.
    for node in state["nodes"].values():
        node.pop("depends_on", None)
    legacy_actions = select_research_actions(state, max_parallelism=8)

    # Dispatch order and payload shape are unchanged, and no dependency
    # context is injected for dependency-free nodes.
    assert [action["id"] for action in legacy_actions] == list(state["frontier_node_ids"])
    for action in legacy_actions:
        assert "dependency_context" not in action["execution_context"]

    # The additive depends_on key (empty) is inert for the same tree.
    annotated = copy.deepcopy(state)
    for node in annotated["nodes"].values():
        node.setdefault("depends_on", [])
    assert [action["id"] for action in select_research_actions(annotated, max_parallelism=8)] == list(
        state["frontier_node_ids"]
    )


def test_ready_set_smaller_than_parallelism_returns_fewer() -> None:
    state = baseline_tree()
    root = state["nodes"]["root:slot-architecture"]
    first = grafted_node(root, node_id="node:dependent-a", question="Design A.", depends_on=["root:slot-architecture"])
    second = grafted_node(root, node_id="node:dependent-b", question="Design B.", depends_on=["root:slot-architecture"])
    first["selection_value"] = 8.0
    second["selection_value"] = 9.0
    root["selection_value"] = 0.5
    graft(state, first, second, order=["node:dependent-b", "node:dependent-a", "root:slot-architecture"])

    # Only the root is ready; the two higher-value dependents must NOT
    # backfill the parallelism budget.
    assert selected_ids(state, max_parallelism=4) == ["root:slot-architecture"]
