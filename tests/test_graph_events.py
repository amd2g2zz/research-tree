"""Graph event vocabulary + payload validation (issue #546, spec graph-store)."""

from __future__ import annotations

import pytest

from research_tree.graph_events import (
    GRAPH_EVENT_TYPES,
    GraphEventError,
    validate_graph_event,
)

CLAIM = {
    "id": "c1",
    "text": "rt works offline",
    "source": "user",
    "weight": "make_or_break",
    "posterior": 0.5,
    "verify_tier": "multi-source",
}

MINIMAL_PAYLOADS = {
    "claim.upsert": {"claim": dict(CLAIM)},
    "claim.kill_edge": {"claim_id": "c1", "kill_target_id": "c2"},
    "stage.upsert": {"stage": {"id": "s1", "title": "cluster", "status": "open"}},
    "stage.depends_on": {"stage_id": "s2", "depends_on_id": "s1"},
    "stage.contains": {"stage_id": "s1", "claim_id": "c1"},
    "evidence.upsert": {"evidence": {"id": "e1", "digest": "a" * 64, "origin": "origin.py"}},
    "evidence.attach": {"evidence_id": "e1", "claim_id": "c1"},
    "artifact.upsert": {"artifact": {"id": "a1", "kind": "finding-pack", "digest": "b" * 64}},
    "artifact.link": {"artifact_id": "a1", "claim_id": "c1"},
    "version.commit": {
        "version": {
            "id": "t1:0",
            "task_id": "t1",
            "v": 0,
            "commit_hash": "c" * 64,
            "verdict": "GO",
            "summary": "first commit",
        }
    },
    "fork.edge": {"child_version_id": "t2:0", "parent_version_id": "t1:0"},
}


@pytest.mark.parametrize("event_type", sorted(GRAPH_EVENT_TYPES))
def test_every_event_type_accepts_its_minimal_payload(event_type: str) -> None:
    normalized = validate_graph_event(event_type, MINIMAL_PAYLOADS[event_type])
    assert isinstance(normalized, dict)


def test_unknown_event_type_rejected() -> None:
    with pytest.raises(GraphEventError, match="unknown graph event type"):
        validate_graph_event("claim.teleport", {"claim_id": "c1"})


def test_payload_must_be_a_mapping() -> None:
    with pytest.raises(GraphEventError, match="payload must be a mapping"):
        validate_graph_event("claim.kill_edge", ["c1", "c2"])


def test_claim_upsert_fills_stale_default() -> None:
    normalized = validate_graph_event("claim.upsert", {"claim": dict(CLAIM)})
    assert normalized["claim"]["stale"] is False


def test_claim_upsert_rejects_posterior_out_of_range() -> None:
    bad = {"claim": {**CLAIM, "posterior": 1.5}}
    with pytest.raises(GraphEventError, match="posterior"):
        validate_graph_event("claim.upsert", bad)


def test_claim_upsert_rejects_unknown_weight() -> None:
    bad = {"claim": {**CLAIM, "weight": "load_bearing"}}
    with pytest.raises(GraphEventError, match="weight"):
        validate_graph_event("claim.upsert", bad)


def test_claim_upsert_rejects_unknown_source() -> None:
    bad = {"claim": {**CLAIM, "source": "vibes"}}
    with pytest.raises(GraphEventError, match="source"):
        validate_graph_event("claim.upsert", bad)


def test_claim_upsert_rejects_unknown_verify_tier() -> None:
    bad = {"claim": {**CLAIM, "verify_tier": "vibes"}}
    with pytest.raises(GraphEventError, match="verify_tier"):
        validate_graph_event("claim.upsert", bad)


def test_version_commit_rejects_unknown_verdict() -> None:
    version = dict(MINIMAL_PAYLOADS["version.commit"]["version"])
    version["verdict"] = "MAYBE"
    with pytest.raises(GraphEventError, match="verdict"):
        validate_graph_event("version.commit", {"version": version})


def test_version_commit_rejects_negative_v() -> None:
    version = dict(MINIMAL_PAYLOADS["version.commit"]["version"])
    version["v"] = -1
    with pytest.raises(GraphEventError, match="v"):
        validate_graph_event("version.commit", {"version": version})


def test_fork_edge_requires_distinct_ids() -> None:
    with pytest.raises(GraphEventError, match="distinct"):
        validate_graph_event("fork.edge", {"child_version_id": "t1:0", "parent_version_id": "t1:0"})


def test_missing_required_id_rejected() -> None:
    with pytest.raises(GraphEventError, match="claim_id"):
        validate_graph_event("claim.kill_edge", {"kill_target_id": "c2"})


def test_unknown_payload_keys_rejected() -> None:
    with pytest.raises(GraphEventError, match="unexpected keys"):
        validate_graph_event("claim.kill_edge", {"claim_id": "c1", "kill_target_id": "c2", "why": "nope"})
