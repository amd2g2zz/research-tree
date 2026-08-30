"""Issue #321: Shared Brief workspace with a verifiable interaction evidence chain."""

from __future__ import annotations

from research_tree.shared_brief import (
    BriefNode,
    BriefWorkspace,
    SharedBrief,
    append_node,
    record_evidence_link,
)


def test_brief_node_carries_space_identity_role_source_timestamp_version() -> None:
    node = BriefNode(
        id="brief-1",
        space="requester",
        origin_role="intent_owner",
        source_ref="forest:req-node-1",
        timestamp="2026-08-30T00:00:00+00:00",
        version=1,
        body={"title": "decide on cache strategy"},
    )
    assert node.id == "brief-1"
    assert node.space == "requester"
    assert node.origin_role == "intent_owner"
    assert node.timestamp == "2026-08-30T00:00:00+00:00"
    assert node.version == 1


def test_append_node_records_evidence_chain() -> None:
    workspace = BriefWorkspace()
    node = BriefNode(
        id="brief-1",
        space="requester",
        origin_role="intent_owner",
        source_ref="forest:req-node-1",
        timestamp="2026-08-30T00:00:00+00:00",
        version=1,
        body={"title": "x"},
    )
    record_evidence_link(workspace, node.id, evidence_refs=("e1", "e2"))
    updated = append_node(workspace, node)
    assert updated.evidence_chain[-1].node_id == "brief-1"
    assert updated.evidence_chain[-1].evidence_refs == ("e1", "e2")


def test_shared_brief_hides_unresolved_deltas() -> None:
    """Unresolved mappings live outside the consensus brief but are visible."""

    workspace = BriefWorkspace()
    # Two requests (requester + agent) with a partial_match reconciliation
    workspace.requester_nodes.append(
        BriefNode(
            id="r1",
            space="requester",
            origin_role="intent_owner",
            source_ref="r1",
            timestamp="2026-08-30T00:00:00+00:00",
            version=1,
            body={"title": "x"},
        )
    )
    workspace.agent_nodes.append(
        BriefNode(
            id="a1",
            space="agent",
            origin_role="research_owner",
            source_ref="a1",
            timestamp="2026-08-30T00:00:00+00:00",
            version=1,
            body={"title": "y"},
        )
    )
    workspace.reconciliation.append({"from_ref": "r1", "to_ref": "a1", "kind": "partial_match", "unresolved": True})
    brief = SharedBrief.from_workspace(workspace)
    # Unresolved mapping must NOT be in the consensus brief
    assert all(m["kind"] != "partial_match" or not m["unresolved"] for m in brief.consensus_mappings)
    # But it is visible in the unresolved view
    assert any(m["unresolved"] for m in brief.unresolved_mappings)


def test_brief_workspace_to_dict_is_canonical() -> None:
    workspace = BriefWorkspace()
    node = BriefNode(
        id="brief-1",
        space="requester",
        origin_role="intent_owner",
        source_ref="r1",
        timestamp="2026-08-30T00:00:00+00:00",
        version=1,
        body={"title": "x"},
    )
    append_node(workspace, node)
    record_evidence_link(workspace, node.id, evidence_refs=("e1",))
    snapshot = workspace.to_dict()
    assert snapshot["requester_nodes"][0]["id"] == "brief-1"
    assert len(snapshot["evidence_chain"]) == 1
    assert snapshot["evidence_chain"][0]["evidence_refs"] == ["e1"]


def test_consensus_brief_only_includes_resolved_mappings() -> None:
    workspace = BriefWorkspace()
    workspace.reconciliation.append({"from_ref": "r1", "to_ref": "a1", "kind": "same_problem", "unresolved": False})
    workspace.reconciliation.append({"from_ref": "r2", "to_ref": "a2", "kind": "contradiction", "unresolved": True})
    brief = SharedBrief.from_workspace(workspace)
    assert len(brief.consensus_mappings) == 1
    assert brief.consensus_mappings[0]["kind"] == "same_problem"
