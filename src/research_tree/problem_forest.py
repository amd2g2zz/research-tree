"""Problem Forest — issue #314.

Five spaces (requester, agent, shared, reconciliation, evidence) keep the
Brief, the agent's structured understanding, and the provenance chain
separable. Both requester and agent forests can grow / contract / split /
merge / regress independently. Raw private chain-of-thought has no field
to live in — by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Iterable, Mapping

from .authority import AuthorityRole
from .domain import freeze_payload, utc_now, validate_identifier

if TYPE_CHECKING:
    from .cognition import CognitionState

RECONCILIATION_KIND_VALUES: frozenset[str] = frozenset(
    {
        "same_problem",
        "partial_match",
        "missing_in_agent",
        "agent_expansion_unconfirmed",
        "topology_mismatch",
        "oracle_mismatch",
        "contradiction",
        "superseded",
    }
)


class ForestSpace(Enum):
    """Which space a node lives in. Determines visibility and authority rules."""

    REQUESTER = "requester"
    AGENT = "agent"
    SHARED = "shared"
    RECONCILIATION = "reconciliation"
    EVIDENCE = "evidence"


class ReconciliationKind(Enum):
    """Edge kind between Requester and Agent forest nodes."""

    SAME_PROBLEM = "same_problem"
    PARTIAL_MATCH = "partial_match"
    MISSING_IN_AGENT = "missing_in_agent"
    AGENT_EXPANSION_UNCONFIRMED = "agent_expansion_unconfirmed"
    TOPOLOGY_MISMATCH = "topology_mismatch"
    ORACLE_MISMATCH = "oracle_mismatch"
    CONTRADICTION = "contradiction"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class ForestNode:
    """An immutable record in one forest space.

    Stable identity is ``id``; ``version`` increments on supersede /
    regress_confidence. ``body`` is an immutable JSON-compatible mapping.
    There is no chain-of-thought field — by construction the agent forest
    cannot store raw private reasoning.
    """

    id: str
    space: ForestSpace
    origin_role: AuthorityRole
    source_ref: str
    timestamp: str
    version: int
    body: Mapping[str, object]
    confidence: float
    parent_of: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.id, "node_id")
        if not isinstance(self.space, ForestSpace):
            raise TypeError(f"space must be a ForestSpace; got {type(self.space).__name__}")
        if not isinstance(self.origin_role, AuthorityRole):
            raise TypeError(f"origin_role must be an AuthorityRole; got {type(self.origin_role).__name__}")
        if not isinstance(self.source_ref, str) or not self.source_ref.strip():
            raise ValueError("source_ref must be a non-empty string")
        if not isinstance(self.timestamp, str) or "T" not in self.timestamp:
            raise ValueError("timestamp must be an ISO-8601 string")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")
        confidence = self.confidence
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError("confidence must be a number")
        if not 0.0 <= float(confidence) <= 1.0:
            raise ValueError("confidence must be within [0.0, 1.0]")
        if not isinstance(self.body, Mapping):
            raise TypeError("body must be a mapping")
        if self.parent_of is not None:
            validate_identifier(self.parent_of, "parent_of")

    @classmethod
    def create(
        cls,
        *,
        node_id: str,
        space: ForestSpace,
        origin_role: AuthorityRole,
        source_ref: str,
        body: Mapping[str, object],
        confidence: float,
        version: int = 1,
        parent_of: str | None = None,
        timestamp: str | None = None,
    ) -> "ForestNode":
        """Factory: freezes body and stamps ``timestamp`` if not supplied."""

        frozen_body = MappingProxyType(dict(freeze_payload(dict(body))))
        return cls(
            id=node_id,
            space=space,
            origin_role=origin_role,
            source_ref=source_ref,
            timestamp=timestamp or utc_now(),
            version=version,
            body=frozen_body,
            confidence=float(confidence),
            parent_of=parent_of,
        )


@dataclass(frozen=True, slots=True)
class ReconciliationMapping:
    """One edge between a requester node and an agent node."""

    kind: ReconciliationKind
    requester_ref: str
    agent_ref: str
    note: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ReconciliationKind):
            raise TypeError(f"kind must be a ReconciliationKind; got {type(self.kind).__name__}")
        validate_identifier(self.requester_ref, "requester_ref")
        validate_identifier(self.agent_ref, "agent_ref")
        if not isinstance(self.note, str):
            raise TypeError("note must be a string")


def _freeze_nodes(mapping: Mapping[str, ForestNode]) -> MappingProxyType[str, ForestNode]:
    return MappingProxyType(dict(mapping))


@dataclass(slots=True)
class Forest:
    """A forest of immutable ``ForestNode`` records.

    Forest itself is mutable; lifecycle ops mutate in place AND return new
    node refs. Nodes stay frozen/immutable per the issue contract; only the
    container is mutable because operations like split/merge naturally
    add many nodes at once and updating the test contract to thread a
    fresh forest through every call adds noise without buying safety.
    """

    _current: dict[str, ForestNode] = field(default_factory=dict)
    _superseded: dict[str, tuple[ForestNode, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._current = {key: value for key, value in self._current.items()}
        self._superseded = {key: tuple(value) for key, value in self._superseded.items()}

    def __len__(self) -> int:
        return len(self._current)

    def __iter__(self):
        return iter(self._current.values())

    def current(self, node_id: str) -> ForestNode:
        try:
            return self._current[node_id]
        except KeyError as error:
            raise KeyError(f"unknown node id: {node_id}") from error

    def current_nodes(self) -> tuple[ForestNode, ...]:
        return tuple(self._current.values())

    def is_superseded(self, node_id: str) -> bool:
        return node_id in self._superseded

    def superseded_history(self, node_id: str) -> tuple[ForestNode, ...]:
        return self._superseded.get(node_id, ())

    def append(self, node: ForestNode) -> "Forest":
        """Add a fresh node to the forest. Returns self for chaining."""

        if not isinstance(node, ForestNode):
            raise TypeError(f"append requires a ForestNode; got {type(node).__name__}")
        if node.id in self._current:
            raise ValueError(f"node id already present; use supersede: {node.id}")
        self._current[node.id] = node
        return self

    def supersede(self, *, node_id: str, body: Mapping[str, object], confidence: float) -> ForestNode:
        if node_id not in self._current:
            raise KeyError(f"cannot supersede unknown node: {node_id}")
        current = self._current[node_id]
        next_node = ForestNode.create(
            node_id=node_id,
            space=current.space,
            origin_role=current.origin_role,
            source_ref=current.source_ref,
            body=body,
            confidence=confidence,
            version=current.version + 1,
            parent_of=current.parent_of,
        )
        self._superseded[node_id] = self._superseded.get(node_id, ()) + (current,)
        self._current[node_id] = next_node
        return next_node

    def split(
        self,
        *,
        parent_id: str,
        children: tuple[tuple[str, Mapping[str, object], float], ...],
        origin_role: AuthorityRole,
        source_ref: str,
    ) -> tuple[ForestNode, ...]:
        if parent_id not in self._current:
            raise KeyError(f"cannot split unknown node: {parent_id}")
        if not children:
            raise ValueError("split requires at least one child")
        created: list[ForestNode] = []
        for child_id, body, confidence in children:
            if child_id in self._current:
                raise ValueError(f"split child id already exists: {child_id}")
            child = ForestNode.create(
                node_id=child_id,
                space=self._current[parent_id].space,
                origin_role=origin_role,
                source_ref=source_ref,
                body=body,
                confidence=confidence,
                parent_of=parent_id,
            )
            self._current[child_id] = child
            created.append(child)
        return tuple(created)

    def merge(
        self,
        *,
        source_ids: Iterable[str],
        merged_id: str,
        body: Mapping[str, object],
        confidence: float,
        origin_role: AuthorityRole,
        source_ref: str,
    ) -> ForestNode:
        sources = tuple(source_ids)
        if not sources:
            raise ValueError("merge requires at least one source id")
        space: ForestSpace | None = None
        for source_id in sources:
            if source_id not in self._current:
                raise KeyError(f"cannot merge unknown node: {source_id}")
            node = self._current[source_id]
            space = node.space if space is None else space
            if node.space is not space:
                raise ValueError("merged nodes must share a space")
        if merged_id in self._current:
            raise ValueError(f"merged id already exists: {merged_id}")
        assert space is not None  # guarded by loop above
        merged = ForestNode.create(
            node_id=merged_id,
            space=space,
            origin_role=origin_role,
            source_ref=source_ref,
            body=body,
            confidence=confidence,
        )
        self._current[merged_id] = merged
        for source_id in sources:
            source = self._current[source_id]
            self.supersede(
                node_id=source_id,
                body=dict(source.body),
                confidence=source.confidence,
            )
        return self._current[merged_id]

    def regress_confidence(self, *, node_id: str, new_confidence: float, reason: str) -> ForestNode:
        if node_id not in self._current:
            raise KeyError(f"cannot regress unknown node: {node_id}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("regress reason must be a non-empty string")
        current = self._current[node_id]
        body = dict(current.body)
        body["regress_reason"] = reason
        next_node = ForestNode.create(
            node_id=node_id,
            space=current.space,
            origin_role=current.origin_role,
            source_ref=current.source_ref,
            body=body,
            confidence=new_confidence,
            version=current.version + 1,
            parent_of=current.parent_of,
        )
        self._superseded[node_id] = self._superseded.get(node_id, ()) + (current,)
        self._current[node_id] = next_node
        return next_node

    def needs_bounded_reconnaissance(self) -> bool:
        """Trigger bounded reconnaissance when intent is vague.

        Either: fewer than two nodes, or average confidence below 0.4.
        """

        nodes = self.current_nodes()
        if len(nodes) < 2:
            return True
        average = sum(node.confidence for node in nodes) / len(nodes)
        return average < 0.4


@dataclass(slots=True)
class ReconciliationGraph:
    """An append-only graph of Requester↔Agent mappings."""

    _edges: list[ReconciliationMapping] = field(default_factory=list)

    def add(self, mapping: ReconciliationMapping) -> ReconciliationMapping:
        if not isinstance(mapping, ReconciliationMapping):
            raise TypeError(f"add requires a ReconciliationMapping; got {type(mapping).__name__}")
        self._edges.append(mapping)
        return mapping

    def remove(self, *, requester_ref: str, agent_ref: str) -> bool:
        before = len(self._edges)
        self._edges[:] = [
            edge for edge in self._edges if not (edge.requester_ref == requester_ref and edge.agent_ref == agent_ref)
        ]
        return len(self._edges) < before

    def list_edges(self) -> tuple[ReconciliationMapping, ...]:
        return tuple(self._edges)


@dataclass(frozen=True, slots=True)
class SharedBriefView:
    """Read-only projection: aligned nodes → shared space; deltas stay outside."""

    requester_forest: Forest
    agent_forest: Forest
    reconciliation: ReconciliationGraph

    def iter_shared(self) -> Iterable[ForestNode]:
        aligned_requester: set[str] = set()
        for edge in self.reconciliation.list_edges():
            if edge.kind in (
                ReconciliationKind.SAME_PROBLEM,
                ReconciliationKind.PARTIAL_MATCH,
                ReconciliationKind.SUPERSEDED,
            ):
                aligned_requester.add(edge.requester_ref)
        for node in self.requester_forest.current_nodes():
            if node.id in aligned_requester:
                yield node

    def iter_unresolved_deltas(self) -> Iterable[ReconciliationMapping]:
        """Edges that flag gaps/mismatches — visible outside the shared view.

        Synthesizes ``MISSING_IN_AGENT`` for any requester node that has no
        edge from the reconciliation graph, so gaps cannot hide behind a
        thin graph.
        """

        delta_kinds = {
            ReconciliationKind.MISSING_IN_AGENT,
            ReconciliationKind.AGENT_EXPANSION_UNCONFIRMED,
            ReconciliationKind.TOPOLOGY_MISMATCH,
            ReconciliationKind.ORACLE_MISMATCH,
            ReconciliationKind.CONTRADICTION,
        }
        referenced: set[str] = set()
        for edge in self.reconciliation.list_edges():
            if edge.kind in delta_kinds:
                yield edge
            referenced.add(edge.requester_ref)
        for node in self.requester_forest.current_nodes():
            if node.space is not ForestSpace.REQUESTER:
                continue
            if node.id not in referenced:
                yield ReconciliationMapping(
                    kind=ReconciliationKind.MISSING_IN_AGENT,
                    requester_ref=node.id,
                    agent_ref="unmapped",
                    note="synthesized: no agent counterpart",
                )


class AgentForest(Forest):
    """Typed alias: agent-space forest. Same lifecycle; distinct import name.

    Structural note: ``ForestNode`` carries no chain-of-thought field — by
    construction the agent forest cannot store raw private reasoning.
    """


# ---------------------------------------------------------------------------
# Issue #315 — asymmetric cognitive model
# ---------------------------------------------------------------------------


SHARED_FOREST_ALIGNMENT_KINDS: frozenset[ReconciliationKind] = frozenset(
    {ReconciliationKind.SAME_PROBLEM, ReconciliationKind.PARTIAL_MATCH}
)


@dataclass(frozen=True, slots=True)
class AlignmentScore:
    """Per-(branch, dimension) alignment score.

    The system never collapses alignment into a single global number.
    ``score`` lives in [0.0, 1.0] and represents the coverage ratio for one
    branch (or branch/dimension cell). ``deltas`` lists the unresolved
    mappings that depress the score so consumers can see *why* a branch is
    under-aligned.
    """

    branch_id: str
    score: float
    covered_nodes: int
    unresolved_nodes: int
    deltas: tuple[ReconciliationKind, ...] = ()

    def __post_init__(self) -> None:
        validate_identifier(self.branch_id, "branch_id")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise TypeError("score must be a number")
        score = float(self.score)
        if not 0.0 <= score <= 1.0:
            raise ValueError("score must be within [0.0, 1.0]")
        if isinstance(self.covered_nodes, bool) or not isinstance(self.covered_nodes, int) or self.covered_nodes < 0:
            raise ValueError("covered_nodes must be a non-negative integer")
        if (
            isinstance(self.unresolved_nodes, bool)
            or not isinstance(self.unresolved_nodes, int)
            or self.unresolved_nodes < 0
        ):
            raise ValueError("unresolved_nodes must be a non-negative integer")
        for kind in self.deltas:
            if not isinstance(kind, ReconciliationKind):
                raise TypeError(f"deltas must be ReconciliationKind entries; got {type(kind).__name__}")


class SharedForestFilter:
    """Project Requester+Agent+Reconciliation into the consensus Shared Forest.

    Only nodes whose reconciliation edges are ``same_problem`` or
    ``partial_match`` *and* are not flagged by any delta edge reach the
    shared view. Unresolved mappings stay in the Shared Brief workspace —
    visible to humans — but never claim consensus.
    """

    def filter(
        self,
        *,
        requester_forest: Forest,
        agent_forest: Forest,
        reconciliation: ReconciliationGraph,
    ) -> tuple[ForestNode, ...]:
        if not isinstance(requester_forest, Forest):
            raise TypeError("requester_forest must be a Forest")
        if not isinstance(agent_forest, Forest):
            raise TypeError("agent_forest must be a Forest")
        if not isinstance(reconciliation, ReconciliationGraph):
            raise TypeError("reconciliation must be a ReconciliationGraph")
        # Any edge that is NOT an alignment edge disqualifies a requester node.
        disqualifying: set[str] = set()
        aligned: set[str] = set()
        for edge in reconciliation.list_edges():
            if edge.kind in SHARED_FOREST_ALIGNMENT_KINDS:
                aligned.add(edge.requester_ref)
            else:
                disqualifying.add(edge.requester_ref)
        shared: list[ForestNode] = []
        for node in requester_forest.current_nodes():
            if node.space is not ForestSpace.REQUESTER:
                continue
            if node.id in aligned and node.id not in disqualifying:
                shared.append(node)
        return tuple(shared)


@dataclass(frozen=True, slots=True)
class UnderstandingDebt:
    """The Agent's self-computed debt of unresolved Requester-owned items.

    Pure projection over (Forest, Forest, ReconciliationGraph) — no
    side effects, no I/O. ``research_obligations`` lists branch ids that
    still need an aligned counterpart (or a recorded disagreement).
    """

    missing_in_agent: tuple[str, ...]
    agent_expansion_unconfirmed: tuple[str, ...]
    active_disagreements: tuple[str, ...]
    research_obligations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "missing_in_agent",
            "agent_expansion_unconfirmed",
            "active_disagreements",
            "research_obligations",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
                raise TypeError(f"{field_name} must be a tuple of strings")


def _synthesize_missing_edges(
    requester_forest: Forest,
    reconciliation: ReconciliationGraph,
) -> tuple[ReconciliationMapping, ...]:
    """Yield synthetic MISSING_IN_AGENT edges for unmapped requester nodes."""

    referenced: set[str] = set()
    for edge in reconciliation.list_edges():
        referenced.add(edge.requester_ref)
    synthesized: list[ReconciliationMapping] = []
    for node in requester_forest.current_nodes():
        if node.space is not ForestSpace.REQUESTER:
            continue
        if node.id in referenced:
            continue
        synthesized.append(
            ReconciliationMapping(
                kind=ReconciliationKind.MISSING_IN_AGENT,
                requester_ref=node.id,
                agent_ref="unmapped",
                note="synthesized: no agent counterpart",
            )
        )
    return tuple(synthesized)


def _branch_id_of(node: ForestNode) -> str | None:
    body = node.body
    candidate = body.get("branch_id") if hasattr(body, "get") else None
    if isinstance(candidate, str) and candidate:
        return candidate
    return None


def compute_understanding_debt(
    *,
    requester_forest: Forest,
    agent_forest: Forest,
    reconciliation: ReconciliationGraph,
) -> UnderstandingDebt:
    """Compute the agent's self-computed UnderstandingDebt (pure function)."""

    if not isinstance(requester_forest, Forest):
        raise TypeError("requester_forest must be a Forest")
    if not isinstance(agent_forest, Forest):
        raise TypeError("agent_forest must be a Forest")
    if not isinstance(reconciliation, ReconciliationGraph):
        raise TypeError("reconciliation must be a ReconciliationGraph")

    synthesized = _synthesize_missing_edges(requester_forest, reconciliation)
    missing_ids: list[str] = []
    expansion_ids: list[str] = []
    disagreement_ids: list[str] = []
    for edge in (*synthesized, *reconciliation.list_edges()):
        if edge.kind is ReconciliationKind.MISSING_IN_AGENT:
            missing_ids.append(edge.requester_ref)
        elif edge.kind is ReconciliationKind.AGENT_EXPANSION_UNCONFIRMED:
            expansion_ids.append(edge.requester_ref)
        elif edge.kind in {
            ReconciliationKind.CONTRADICTION,
            ReconciliationKind.TOPOLOGY_MISMATCH,
            ReconciliationKind.ORACLE_MISMATCH,
        }:
            disagreement_ids.append(edge.requester_ref)

    # Branches present in the requester forest without any aligned counterpart.
    aligned_branches: set[str] = set()
    requester_branches: set[str] = set()
    for node in requester_forest.current_nodes():
        branch = _branch_id_of(node)
        if branch is not None:
            requester_branches.add(branch)
    for edge in reconciliation.list_edges():
        if edge.kind not in SHARED_FOREST_ALIGNMENT_KINDS:
            continue
        requester_node = requester_forest._current.get(edge.requester_ref)  # type: ignore[attr-defined]
        if requester_node is None:
            continue
        branch = _branch_id_of(requester_node)
        if branch is not None:
            aligned_branches.add(branch)
    obligations = tuple(sorted(requester_branches - aligned_branches))

    return UnderstandingDebt(
        missing_in_agent=tuple(missing_ids),
        agent_expansion_unconfirmed=tuple(expansion_ids),
        active_disagreements=tuple(disagreement_ids),
        research_obligations=obligations,
    )


def catch_up_triggers(debt: UnderstandingDebt) -> tuple[str, ...]:
    """Return catch-up event ids: every node missing in the agent forest."""

    if not isinstance(debt, UnderstandingDebt):
        raise TypeError("debt must be an UnderstandingDebt")
    return debt.missing_in_agent


@dataclass(frozen=True, slots=True)
class DisclosureTrigger:
    """Disclosure event id: agent expansion that affects a requester-owned decision."""

    node_id: str
    agent_ref: str
    evidence_id: str
    reason: str

    def __post_init__(self) -> None:
        validate_identifier(self.node_id, "node_id")
        if not isinstance(self.agent_ref, str) or not self.agent_ref:
            raise ValueError("agent_ref must be a non-empty string")
        if not isinstance(self.evidence_id, str) or not self.evidence_id:
            raise ValueError("evidence_id must be a non-empty string")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("reason must be a non-empty string")


_DECISION_OWNING_ROLES: frozenset[AuthorityRole] = frozenset(
    {AuthorityRole.DECISION_OWNER, AuthorityRole.APPROVAL_REQUIRED, AuthorityRole.AUTHORITY_SCOPE}
)


def disclosure_triggers(state: "CognitionState") -> tuple[DisclosureTrigger, ...]:
    """Return disclosure triggers for evidence-backed agent expansions on requester-owned decisions.

    A trigger fires when:
    * a requester node has a DECISION_OWNER/APPROVAL_REQUIRED/AUTHORITY_SCOPE role,
    * the reconciliation graph carries an AGENT_EXPANSION_UNCONFIRMED edge for it,
    * the agent's body references evidence that is present in ``state.evidence``.
    """

    if state is None or not hasattr(state, "evidence"):
        raise TypeError("disclosure_triggers requires a CognitionState")
    evidence_by_id: dict[str, object] = {
        getattr(artifact, "evidence_id", None): artifact for artifact in state.evidence
    }
    triggers: list[DisclosureTrigger] = []
    for edge in state.reconciliation.list_edges():
        if edge.kind is not ReconciliationKind.AGENT_EXPANSION_UNCONFIRMED:
            continue
        requester_node = state.requester_forest._current.get(edge.requester_ref)  # type: ignore[attr-defined]
        if requester_node is None or requester_node.origin_role not in _DECISION_OWNING_ROLES:
            continue
        agent_node = state.agent_forest._current.get(edge.agent_ref)  # type: ignore[attr-defined]
        if agent_node is None:
            continue
        body = agent_node.body
        evidence_id = body.get("evidence_id") if hasattr(body, "get") else None
        evidence_backed = body.get("evidence_backed") if hasattr(body, "get") else False
        if not isinstance(evidence_id, str) or not isinstance(evidence_backed, bool) or not evidence_backed:
            continue
        if evidence_id not in evidence_by_id:
            continue
        triggers.append(
            DisclosureTrigger(
                node_id=edge.requester_ref,
                agent_ref=edge.agent_ref,
                evidence_id=evidence_id,
                reason="evidence-backed agent expansion on requester-owned decision",
            )
        )
    return tuple(triggers)


@dataclass(slots=True)
class BoundedReconstitutionTrigger:
    """Signal that the Requester Forest is too sparse for normal cognition.

    ``mode == "bounded_reconnaissance"`` means the agent must READ context
    (not invent requirements) to fill the gap. ``mode == "none"`` means no
    trigger. The trigger never mutates either forest.
    """

    fired: bool
    mode: str
    reason: str

    @classmethod
    def evaluate(cls, state: "CognitionState") -> "BoundedReconstitutionTrigger":
        if state is None or not hasattr(state, "requester_forest"):
            raise TypeError("BoundedReconstitutionTrigger.evaluate requires a CognitionState")
        nodes = state.requester_forest.current_nodes()
        if len(nodes) < 2:
            return cls(fired=True, mode="bounded_reconnaissance", reason="fewer than 2 requester nodes")
        average = sum(node.confidence for node in nodes) / len(nodes)
        if average < 0.4:
            return cls(
                fired=True,
                mode="bounded_reconnaissance",
                reason=f"mean confidence below 0.4 (got {average:.3f})",
            )
        return cls(fired=False, mode="none", reason="forest dense and confident")
