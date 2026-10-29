"""Kùzu projection: apply/rebuild/snapshot/lineage (issue #546, spec graph-store)."""

from __future__ import annotations

import pytest

from research_tree.graph_events import validate_graph_event
from research_tree.graph_store import GraphStore

CLAIM_A = {
    "id": "c1",
    "text": "rt works offline",
    "source": "user",
    "weight": "make_or_break",
    "posterior": 0.5,
    "verify_tier": "multi-source",
}
CLAIM_B = {
    "id": "c2",
    "text": "kuzu replay is deterministic",
    "source": "research",
    "weight": "important",
    "posterior": 0.9,
    "verify_tier": "rederive",
}


def _records(*pairs: tuple[str, dict]) -> list[dict]:
    """Turn (type, payload) pairs into log-shaped records with distinct created_at."""
    return [
        {
            "seq": index,
            "run_id": None,
            "event_type": kind,
            "payload": payload,
            "created_at": f"2026-10-29T00:00:{index:02d}Z",
        }
        for index, (kind, payload) in enumerate(pairs, start=1)
    ]


def _sample_events() -> list[dict]:
    return _records(
        ("claim.upsert", {"claim": dict(CLAIM_A)}),
        ("claim.upsert", {"claim": dict(CLAIM_B)}),
        ("claim.kill_edge", {"claim_id": "c2", "kill_target_id": "c1"}),
        ("stage.upsert", {"stage": {"id": "s1", "title": "cluster", "status": "open"}}),
        ("stage.contains", {"stage_id": "s1", "claim_id": "c1"}),
        ("evidence.upsert", {"evidence": {"id": "e1", "digest": "a" * 64, "origin": "origin.py"}}),
        ("evidence.attach", {"evidence_id": "e1", "claim_id": "c1"}),
        ("artifact.upsert", {"artifact": {"id": "a1", "kind": "finding-pack", "digest": "b" * 64}}),
        ("artifact.link", {"artifact_id": "a1", "claim_id": "c1"}),
        (
            "version.commit",
            {
                "version": {
                    "id": "t1:0",
                    "task_id": "t1",
                    "v": 0,
                    "commit_hash": "c" * 64,
                    "verdict": "GO",
                    "summary": "first",
                }
            },
        ),
        (
            "version.commit",
            {
                "version": {
                    "id": "t2:0",
                    "task_id": "t2",
                    "v": 0,
                    "commit_hash": "d" * 64,
                    "verdict": "PARK",
                    "summary": "fork",
                }
            },
        ),
        ("fork.edge", {"child_version_id": "t2:0", "parent_version_id": "t1:0"}),
    )


def test_apply_claim_upsert_is_queryable(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    store.apply_event(_records(("claim.upsert", {"claim": dict(CLAIM_A)}))[0])
    snapshot = store.snapshot_state()
    assert snapshot["Claim"]["c1"]["text"] == "rt works offline"
    assert snapshot["Claim"]["c1"]["posterior"] == 0.5


def test_apply_event_twice_is_idempotent(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    event = _records(("claim.upsert", {"claim": dict(CLAIM_A)}))[0]
    store.apply_event(event)
    first = store.snapshot_state()
    store.apply_event(event)
    assert store.snapshot_state() == first


def test_edges_are_idempotent(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    events = _sample_events()
    for record in events:
        store.apply_event(record)
    first = store.snapshot_state()
    for record in events[:3]:
        store.apply_event(record)
    assert store.snapshot_state() == first


def test_rebuild_equals_incremental_state(tmp_path) -> None:
    events = _sample_events()
    incremental = GraphStore(tmp_path / "incremental.kuzu")
    for record in events:
        incremental.apply_event(record)
    rebuilt = GraphStore(tmp_path / "rebuilt.kuzu")
    rebuilt.rebuild(events)
    assert rebuilt.snapshot_state() == incremental.snapshot_state()


def test_two_fresh_rebuilds_are_deterministic(tmp_path) -> None:
    events = _sample_events()
    one = GraphStore(tmp_path / "one.kuzu").rebuild(events)
    two = GraphStore(tmp_path / "two.kuzu").rebuild(events)
    assert one == two


def test_rebuild_wipes_previous_state(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    store.rebuild(_sample_events())
    subset = _sample_events()[:2]
    snapshot = store.rebuild(subset)
    assert set(snapshot["Claim"]) == {"c1", "c2"}
    assert snapshot["VersionNode"] == {}
    assert snapshot["FORKED_FROM"] == []


def test_posterior_update_via_second_upsert(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    store.apply_event(_records(("claim.upsert", {"claim": dict(CLAIM_A)}))[0])
    updated = {**CLAIM_A, "posterior": 0.85, "stale": True}
    store.apply_event(_records(("claim.upsert", {"claim": updated}))[0])
    snapshot = store.snapshot_state()
    assert snapshot["Claim"]["c1"]["posterior"] == 0.85
    assert snapshot["Claim"]["c1"]["stale"] is True
    assert len(snapshot["Claim"]) == 1


def test_fork_lineage_bidirectional(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    store.rebuild(_sample_events())
    assert store.fork_parent("t2:0") == "t1:0"
    assert store.fork_parent("t1:0") is None
    assert store.fork_children("t1:0") == ["t2:0"]
    assert store.fork_children("t2:0") == []


def test_apply_revalidates_payload_at_projection_boundary(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    bad = {
        "seq": 1,
        "created_at": "x",
        "event_type": "claim.upsert",
        "payload": {"claim": {**CLAIM_A, "posterior": 7.0}},
    }
    with pytest.raises(Exception):
        store.apply_event(bad)
    assert store.snapshot_state()["Claim"] == {}


def test_counts_cover_all_tables(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    store.rebuild(_sample_events())
    counts = store.counts()
    assert counts == {
        "Claim": 2,
        "Stage": 1,
        "Evidence": 1,
        "Artifact": 1,
        "VersionNode": 2,
        "KILL_EDGE": 1,
        "STAGE_DEPENDS_ON": 0,
        "CONTAINS": 1,
        "EVIDENCE_FOR": 1,
        "ARTIFACT_FOR": 1,
        "FORKED_FROM": 1,
    }


def test_validate_roundtrip_of_vocabulary_stays_in_sync() -> None:
    # every vocabulary type must be exercisable through the projection boundary
    for event_type, payload in {
        "claim.upsert": {"claim": dict(CLAIM_A)},
        "claim.kill_edge": {"claim_id": "c1", "kill_target_id": "c2"},
    }.items():
        assert validate_graph_event(event_type, payload)["claim" if event_type == "claim.upsert" else "claim_id"]
