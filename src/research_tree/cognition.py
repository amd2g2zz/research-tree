"""Canonical asymmetric cognitive model — issue #315.

Composes the four canonical spaces (requester, agent, shared, evidence)
with reconciliation edges into a single ``CognitionState``, then projects
that state into per-branch alignment scores. No global "who is smarter"
score is ever produced; per-branch scores are the only contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Iterable, Mapping

from .evidence import EvidenceArtifact
from .problem_forest import (
    AlignmentScore,
    Forest,
    ReconciliationGraph,
    ReconciliationKind,
    SharedForestFilter,
    UnderstandingDebt,
    _branch_id_of,
    _synthesize_missing_edges,
    compute_understanding_debt,
)

if TYPE_CHECKING:
    from .authority import AuthorityRole  # noqa: F401  (re-exported for downstream type hints)

EVIDENCE_AUTHORITATIVE_STATUSES: frozenset[str] = frozenset({"active"})
SHARED_FOREST_ALIGNMENT_KINDS: frozenset[ReconciliationKind] = frozenset(
    {ReconciliationKind.SAME_PROBLEM, ReconciliationKind.PARTIAL_MATCH}
)


@dataclass(slots=True)
class CognitionState:
    """The four canonical spaces + reconciliation + cached understanding debt.

    Forest itself is mutable so agents can append/supersede in place.
    ``evidence`` is held as a tuple to keep the dataclass hashable by
    intent; ``understanding_debt`` is computed lazily on first access via
    :meth:`debt`.
    """

    requester_forest: Forest
    agent_forest: Forest
    reconciliation: ReconciliationGraph
    evidence: tuple[EvidenceArtifact, ...] = ()
    _debt: UnderstandingDebt | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.requester_forest, Forest):
            raise TypeError("requester_forest must be a Forest")
        if not isinstance(self.agent_forest, Forest):
            raise TypeError("agent_forest must be a Forest")
        if not isinstance(self.reconciliation, ReconciliationGraph):
            raise TypeError("reconciliation must be a ReconciliationGraph")
        if not isinstance(self.evidence, tuple):
            raise TypeError("evidence must be a tuple of EvidenceArtifact")
        for artifact in self.evidence:
            if not isinstance(artifact, EvidenceArtifact):
                raise TypeError("evidence entries must be EvidenceArtifact instances")

    @property
    def shared_forest(self) -> tuple[object, ...]:
        """Aligned nodes, projected through :class:`SharedForestFilter`."""

        return SharedForestFilter().filter(
            requester_forest=self.requester_forest,
            agent_forest=self.agent_forest,
            reconciliation=self.reconciliation,
        )

    def debt(self) -> UnderstandingDebt:
        """Compute (and cache) the agent's self-computed UnderstandingDebt."""

        if self._debt is None:
            self._debt = compute_understanding_debt(
                requester_forest=self.requester_forest,
                agent_forest=self.agent_forest,
                reconciliation=self.reconciliation,
            )
        return self._debt


def _authoritative_evidence_by_id(evidence: Iterable[EvidenceArtifact]) -> Mapping[str, EvidenceArtifact]:
    return MappingProxyType(
        {artifact.evidence_id: artifact for artifact in evidence if artifact.status in EVIDENCE_AUTHORITATIVE_STATUSES}
    )


def _branch_alignment(
    *,
    branch_id: str,
    edges_for_branch: tuple[object, ...],
    coverage_total: int,
    requester_total: int,
) -> AlignmentScore:
    covered = sum(1 for edge in edges_for_branch if getattr(edge, "kind", None) in SHARED_FOREST_ALIGNMENT_KINDS)
    deltas = tuple(
        sorted(
            {
                getattr(edge, "kind")
                for edge in edges_for_branch
                if getattr(edge, "kind", None) not in SHARED_FOREST_ALIGNMENT_KINDS
            },
            key=lambda kind: kind.value,
        )
    )
    if coverage_total == 0:
        score = 0.0
    else:
        score = covered / coverage_total
    return AlignmentScore(
        branch_id=branch_id,
        score=float(score),
        covered_nodes=covered,
        unresolved_nodes=requester_total - covered,
        deltas=deltas,
    )


def compute_alignment_per_branch(state: CognitionState) -> dict[str, AlignmentScore]:
    """Per-(branch, dimension) alignment scores; never a global aggregate.

    Branches are derived from the ``branch_id`` body field on forest
    nodes. Nodes without a branch id fall under a single ``_unscoped``
    bucket so the projection is total over the requester forest.
    """

    if not isinstance(state, CognitionState):
        raise TypeError("state must be a CognitionState")

    requester_nodes_by_branch: dict[str, list[object]] = {}
    for node in state.requester_forest.current_nodes():
        branch = _branch_id_of(node) or "_unscoped"
        requester_nodes_by_branch.setdefault(branch, []).append(node)

    synthesized = _synthesize_missing_edges(state.requester_forest, state.reconciliation)
    all_edges = (*synthesized, *state.reconciliation.list_edges())
    edges_by_requester: dict[str, list[object]] = {}
    for edge in all_edges:
        edges_by_requester.setdefault(getattr(edge, "requester_ref"), []).append(edge)

    scores: dict[str, AlignmentScore] = {}
    for branch, nodes in sorted(requester_nodes_by_branch.items()):
        edges_for_branch = tuple(edge for node in nodes for edge in edges_by_requester.get(node.id, ()))
        scores[branch] = _branch_alignment(
            branch_id=branch,
            edges_for_branch=edges_for_branch,
            coverage_total=len(nodes),
            requester_total=len(nodes),
        )
    return scores


__all__ = [
    "CognitionState",
    "EVIDENCE_AUTHORITATIVE_STATUSES",
    "SHARED_FOREST_ALIGNMENT_KINDS",
    "compute_alignment_per_branch",
]
