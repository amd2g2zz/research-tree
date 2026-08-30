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
from typing import Iterable, Mapping

from .authority import AuthorityRole
from .domain import freeze_payload, utc_now, validate_identifier

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
