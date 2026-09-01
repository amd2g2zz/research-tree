"""Cognitive-surface coverage for surviving ``problem_forest`` symbols.

Ported from ``origin/dev:tests/test_cognitive_model.py`` after batch-1
retired ``cognition.py`` (CognitionState) along with that test file. The
deleted file carried assertions about surviving ``problem_forest`` behaviour;
this module restores them without reviving the deleted type.

The retired ``CognitionState`` is replaced by :class:`_CognitionSurface`, a
duck-typed fixture exposing exactly the attribute surface the surviving
functions read: ``.evidence`` / ``.reconciliation`` / ``.requester_forest`` /
``.agent_forest``. Where ``problem_forest`` isinstance-checks its inputs
(``Forest`` / ``ReconciliationGraph``) the real types are used — a duck-typed
stand-in there would only weaken the contract under test.
"""

from __future__ import annotations

from dataclasses import dataclass

from research_tree import (
    AuthorityRole,
    BoundedReconstitutionTrigger,
    DisclosureTrigger,
    EvidenceArtifact,
    Forest,
    ForestSpace,
    ReconciliationGraph,
    ReconciliationKind,
    ReconciliationMapping,
    SharedForestFilter,
    UnderstandingDebt,
    catch_up_triggers,
    compute_understanding_debt,
    disclosure_triggers,
)
from research_tree.authority import authority_scope, role_of


@dataclass(frozen=True, slots=True)
class _CognitionSurface:
    """Duck-typed stand-in for the retired ``CognitionState``.

    Minimal attribute surface consumed by ``disclosure_triggers`` and
    ``BoundedReconstitutionTrigger.evaluate``.
    """

    requester_forest: Forest
    agent_forest: Forest
    reconciliation: ReconciliationGraph
    evidence: tuple[EvidenceArtifact, ...] = ()


def _node(
    *,
    node_id: str,
    space: ForestSpace,
    role: AuthorityRole,
    body: dict[str, object],
    confidence: float = 0.5,
    version: int = 1,
) -> object:
    from research_tree import ForestNode

    return ForestNode.create(
        node_id=node_id,
        space=space,
        origin_role=role,
        source_ref="src:test",
        body=body,
        confidence=confidence,
        version=version,
    )


def _aligned_pair(
    *,
    requester_id: str,
    agent_id: str,
    branch_id: str,
    requester_body: dict[str, object] | None = None,
    agent_body: dict[str, object] | None = None,
    requester_confidence: float = 0.9,
    agent_confidence: float = 0.8,
) -> tuple[object, object]:
    """Append one aligned requester/agent node pair for a branch."""

    requester = _node(
        node_id=requester_id,
        space=ForestSpace.REQUESTER,
        role=AuthorityRole.DECISION_OWNER,
        body={"statement": "users want lower latency", "branch_id": branch_id, **(requester_body or {})},
        confidence=requester_confidence,
    )
    agent = _node(
        node_id=agent_id,
        space=ForestSpace.AGENT,
        role=AuthorityRole.RESEARCH_OWNER,
        body={"statement": "latency hypothesis", "branch_id": branch_id, **(agent_body or {})},
        confidence=agent_confidence,
    )
    return requester, agent


def _mapping(
    kind: ReconciliationKind,
    requester_ref: str,
    agent_ref: str,
    note: str,
) -> ReconciliationMapping:
    return ReconciliationMapping(kind=kind, requester_ref=requester_ref, agent_ref=agent_ref, note=note)


def test_shared_forest_excludes_unresolved_mappings() -> None:
    """Only same_problem / partial_match edges without delta flags reach SharedForestFilter output."""

    requester = Forest()
    agent = Forest()
    graph = ReconciliationGraph()

    aligned_req, aligned_agt = _aligned_pair(requester_id="r-aligned", agent_id="a-aligned", branch_id="branch-a")
    partial_req, partial_agt = _aligned_pair(
        requester_id="r-partial",
        agent_id="a-partial",
        branch_id="branch-a",
        agent_body={"partial": True},
    )
    contradiction_req, contradiction_agt = _aligned_pair(
        requester_id="r-contradiction",
        agent_id="a-contradiction",
        branch_id="branch-a",
    )

    requester.append(aligned_req).append(partial_req).append(contradiction_req)
    agent.append(aligned_agt).append(partial_agt).append(contradiction_agt)

    graph.add(_mapping(ReconciliationKind.SAME_PROBLEM, "r-aligned", "a-aligned", "aligned"))
    graph.add(_mapping(ReconciliationKind.PARTIAL_MATCH, "r-partial", "a-partial", "partial"))
    graph.add(_mapping(ReconciliationKind.CONTRADICTION, "r-contradiction", "a-contradiction", "disputed"))

    shared = SharedForestFilter().filter(requester_forest=requester, agent_forest=agent, reconciliation=graph)
    shared_ids = {node.id for node in shared}
    assert "r-aligned" in shared_ids
    assert "r-partial" in shared_ids
    assert "r-contradiction" not in shared_ids, "unresolved mapping leaked into Shared Forest"


def test_understanding_debt_lists_missing_expansion_disagreement_obligations() -> None:
    """compute_understanding_debt surfaces the canonical debt categories."""

    requester = Forest()
    agent = Forest()
    graph = ReconciliationGraph()

    missing_req = _node(
        node_id="r-missing",
        space=ForestSpace.REQUESTER,
        role=AuthorityRole.INTENT_OWNER,
        body={"statement": "agent has no counterpart"},
        confidence=0.6,
    )
    requester.append(missing_req)
    # No edge for r-missing → synthesized missing_in_agent delta.

    expansion_req, expansion_agt = _aligned_pair(
        requester_id="r-expansion",
        agent_id="a-expansion",
        branch_id="branch-a",
        agent_body={"unconfirmed": True},
    )
    requester.append(expansion_req)
    agent.append(expansion_agt)
    graph.add(
        _mapping(
            ReconciliationKind.AGENT_EXPANSION_UNCONFIRMED,
            "r-expansion",
            "a-expansion",
            "agent expansion awaiting confirmation",
        )
    )

    disagreement_req, disagreement_agt = _aligned_pair(
        requester_id="r-disagree",
        agent_id="a-disagree",
        branch_id="branch-a",
    )
    requester.append(disagreement_req)
    agent.append(disagreement_agt)
    graph.add(_mapping(ReconciliationKind.CONTRADICTION, "r-disagree", "a-disagree", "disputed"))

    debt = compute_understanding_debt(requester_forest=requester, agent_forest=agent, reconciliation=graph)

    assert isinstance(debt, UnderstandingDebt)
    assert "r-missing" in debt.missing_in_agent
    assert "r-expansion" in debt.agent_expansion_unconfirmed
    assert "r-disagree" in debt.active_disagreements
    # Neither expansion nor disagreement edges count as alignment, so the
    # branch's requester-owned scope stays an open research obligation.
    assert "branch-a" in debt.research_obligations


def test_catch_up_triggered_for_missing_in_agent() -> None:
    """Missing requester nodes produce catch_up event ids, not silent acceptance."""

    requester = Forest()
    agent = Forest()
    graph = ReconciliationGraph()

    # Two requester nodes; neither mapped → both missing.
    requester.append(
        _node(
            node_id="r-problem-x",
            space=ForestSpace.REQUESTER,
            role=AuthorityRole.INTENT_OWNER,
            body={"statement": "x"},
            confidence=0.7,
        )
    ).append(
        _node(
            node_id="r-problem-y",
            space=ForestSpace.REQUESTER,
            role=AuthorityRole.DECISION_OWNER,
            body={"statement": "y"},
            confidence=0.6,
        )
    )

    debt = compute_understanding_debt(requester_forest=requester, agent_forest=agent, reconciliation=graph)
    triggers = catch_up_triggers(debt)

    assert "r-problem-x" in triggers
    assert "r-problem-y" in triggers


def test_disclosure_triggered_for_evidence_backed_expansion_on_requester_node() -> None:
    """An agent expansion with new evidence on a requester-owned decision fires disclosure."""

    requester = Forest()
    agent = Forest()
    graph = ReconciliationGraph()

    decision_req, expansion_agt = _aligned_pair(
        requester_id="r-decision-1",
        agent_id="a-expansion-1",
        branch_id="branch-a",
        agent_body={"evidence_backed": True, "evidence_id": "ev-1"},
    )
    requester.append(decision_req)
    agent.append(expansion_agt)
    graph.add(
        _mapping(
            ReconciliationKind.AGENT_EXPANSION_UNCONFIRMED,
            "r-decision-1",
            "a-expansion-1",
            "evidence-backed expansion",
        )
    )

    # Synthetic evidence anchor backed by a real EvidenceArtifact record.
    artifact = EvidenceArtifact(
        evidence_id="ev-1",
        run_id="run-1",
        revision=1,
        media_type="text/plain",
        locator={"path": "notes/x.md"},
        content_digest="0" * 64,
        size_bytes=12,
        acquired_at="2026-01-01T00:00:00+00:00",
        acquisition_method="manual",
        provenance_group="p",
        applicability="supports expansion",
        confidence="high",
        limitations=(),
        status="active",
        extractor_version="v1",
        evidence_class="primary",
    )
    state = _CognitionSurface(
        requester_forest=requester,
        agent_forest=agent,
        reconciliation=graph,
        evidence=(artifact,),
    )

    triggers = disclosure_triggers(state)
    assert any(t.node_id == "r-decision-1" for t in triggers), (
        "evidence-backed agent expansion on a requester-owned decision must trigger disclosure"
    )
    trigger = next(t for t in triggers if t.node_id == "r-decision-1")
    assert isinstance(trigger, DisclosureTrigger)
    assert trigger.agent_ref == "a-expansion-1"
    assert trigger.evidence_id == "ev-1"


def test_bounded_reconstitution_for_sparse_forest_not_requirement_invention() -> None:
    """A vague/sparse requester forest must NOT fabricate nodes; it must trigger bounded reconstitution."""

    requester = Forest()
    agent = Forest()
    graph = ReconciliationGraph()

    # Single vague node (<2 nodes AND confidence < 0.4) → sparse.
    requester.append(
        _node(
            node_id="r-vague",
            space=ForestSpace.REQUESTER,
            role=AuthorityRole.INTENT_OWNER,
            body={"statement": "?"},
            confidence=0.2,
        )
    )

    state = _CognitionSurface(
        requester_forest=requester,
        agent_forest=agent,
        reconciliation=graph,
        evidence=(),
    )

    trigger = BoundedReconstitutionTrigger.evaluate(state)
    assert isinstance(trigger, BoundedReconstitutionTrigger)
    assert trigger.fired is True
    assert trigger.mode == "bounded_reconnaissance"
    # No fabricated nodes: forest size unchanged after evaluation.
    assert len(requester) == 1, f"sparse evaluation must not fabricate nodes; got {len(requester)} nodes"


def test_authority_explicit_per_node() -> None:
    """All 5 AuthorityRoles remain explicit per node in the cognition surface."""

    expected = {
        "intent_owner",
        "research_owner",
        "decision_owner",
        "approval_required",
        "authority_scope",
    }
    assert {role.value for role in AuthorityRole} == expected

    samples = [
        ("r-intent", ForestSpace.REQUESTER, AuthorityRole.INTENT_OWNER, "intent"),
        ("a-research", ForestSpace.AGENT, AuthorityRole.RESEARCH_OWNER, "research"),
        ("r-decision", ForestSpace.REQUESTER, AuthorityRole.DECISION_OWNER, "decision"),
        ("r-approval", ForestSpace.REQUESTER, AuthorityRole.APPROVAL_REQUIRED, "approval"),
        ("a-scope", ForestSpace.AGENT, AuthorityRole.AUTHORITY_SCOPE, "scope"),
    ]
    for node_id, space, role, statement in samples:
        node = _node(node_id=node_id, space=space, role=role, body={"statement": statement}, confidence=0.8)
        assert role_of(node) is role
        assert authority_scope(node) == frozenset({role.value})
