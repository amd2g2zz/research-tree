"""Coordinator dual-write + self-heal over the graph event stream (issue #546)."""

from __future__ import annotations

import sqlite3

import pytest

from research_tree.coordinator import (
    CoordinatorConflictError,
    GraphProjectionError,
    ResearchRunCoordinator,
)
from research_tree.graph_store import GraphStore
from research_tree.run_ledger import RunLedger

CLAIM = {
    "id": "c1",
    "text": "rt works offline",
    "source": "user",
    "weight": "make_or_break",
    "posterior": 0.5,
    "verify_tier": "multi-source",
}
CLAIM_RECORD = ("claim.upsert", {"claim": dict(CLAIM)})
FORK_RECORD = ("fork.edge", {"child_version_id": "t2:0", "parent_version_id": "t1:0"})


@pytest.fixture()
def ledger(tmp_path) -> RunLedger:
    run_ledger = RunLedger(tmp_path)
    run_ledger.initialize()
    return run_ledger


def _coordinator(ledger: RunLedger, store: GraphStore | None) -> ResearchRunCoordinator:
    return ResearchRunCoordinator(ledger, graph_store=store)


def test_dual_write_lands_in_log_and_projection(tmp_path, ledger) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    coordinator = _coordinator(ledger, store)
    record = coordinator.append_graph_event(*CLAIM_RECORD)
    assert record["seq"] == 1
    assert coordinator.graph_events()[0]["event_type"] == "claim.upsert"
    assert store.snapshot_state()["Claim"]["c1"]["text"] == "rt works offline"


def test_without_graph_store_only_the_log_is_written(ledger) -> None:
    coordinator = _coordinator(ledger, None)
    record = coordinator.append_graph_event(*CLAIM_RECORD)
    assert record["seq"] == 1
    assert len(coordinator.graph_events()) == 1


def test_graph_store_kwarg_is_type_enforced(ledger) -> None:
    with pytest.raises(CoordinatorConflictError, match="GraphStore"):
        _coordinator(ledger, object())  # type: ignore[arg-type]


def test_projection_failure_is_fail_closed(tmp_path, ledger, monkeypatch) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    coordinator = _coordinator(ledger, store)

    def broken_apply(record):
        raise RuntimeError("kuzu engine failure")

    monkeypatch.setattr(store, "apply_event", broken_apply)
    with pytest.raises(GraphProjectionError, match="resync"):
        coordinator.append_graph_event(*CLAIM_RECORD)
    # the log (authority) still holds the event
    assert len(coordinator.ledger.graph_events()) == 1


def test_resync_restores_state_after_drift(tmp_path, ledger) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    coordinator = _coordinator(ledger, store)
    coordinator.append_graph_event(*CLAIM_RECORD)
    # pollute the projection with state the log does not contain
    store.apply_event(
        {
            "seq": 99,
            "run_id": None,
            "created_at": "x",
            "event_type": "claim.upsert",
            "payload": {"claim": {**CLAIM, "id": "ghost"}},
        }
    )
    assert "ghost" in store.snapshot_state()["Claim"]
    counts = coordinator.resync_graph()
    assert "ghost" not in counts["Claim"]

    fresh = GraphStore(tmp_path / "fresh.kuzu").rebuild(ledger.graph_events())
    assert store.snapshot_state() == fresh


def test_replay_from_log_alone_rebuilds_identical_graph(tmp_path, ledger) -> None:
    store = GraphStore(tmp_path / "graph.kuzu")
    coordinator = _coordinator(ledger, store)
    coordinator.append_graph_event(*CLAIM_RECORD)
    coordinator.append_graph_event(*FORK_RECORD)
    fresh = GraphStore(tmp_path / "fresh.kuzu")
    fresh.rebuild(coordinator.ledger.graph_events())
    assert fresh.snapshot_state() == store.snapshot_state()


def test_verify_graph_chain_detects_tampered_payload(tmp_path, ledger) -> None:
    coordinator = _coordinator(ledger, None)
    coordinator.append_graph_event(*CLAIM_RECORD)
    with sqlite3.connect(ledger.database) as connection:
        connection.execute(
            "UPDATE graph_events SET payload_json = ? WHERE seq = 1",
            (b'{"claim": {"id": "tampered"}}',),
        )
    with pytest.raises(Exception, match="hash mismatch"):
        ledger.verify_graph_chain()


def test_verify_graph_chain_detects_deleted_row(tmp_path, ledger) -> None:
    coordinator = _coordinator(ledger, None)
    coordinator.append_graph_event(*CLAIM_RECORD)
    coordinator.append_graph_event(*FORK_RECORD)
    with sqlite3.connect(ledger.database) as connection:
        connection.execute("DELETE FROM graph_events WHERE seq = 1")
    with pytest.raises(Exception, match="gap"):
        ledger.verify_graph_chain()


def test_chain_is_intact_after_normal_appends(tmp_path, ledger) -> None:
    coordinator = _coordinator(ledger, None)
    coordinator.append_graph_event(*CLAIM_RECORD)
    coordinator.append_graph_event(*FORK_RECORD)
    coordinator.ledger.verify_graph_chain()  # must not raise
    records = coordinator.graph_events()
    assert records[0]["prev_hash"] == "0" * 64
    assert records[1]["prev_hash"] == records[0]["content_hash"]
