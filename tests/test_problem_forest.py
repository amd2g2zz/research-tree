"""Issue #314 — Problem Forest: forest/reconciliation/authority primitives.

Each test maps to one acceptance bullet from the issue spec. Kept tiny so
the suite doubles as living documentation for the forest contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


def _api():
    from research_tree import (
        AgentForest,
        AuthorityRole,
        Forest,
        ForestNode,
        ForestSpace,
        ReconciliationGraph,
        ReconciliationKind,
        ReconciliationMapping,
        RepositoryInspector,
        SharedBriefView,
    )

    return {
        "AgentForest": AgentForest,
        "AuthorityRole": AuthorityRole,
        "Forest": Forest,
        "ForestNode": ForestNode,
        "ForestSpace": ForestSpace,
        "ReconciliationGraph": ReconciliationGraph,
        "ReconciliationKind": ReconciliationKind,
        "ReconciliationMapping": ReconciliationMapping,
        "RepositoryInspector": RepositoryInspector,
        "SharedBriefView": SharedBriefView,
    }


def _node(
    *,
    api: dict[str, object],
    node_id: str,
    space: object,
    role: object,
    body: dict[str, object],
    confidence: float = 0.5,
    version: int = 1,
    source: str = "src:test",
) -> object:
    ForestNode = api["ForestNode"]  # type: ignore[index]
    return ForestNode.create(
        node_id=node_id,
        space=space,
        origin_role=role,
        source_ref=source,
        body=body,
        confidence=confidence,
        version=version,
    )


def test_requester_forest_starts_sparse_when_intent_vague(tmp_path: Path) -> None:
    """Vague intent → sparse forest; NO fabricated requirements."""

    api = _api()
    inspector = api["RepositoryInspector"]()
    baseline = inspector.inspect(tmp_path)
    forest = inspector.collect_problem_forest(baseline=baseline, intent_text="huh?")

    # At most one or two anchor nodes from baseline — never invented requirements.
    assert len(forest) < 3, f"vague intent must not fabricate; got {len(forest)} nodes"
    for node in forest.current_nodes():
        assert node.space is api["ForestSpace"].REQUESTER
        assert node.confidence < 0.5


def test_bounded_reconnaissance_triggered_by_low_confidence() -> None:
    """Confidence < 0.4 OR < 2 nodes → bounded reconnaissance flag is set."""

    api = _api()
    Forest = api["Forest"]  # type: ignore[index]
    forest = Forest()
    node = _node(
        api=api,
        node_id="r-goal-1",
        space=api["ForestSpace"].REQUESTER,
        role=api["AuthorityRole"].INTENT_OWNER,
        body={"statement": "maybe explore X"},
        confidence=0.2,
    )
    forest = forest.append(node)
    assert forest.needs_bounded_reconnaissance() is True

    # Two solid nodes → no reconnaissance.
    second = _node(
        api=api,
        node_id="r-constraint-1",
        space=api["ForestSpace"].REQUESTER,
        role=api["AuthorityRole"].DECISION_OWNER,
        body={"statement": "must run on python 3.11"},
        confidence=0.9,
    )
    forest = forest.append(second)
    assert forest.needs_bounded_reconnaissance() is False


def test_agent_forest_rejects_raw_chain_of_thought() -> None:
    """Agent forest MUST NOT carry raw private chain-of-thought.

    Structural guarantee: there is no field to hold it. Asserted by absence.
    """

    import dataclasses

    api = _api()
    ForestNode = api["ForestNode"]  # type: ignore[index]
    field_names = {field.name for field in dataclasses.fields(ForestNode)}
    forbidden = {"chain_of_thought", "raw_thinking", "private_reasoning", "scratchpad", "inner_monologue"}
    leaked = field_names & forbidden
    assert not leaked, f"Agent forest must not carry raw CoT; leaked fields: {sorted(leaked)}"


def test_node_carries_all_required_metadata_fields() -> None:
    """Every node carries space, stable identity, origin role, source, timestamp, version."""

    api = _api()
    node = _node(
        api=api,
        node_id="r-problem-1",
        space=api["ForestSpace"].REQUESTER,
        role=api["AuthorityRole"].INTENT_OWNER,
        body={"statement": "users complain about latency"},
        confidence=0.7,
    )
    required = {"id", "space", "origin_role", "source_ref", "timestamp", "version"}
    missing = required - set(node.__dataclass_fields__.keys())  # type: ignore[attr-defined]
    assert not missing, f"missing required fields: {sorted(missing)}"
    assert isinstance(node.id, str) and node.id
    assert isinstance(node.timestamp, str) and "T" in node.timestamp
    assert node.version >= 1
    assert node.space is api["ForestSpace"].REQUESTER
    assert isinstance(node.body, Mapping)


def test_reconciliation_supports_all_eight_kinds() -> None:
    """All 8 reconciliation kinds are representable and accepted."""

    api = _api()
    ReconciliationKind = api["ReconciliationKind"]  # type: ignore[index]
    expected = {
        "same_problem",
        "partial_match",
        "missing_in_agent",
        "agent_expansion_unconfirmed",
        "topology_mismatch",
        "oracle_mismatch",
        "contradiction",
        "superseded",
    }
    actual = {kind.value for kind in ReconciliationKind}
    assert actual == expected, f"expected {expected}, got {actual}"

    graph = api["ReconciliationGraph"]()  # type: ignore[index]
    for kind in ReconciliationKind:
        graph.add(
            api["ReconciliationMapping"](  # type: ignore[index]
                kind=kind,
                requester_ref="r-problem-1",
                agent_ref="a-hypothesis-1",
                note=f"sample {kind.value}",
            )
        )
    listed = {(edge.kind, edge.requester_ref, edge.agent_ref) for edge in graph.list_edges()}
    assert len(listed) == 8


def test_supersede_split_merge_regress_confidence_round_trip() -> None:
    """Lifecycle: append → supersede → split → merge → regress_confidence round-trips."""

    api = _api()
    Forest = api["Forest"]  # type: ignore[index]
    Space = api["ForestSpace"]  # type: ignore[index]
    Role = api["AuthorityRole"]  # type: ignore[index]

    forest = Forest()
    initial = _node(
        api=api,
        node_id="r-problem-1",
        space=Space.REQUESTER,
        role=Role.INTENT_OWNER,
        body={"statement": "vague"},
        confidence=0.4,
    )
    forest = forest.append(initial)

    # supersede → same id, version bumps
    superseded_ref = forest.supersede(node_id="r-problem-1", body={"statement": "refined"}, confidence=0.7)
    assert superseded_ref.version == 2
    assert forest.current("r-problem-1").version == 2

    # split → children with stable ids
    children = forest.split(
        parent_id="r-problem-1",
        children=(
            ("r-problem-1a", {"statement": "child a"}, 0.6),
            ("r-problem-1b", {"statement": "child b"}, 0.5),
        ),
        origin_role=Role.INTENT_OWNER,
        source_ref="src:split",
    )
    assert [child.id for child in children] == ["r-problem-1a", "r-problem-1b"]
    assert forest.current("r-problem-1a").parent_of == "r-problem-1"
    assert forest.current("r-problem-1b").parent_of == "r-problem-1"

    # merge → new id, originals superseded
    merged = forest.merge(
        source_ids=["r-problem-1a", "r-problem-1b"],
        merged_id="r-problem-merged",
        body={"statement": "merged view"},
        confidence=0.8,
        origin_role=Role.INTENT_OWNER,
        source_ref="src:merge",
    )
    assert merged.id == "r-problem-merged"
    assert forest.is_superseded("r-problem-1a") is True

    # regress_confidence → new version with lower confidence
    regressed = forest.regress_confidence(
        node_id="r-problem-merged",
        new_confidence=0.3,
        reason="evidence weakened",
    )
    assert regressed.confidence == 0.3
    assert regressed.version > merged.version


def test_shared_brief_view_hides_unresolved_deltas() -> None:
    """Shared view shows aligned nodes; unresolved deltas live outside it but are visible."""

    api = _api()
    Forest = api["Forest"]  # type: ignore[index]
    Space = api["ForestSpace"]  # type: ignore[index]
    Role = api["AuthorityRole"]  # type: ignore[index]

    requester = Forest()
    agent = Forest()
    aligned_id = "r-problem-1"
    unaligned_requester = "r-problem-2"

    # Aligned pair: same_problem mapping exists.
    requester = requester.append(
        _node(
            api=api,
            node_id=aligned_id,
            space=Space.REQUESTER,
            role=Role.INTENT_OWNER,
            body={"statement": "users want lower latency"},
            confidence=0.8,
        )
    )
    agent = agent.append(
        _node(
            api=api,
            node_id="a-hypothesis-1",
            space=Space.AGENT,
            role=Role.RESEARCH_OWNER,
            body={"statement": "latency hypothesis"},
            confidence=0.7,
        )
    )
    # Unaligned requester node: agent has no corresponding hypothesis.
    requester = requester.append(
        _node(
            api=api,
            node_id=unaligned_requester,
            space=Space.REQUESTER,
            role=Role.INTENT_OWNER,
            body={"statement": "users want offline mode"},
            confidence=0.6,
        )
    )

    graph = api["ReconciliationGraph"]()  # type: ignore[index]
    graph.add(
        api["ReconciliationMapping"](  # type: ignore[index]
            kind=api["ReconciliationKind"].SAME_PROBLEM,  # type: ignore[index]
            requester_ref=aligned_id,
            agent_ref="a-hypothesis-1",
            note="aligned",
        )
    )

    view = api["SharedBriefView"](  # type: ignore[index]
        requester_forest=requester,
        agent_forest=agent,
        reconciliation=graph,
    )

    shared_nodes = list(view.iter_shared())
    shared_ids = {node.id for node in shared_nodes}
    assert aligned_id in shared_ids
    assert unaligned_requester not in shared_ids

    # Unresolved deltas visible separately (but not part of the shared view).
    deltas = list(view.iter_unresolved_deltas())
    assert any(delta.requester_ref == unaligned_requester for delta in deltas)


def test_authority_explicit_per_node() -> None:
    """Authority is explicit per node; every node carries exactly one of 5 roles."""

    api = _api()
    AuthorityRole = api["AuthorityRole"]  # type: ignore[index]
    expected_roles = {
        "intent_owner",
        "research_owner",
        "decision_owner",
        "approval_required",
        "authority_scope",
    }
    actual_roles = {role.value for role in AuthorityRole}
    assert actual_roles == expected_roles

    Space = api["ForestSpace"]  # type: ignore[index]
    from research_tree.authority import authority_scope as _scope_fn
    from research_tree.authority import role_of as _role_of

    node = _node(
        api=api,
        node_id="a-finding-1",
        space=Space.AGENT,
        role=AuthorityRole.RESEARCH_OWNER,
        body={"statement": "found X"},
        confidence=0.9,
    )
    assert _role_of(node) is AuthorityRole.RESEARCH_OWNER
    assert _scope_fn(node) == {"research_owner"}

    # Decision-owner node returns the decision_owner scope.
    decision_node = _node(
        api=api,
        node_id="r-decision-1",
        space=Space.REQUESTER,
        role=AuthorityRole.DECISION_OWNER,
        body={"statement": "approved Y"},
        confidence=0.95,
    )
    assert _role_of(decision_node) is AuthorityRole.DECISION_OWNER
    assert _scope_fn(decision_node) == {"decision_owner"}
