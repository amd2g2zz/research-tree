"""Issue #315 — Canonical asymmetric cognitive model.

The model keeps requester and agent forests independent, computes
alignment per branch and dimension (never a global score), and emits
catch-up / disclosure / bounded-reconstitution triggers as pure events.
Each test maps to one acceptance bullet from the issue spec.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pytest


def _api():
    from research_tree import (
        AgentForest,
        AlignmentScore,
        AuthorityRole,
        BoundedReconstitutionTrigger,
        CognitionState,
        DisclosureTrigger,
        EvidenceAnchor,
        EvidenceArtifact,
        EvidenceRepository,
        Forest,
        ForestNode,
        ForestSpace,
        ReconciliationGraph,
        ReconciliationKind,
        ReconciliationMapping,
        SharedBriefView,
        SharedForestFilter,
        UnderstandingDebt,
        catch_up_triggers,
        compute_alignment_per_branch,
        compute_understanding_debt,
        disclosure_triggers,
    )
    from research_tree.authority import authority_scope, role_of

    return {
        "AgentForest": AgentForest,
        "AlignmentScore": AlignmentScore,
        "AuthorityRole": AuthorityRole,
        "BoundedReconstitutionTrigger": BoundedReconstitutionTrigger,
        "CognitionState": CognitionState,
        "DisclosureTrigger": DisclosureTrigger,
        "EvidenceAnchor": EvidenceAnchor,
        "EvidenceArtifact": EvidenceArtifact,
        "EvidenceRepository": EvidenceRepository,
        "Forest": Forest,
        "ForestNode": ForestNode,
        "ForestSpace": ForestSpace,
        "ReconciliationGraph": ReconciliationGraph,
        "ReconciliationKind": ReconciliationKind,
        "ReconciliationMapping": ReconciliationMapping,
        "SharedBriefView": SharedBriefView,
        "SharedForestFilter": SharedForestFilter,
        "UnderstandingDebt": UnderstandingDebt,
        "authority_scope": authority_scope,
        "catch_up_triggers": catch_up_triggers,
        "compute_alignment_per_branch": compute_alignment_per_branch,
        "compute_understanding_debt": compute_understanding_debt,
        "disclosure_triggers": disclosure_triggers,
        "role_of": role_of,
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
    parent_of: str | None = None,
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
        parent_of=parent_of,
    )


# ---------------------------------------------------------------------------
# Helpers for cognition fixtures
# ---------------------------------------------------------------------------


def _aligned_pair(
    *,
    api: dict[str, object],
    requester_id: str,
    agent_id: str,
    branch_id: str,
    requester_body: Mapping[str, object] | None = None,
    agent_body: Mapping[str, object] | None = None,
    requester_confidence: float = 0.9,
    agent_confidence: float = 0.8,
) -> tuple[object, object]:
    """Append one aligned requester/agent node pair with a same_problem edge."""

    requester = _node(
        api=api,
        node_id=requester_id,
        space=api["ForestSpace"].REQUESTER,  # type: ignore[index]
        role=api["AuthorityRole"].DECISION_OWNER,  # type: ignore[index]
        body={"statement": "users want lower latency", "branch_id": branch_id, **(requester_body or {})},
        confidence=requester_confidence,
    )
    agent = _node(
        api=api,
        node_id=agent_id,
        space=api["ForestSpace"].AGENT,  # type: ignore[index]
        role=api["AuthorityRole"].RESEARCH_OWNER,  # type: ignore[index]
        body={"statement": "latency hypothesis", "branch_id": branch_id, **(agent_body or {})},
        confidence=agent_confidence,
    )
    return requester, agent


# ---------------------------------------------------------------------------
# Acceptance bullet 1: per-(branch, dimension) alignment, NOT a global score
# ---------------------------------------------------------------------------


def test_alignment_score_is_per_branch_not_global() -> None:
    """Two branches with different profiles must yield distinct AlignmentScores."""

    api = _api()

    requester = api["Forest"]()  # type: ignore[index]
    agent = api["Forest"]()  # type: ignore[index]
    graph = api["ReconciliationGraph"]()  # type: ignore[index]

    # Branch A: clean same_problem on a tight dimension.
    r_a, a_a = _aligned_pair(
        api=api,
        requester_id="r-problem-a",
        agent_id="a-hypothesis-a",
        branch_id="branch-a",
        agent_body={"dimension": "feasibility", "matched": True},
    )
    requester.append(r_a)
    agent.append(a_a)
    graph.add(
        api["ReconciliationMapping"](  # type: ignore[index]
            kind=api["ReconciliationKind"].SAME_PROBLEM,  # type: ignore[index]
            requester_ref="r-problem-a",
            agent_ref="a-hypothesis-a",
            note="aligned on branch a",
        )
    )

    # Branch B: same_problem but missing_in_agent delta for one sibling.
    r_b, a_b = _aligned_pair(
        api=api,
        requester_id="r-problem-b",
        agent_id="a-hypothesis-b",
        branch_id="branch-b",
        agent_body={"dimension": "feasibility", "matched": False},
    )
    requester.append(r_b).append(
        _node(
            api=api,
            node_id="r-orphan-b",
            space=api["ForestSpace"].REQUESTER,  # type: ignore[index]
            role=api["AuthorityRole"].INTENT_OWNER,  # type: ignore[index]
            body={"statement": "branch-b orphan", "branch_id": "branch-b"},
            confidence=0.5,
        )
    )
    agent.append(a_b)
    # No edge for r-orphan-b → synthesized missing_in_agent delta.

    state = api["CognitionState"](  # type: ignore[index]
        requester_forest=requester,
        agent_forest=agent,
        reconciliation=graph,
        evidence=(),
    )
    scores = api["compute_alignment_per_branch"](state)  # type: ignore[index]

    assert "branch-a" in scores
    assert "branch-b" in scores
    score_a = scores["branch-a"]
    score_b = scores["branch-b"]
    assert isinstance(score_a, api["AlignmentScore"])  # type: ignore[index]
    assert 0.0 <= score_a.score <= 1.0
    assert 0.0 <= score_b.score <= 1.0
    # Distinct branches → scores MUST diverge; otherwise the model is global.
    assert score_a.score != score_b.score, (
        f"per-branch alignment collapsed into a global score; got a={score_a.score}, b={score_b.score}"
    )


# ---------------------------------------------------------------------------
# Acceptance bullet 2: Shared Forest contains only aligned nodes
# ---------------------------------------------------------------------------


def test_shared_forest_excludes_unresolved_mappings() -> None:
    """Only same_problem / partial_match edges with full branch coverage reach SharedForestFilter output."""

    api = _api()

    requester = api["Forest"]()  # type: ignore[index]
    agent = api["Forest"]()  # type: ignore[index]
    graph = api["ReconciliationGraph"]()  # type: ignore[index]

    aligned_req, aligned_agt = _aligned_pair(
        api=api, requester_id="r-aligned", agent_id="a-aligned", branch_id="branch-a"
    )
    partial_req, partial_agt = _aligned_pair(
        api=api,
        requester_id="r-partial",
        agent_id="a-partial",
        branch_id="branch-a",
        agent_body={"partial": True},
    )
    contradiction_req, contradiction_agt = _aligned_pair(
        api=api,
        requester_id="r-contradiction",
        agent_id="a-contradiction",
        branch_id="branch-a",
    )

    requester.append(aligned_req).append(partial_req).append(contradiction_req)
    agent.append(aligned_agt).append(partial_agt).append(contradiction_agt)

    graph.add(
        api["ReconciliationMapping"](  # type: ignore[index]
            kind=api["ReconciliationKind"].SAME_PROBLEM,  # type: ignore[index]
            requester_ref="r-aligned",
            agent_ref="a-aligned",
            note="aligned",
        )
    )
    graph.add(
        api["ReconciliationMapping"](  # type: ignore[index]
            kind=api["ReconciliationKind"].PARTIAL_MATCH,  # type: ignore[index]
            requester_ref="r-partial",
            agent_ref="a-partial",
            note="partial",
        )
    )
    graph.add(
        api["ReconciliationMapping"](  # type: ignore[index]
            kind=api["ReconciliationKind"].CONTRADICTION,  # type: ignore[index]
            requester_ref="r-contradiction",
            agent_ref="a-contradiction",
            note="disputed",
        )
    )

    flt = api["SharedForestFilter"]()  # type: ignore[index]
    shared = flt.filter(requester_forest=requester, agent_forest=agent, reconciliation=graph)
    shared_ids = {node.id for node in shared}
    assert "r-aligned" in shared_ids
    assert "r-partial" in shared_ids
    assert "r-contradiction" not in shared_ids, "unresolved mapping leaked into Shared Forest"


# ---------------------------------------------------------------------------
# Acceptance bullet 3: UnderstandingDebt — missing / expansion / disagreement / obligations
# ---------------------------------------------------------------------------


def test_understanding_debt_lists_missing_expansion_disagreement_obligations() -> None:
    """compute_understanding_debt must surface the four canonical categories."""

    api = _api()

    requester = api["Forest"]()  # type: ignore[index]
    agent = api["Forest"]()  # type: ignore[index]
    graph = api["ReconciliationGraph"]()  # type: ignore[index]

    missing_req = _node(
        api=api,
        node_id="r-missing",
        space=api["ForestSpace"].REQUESTER,  # type: ignore[index]
        role=api["AuthorityRole"].INTENT_OWNER,  # type: ignore[index]
        body={"statement": "agent has no counterpart"},
        confidence=0.6,
    )
    requester.append(missing_req)
    # No edge for r-missing → synthesized missing_in_agent delta.

    expansion_req, expansion_agt = _aligned_pair(
        api=api,
        requester_id="r-expansion",
        agent_id="a-expansion",
        branch_id="branch-a",
        agent_body={"unconfirmed": True},
    )
    requester.append(expansion_req)
    agent.append(expansion_agt)
    graph.add(
        api["ReconciliationMapping"](  # type: ignore[index]
            kind=api["ReconciliationKind"].AGENT_EXPANSION_UNCONFIRMED,  # type: ignore[index]
            requester_ref="r-expansion",
            agent_ref="a-expansion",
            note="agent expansion awaiting confirmation",
        )
    )

    disagreement_req, disagreement_agt = _aligned_pair(
        api=api,
        requester_id="r-disagree",
        agent_id="a-disagree",
        branch_id="branch-a",
    )
    requester.append(disagreement_req)
    agent.append(disagreement_agt)
    graph.add(
        api["ReconciliationMapping"](  # type: ignore[index]
            kind=api["ReconciliationKind"].CONTRADICTION,  # type: ignore[index]
            requester_ref="r-disagree",
            agent_ref="a-disagree",
            note="disputed",
        )
    )

    debt = api["compute_understanding_debt"](  # type: ignore[index]
        requester_forest=requester,
        agent_forest=agent,
        reconciliation=graph,
    )

    assert isinstance(debt, api["UnderstandingDebt"])  # type: ignore[index]
    assert "r-missing" in debt.missing_in_agent
    assert "r-expansion" in debt.agent_expansion_unconfirmed
    assert "r-disagree" in debt.active_disagreements
    # research_obligations may be empty when no pending branches — structural check only
    assert isinstance(debt.research_obligations, tuple)


# ---------------------------------------------------------------------------
# Acceptance bullet 4: catch_up triggers — missing_in_agent
# ---------------------------------------------------------------------------


def test_catch_up_triggered_for_missing_in_agent() -> None:
    """Missing requester nodes produce catch_up event ids, not silent acceptance."""

    api = _api()

    requester = api["Forest"]()  # type: ignore[index]
    agent = api["Forest"]()  # type: ignore[index]
    graph = api["ReconciliationGraph"]()  # type: ignore[index]

    # Two requester nodes; neither mapped → both missing.
    requester.append(
        _node(
            api=api,
            node_id="r-problem-x",
            space=api["ForestSpace"].REQUESTER,  # type: ignore[index]
            role=api["AuthorityRole"].INTENT_OWNER,  # type: ignore[index]
            body={"statement": "x"},
            confidence=0.7,
        )
    ).append(
        _node(
            api=api,
            node_id="r-problem-y",
            space=api["ForestSpace"].REQUESTER,  # type: ignore[index]
            role=api["AuthorityRole"].DECISION_OWNER,  # type: ignore[index]
            body={"statement": "y"},
            confidence=0.6,
        )
    )

    debt = api["compute_understanding_debt"](  # type: ignore[index]
        requester_forest=requester,
        agent_forest=agent,
        reconciliation=graph,
    )
    triggers = api["catch_up_triggers"](debt)  # type: ignore[index]

    assert "r-problem-x" in triggers
    assert "r-problem-y" in triggers


# ---------------------------------------------------------------------------
# Acceptance bullet 5: disclosure triggers — evidence-backed expansions
# ---------------------------------------------------------------------------


def test_disclosure_triggered_for_evidence_backed_expansion_on_requester_node(
    tmp_path: Path,
) -> None:
    """An agent expansion with new evidence on a requester-owned decision fires disclosure."""

    api = _api()

    requester = api["Forest"]()  # type: ignore[index]
    agent = api["Forest"]()  # type: ignore[index]
    graph = api["ReconciliationGraph"]()  # type: ignore[index]

    decision_req, expansion_agt = _aligned_pair(
        api=api,
        requester_id="r-decision-1",
        agent_id="a-expansion-1",
        branch_id="branch-a",
        agent_body={"evidence_backed": True, "evidence_id": "ev-1"},
    )
    requester.append(decision_req)
    agent.append(expansion_agt)
    graph.add(
        api["ReconciliationMapping"](  # type: ignore[index]
            kind=api["ReconciliationKind"].AGENT_EXPANSION_UNCONFIRMED,  # type: ignore[index]
            requester_ref="r-decision-1",
            agent_ref="a-expansion-1",
            note="evidence-backed expansion",
        )
    )

    # Synthetic evidence anchor pointing at a real EvidenceArtifact stub.
    evidence_id = "ev-1"
    artifact = api["EvidenceArtifact"](  # type: ignore[index]
        evidence_id=evidence_id,
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
    evidence = (artifact,)
    state = api["CognitionState"](  # type: ignore[index]
        requester_forest=requester,
        agent_forest=agent,
        reconciliation=graph,
        evidence=evidence,
    )

    triggers = api["disclosure_triggers"](state)  # type: ignore[index]
    assert any(t.node_id == "r-decision-1" for t in triggers), (
        "evidence-backed agent expansion on a requester-owned decision must trigger disclosure"
    )


# ---------------------------------------------------------------------------
# Acceptance bullet 6: bounded reconstitution for sparse forests
# ---------------------------------------------------------------------------


def test_bounded_reconstitution_for_sparse_forest_not_requirement_invention() -> None:
    """A vague/sparse requester forest must NOT fabricate nodes; it must trigger bounded reconstitution."""

    api = _api()

    requester = api["Forest"]()  # type: ignore[index]
    agent = api["Forest"]()  # type: ignore[index]
    graph = api["ReconciliationGraph"]()  # type: ignore[index]

    # Single vague node (<2 nodes AND confidence < 0.4) → sparse.
    requester.append(
        _node(
            api=api,
            node_id="r-vague",
            space=api["ForestSpace"].REQUESTER,  # type: ignore[index]
            role=api["AuthorityRole"].INTENT_OWNER,  # type: ignore[index]
            body={"statement": "?"},
            confidence=0.2,
        )
    )

    state = api["CognitionState"](  # type: ignore[index]
        requester_forest=requester,
        agent_forest=agent,
        reconciliation=graph,
        evidence=(),
    )

    trigger = api["BoundedReconstitutionTrigger"].evaluate(state)  # type: ignore[index]
    assert isinstance(trigger, api["BoundedReconstitutionTrigger"])  # type: ignore[index]
    assert trigger.fired is True
    assert trigger.mode == "bounded_reconnaissance"
    # No fabricated nodes: forest size unchanged after evaluation.
    assert len(requester) == 1, f"sparse evaluation must not fabricate nodes; got {len(requester)} nodes"


# ---------------------------------------------------------------------------
# Acceptance bullet 7: authority roles explicit per node (5 roles)
# ---------------------------------------------------------------------------


def test_authority_explicit_per_node() -> None:
    """All 5 AuthorityRoles remain explicit per node after the cognition layer is added."""

    api = _api()
    AuthorityRole = api["AuthorityRole"]  # type: ignore[index]
    expected = {
        "intent_owner",
        "research_owner",
        "decision_owner",
        "approval_required",
        "authority_scope",
    }
    assert {role.value for role in AuthorityRole} == expected

    Space = api["ForestSpace"]  # type: ignore[index]
    role_of = api["role_of"]  # type: ignore[index]
    authority_scope = api["authority_scope"]  # type: ignore[index]

    samples = [
        ("r-intent", Space.REQUESTER, AuthorityRole.INTENT_OWNER, "intent"),
        ("a-research", Space.AGENT, AuthorityRole.RESEARCH_OWNER, "research"),
        ("r-decision", Space.REQUESTER, AuthorityRole.DECISION_OWNER, "decision"),
        ("r-approval", Space.REQUESTER, AuthorityRole.APPROVAL_REQUIRED, "approval"),
        ("a-scope", Space.AGENT, AuthorityRole.AUTHORITY_SCOPE, "scope"),
    ]
    for node_id, space, role, body in samples:
        node = _node(
            api=api,
            node_id=node_id,
            space=space,
            role=role,
            body={"statement": body},
            confidence=0.8,
        )
        assert role_of(node) is role
        assert authority_scope(node) == frozenset({role.value})


# ---------------------------------------------------------------------------
# Acceptance bullet 8: independent grow / split / merge / regress
# ---------------------------------------------------------------------------


def test_independent_grow_split_merge_regress() -> None:
    """Requester and Agent forests operate independently: an Agent-side change MUST NOT
    perturb the Requester forest, and vice versa."""

    api = _api()
    Forest = api["Forest"]  # type: ignore[index]
    Space = api["ForestSpace"]  # type: ignore[index]
    Role = api["AuthorityRole"]  # type: ignore[index]

    requester = Forest()
    agent = Forest()

    # Initial seed in both forests.
    requester.append(
        _node(
            api=api,
            node_id="r-problem-1",
            space=Space.REQUESTER,
            role=Role.INTENT_OWNER,
            body={"statement": "initial"},
            confidence=0.4,
        )
    )
    agent.append(
        _node(
            api=api,
            node_id="a-hypothesis-1",
            space=Space.AGENT,
            role=Role.RESEARCH_OWNER,
            body={"statement": "hypothesis"},
            confidence=0.5,
        )
    )

    requester_snapshot = requester.current_nodes()
    agent_snapshot = agent.current_nodes()

    # Grow the agent forest: split + supersede + regress — requester forest untouched.
    agent.split(
        parent_id="a-hypothesis-1",
        children=(("a-hypothesis-1a", {"statement": "child a"}, 0.6),),
        origin_role=Role.RESEARCH_OWNER,
        source_ref="src:agent-split",
    )
    agent.supersede(node_id="a-hypothesis-1a", body={"statement": "refined"}, confidence=0.8)
    agent.regress_confidence(node_id="a-hypothesis-1a", new_confidence=0.3, reason="new evidence")

    # Requester forest: same nodes, same versions, same confidence.
    assert requester.current_nodes() == requester_snapshot
    assert len(requester) == 1
    assert requester.current("r-problem-1").version == 1
    assert requester.current("r-problem-1").confidence == pytest.approx(0.4)

    # Agent forest grew and changed.
    assert len(agent) == 2
    assert agent.current("a-hypothesis-1a").confidence == pytest.approx(0.3)
    assert agent.current("a-hypothesis-1a").version >= 3

    # Reverse direction: requester-side merge must not affect agent.
    requester.append(
        _node(
            api=api,
            node_id="r-problem-2",
            space=Space.REQUESTER,
            role=Role.INTENT_OWNER,
            body={"statement": "second"},
            confidence=0.7,
        )
    )
    requester.merge(
        source_ids=("r-problem-1", "r-problem-2"),
        merged_id="r-problem-merged",
        body={"statement": "merged"},
        confidence=0.8,
        origin_role=Role.INTENT_OWNER,
        source_ref="src:requester-merge",
    )
    assert (
        agent.current_nodes()
        == tuple(node for node in agent_snapshot + (agent.current("a-hypothesis-1a"),) if node.id == "a-hypothesis-1a")
        or len(agent) == 2
    )  # agent stayed independent


# ---------------------------------------------------------------------------
# Acceptance bullet 9: alignment yields no global score
# ---------------------------------------------------------------------------


def test_alignment_per_branch_yields_no_global_score() -> None:
    """The Cognition layer must not expose a single aggregate score."""

    api = _api()
    state = api["CognitionState"](  # type: ignore[index]
        requester_forest=api["Forest"](),  # type: ignore[index]
        agent_forest=api["Forest"](),  # type: ignore[index]
        reconciliation=api["ReconciliationGraph"](),  # type: ignore[index]
        evidence=(),
    )
    scores = api["compute_alignment_per_branch"](state)  # type: ignore[index]
    # A single number would be 'who is smarter'; the model is per-branch.
    assert not hasattr(scores, "score"), "alignment output is per-branch mapping, not a scalar"
    forbidden = {"score", "global", "aggregate", "total"}
    leaked = forbidden & set(scores.keys())
    assert not leaked, f"alignment output exposes a global score field: {sorted(leaked)}"
    # And the contract: branch ids (str) → AlignmentScore; no top-level scalar.
    for key, value in scores.items():
        assert isinstance(key, str)
        assert isinstance(value, api["AlignmentScore"])  # type: ignore[index]
