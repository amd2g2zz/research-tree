"""Issue #321: Shared Brief workspace with a verifiable interaction evidence chain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class BriefNode:
    """One brief node carrying the full provenance required by issue #321."""

    id: str
    space: str
    origin_role: str
    source_ref: str
    timestamp: str
    version: int
    body: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    """A verified link from a brief node to its underlying evidence."""

    node_id: str
    evidence_refs: tuple[str, ...]


@dataclass
class BriefWorkspace:
    """Mutable workspace; the append/record operations build the evidence chain."""

    requester_nodes: list[BriefNode] = field(default_factory=list)
    agent_nodes: list[BriefNode] = field(default_factory=list)
    shared_nodes: list[BriefNode] = field(default_factory=list)
    reconciliation: list[dict[str, object]] = field(default_factory=list)
    evidence_chain: list[EvidenceLink] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "requester_nodes": [
                {
                    "id": n.id,
                    "space": n.space,
                    "origin_role": n.origin_role,
                    "source_ref": n.source_ref,
                    "timestamp": n.timestamp,
                    "version": n.version,
                    "body": dict(n.body),
                }
                for n in self.requester_nodes
            ],
            "agent_nodes": [
                {
                    "id": n.id,
                    "space": n.space,
                    "origin_role": n.origin_role,
                    "source_ref": n.source_ref,
                    "timestamp": n.timestamp,
                    "version": n.version,
                    "body": dict(n.body),
                }
                for n in self.agent_nodes
            ],
            "shared_nodes": [
                {
                    "id": n.id,
                    "space": n.space,
                    "origin_role": n.origin_role,
                    "source_ref": n.source_ref,
                    "timestamp": n.timestamp,
                    "version": n.version,
                    "body": dict(n.body),
                }
                for n in self.shared_nodes
            ],
            "reconciliation": list(self.reconciliation),
            "evidence_chain": [
                {"node_id": link.node_id, "evidence_refs": list(link.evidence_refs)} for link in self.evidence_chain
            ],
        }


@dataclass(frozen=True, slots=True)
class SharedBrief:
    """Read-only projection: consensus + visible unresolved deltas."""

    consensus_nodes: tuple[dict[str, object], ...]
    consensus_mappings: tuple[dict[str, object], ...]
    unresolved_mappings: tuple[dict[str, object], ...]

    @classmethod
    def from_workspace(cls, workspace: BriefWorkspace) -> "SharedBrief":
        consensus_nodes = tuple(node.__dict__ for node in workspace.shared_nodes)
        consensus_mappings = tuple(mapping for mapping in workspace.reconciliation if not mapping.get("unresolved"))
        unresolved_mappings = tuple(mapping for mapping in workspace.reconciliation if mapping.get("unresolved"))
        return cls(
            consensus_nodes=consensus_nodes,
            consensus_mappings=consensus_mappings,
            unresolved_mappings=unresolved_mappings,
        )


def append_node(workspace: BriefWorkspace, node: BriefNode) -> BriefWorkspace:
    """Add a node to the appropriate space bucket."""

    if node.space == "requester":
        workspace.requester_nodes.append(node)
    elif node.space == "agent":
        workspace.agent_nodes.append(node)
    elif node.space == "shared":
        workspace.shared_nodes.append(node)
    else:
        raise ValueError(f"unknown space: {node.space}")
    return workspace


def record_evidence_link(workspace: BriefWorkspace, node_id: str, *, evidence_refs: Sequence[str]) -> BriefWorkspace:
    """Append an EvidenceLink to the chain."""

    workspace.evidence_chain.append(EvidenceLink(node_id=node_id, evidence_refs=tuple(evidence_refs)))
    return workspace
