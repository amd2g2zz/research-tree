from datetime import datetime, timezone
import hashlib

import pytest

from research_tree import AttemptLease, CoordinatorError, LegacyRunStoreImporter, LeaseError, MigrationError, MigrationManager, ResearchRunCoordinator, RunStore, SQLiteRunLedger
from research_tree.replay import ReplayError, ordered_events, replay_events, semantic_state_digest


def _digest(value=b"dispatch"):
    return hashlib.sha256(value).hexdigest()


def test_attempt_lease_heartbeat_and_expiry_are_deterministic():
    lease = AttemptLease.create(
        attempt_id="attempt-1", work_item_id="work-1", run_id="run-1", owner="worker-a",
        dispatch_digest=_digest(), started_at="2026-08-05T00:00:00+00:00",
        lease_expires_at="2026-08-05T00:01:00+00:00",
    )
    renewed = lease.heartbeat(now="2026-08-05T00:00:20+00:00", lease_seconds=60)
    assert renewed.heartbeat_sequence == 1
    assert renewed.status == "running"
    assert renewed.expire(now="2026-08-05T00:02:00+00:00").status == "unknown"
    assert renewed.expire(now="2026-08-05T00:00:21+00:00") == renewed


def test_attempt_lease_rejects_retry_of_completed_attempt():
    lease = AttemptLease.create(
        attempt_id="attempt-1", work_item_id="work-1", run_id="run-1", owner="worker-a",
        dispatch_digest=_digest(), started_at="2026-08-05T00:00:00+00:00",
        lease_expires_at="2026-08-05T00:01:00+00:00", status="completed",
    )
    with pytest.raises(LeaseError):
        lease.retry(dispatch_digest=_digest(b"other"))


def test_replay_orders_by_sequence_and_rejects_gaps():
    events = [{"event_id": "b", "sequence": 2, "payload": {"value": 2}}, {"event_id": "a", "sequence": 1, "payload": {"value": 1}}]
    assert [e["event_id"] for e in ordered_events(events)] == ["a", "b"]
    assert replay_events({}, events)["value"] == 2
    assert semantic_state_digest({"b": 1}) == semantic_state_digest({"b": 1})
    with pytest.raises(ReplayError):
        ordered_events([{"event_id": "a", "sequence": 2}])


def test_migration_is_confirmed_idempotent_verified_and_reversible(tmp_path):
    source = tmp_path / "legacy.json"
    source.write_text('{"legacy":true}\n', encoding="utf-8")
    manager = MigrationManager(tmp_path)
    plan = manager.dry_run([source])
    assert plan["mode"] == "dry-run"
    with pytest.raises(MigrationError):
        manager.apply([source])
    applied = manager.apply([source], confirmation="CONFIRM-MIGRATION")
    assert applied["mode"] == "applied"
    second = manager.dry_run([source])
    assert second["entries"][0]["disposition"] == "already_imported"
    assert manager.verify()["status"] == "verified"
    assert manager.rollback()["status"] == "rolled_back"


def test_coordinator_persists_and_expires_attempt_leases(tmp_path):
    coordinator = ResearchRunCoordinator(tmp_path)
    coordinator.create("run-1")
    lease = AttemptLease.create(
        attempt_id="attempt-1", work_item_id="work-1", run_id="run-1", owner="worker-a",
        dispatch_digest=_digest(), started_at="2026-08-05T00:00:00+00:00",
        lease_expires_at="2026-08-05T00:01:00+00:00",
    )
    coordinator.issue_lease(lease, expected_revision=0)
    heartbeat = coordinator.heartbeat_lease("run-1", "attempt-1", now="2026-08-05T00:00:10+00:00")
    assert heartbeat["heartbeat_sequence"] == 1
    expired = coordinator.expire_leases("run-1", now="2026-08-05T00:02:00+00:00")
    assert expired[0]["status"] == "unknown"
    with pytest.raises(CoordinatorError):
        coordinator.issue_lease(lease, expected_revision=1)


def test_coordinator_reconcile_host_reads_canonical_ledger(tmp_path):
    coordinator = ResearchRunCoordinator(tmp_path)
    coordinator.create("run-1")
    assert coordinator.reconcile_host("run-1")["status"] == "no_divergence_detected"


def test_legacy_run_store_import_is_idempotent_and_unverified(tmp_path):
    source = tmp_path / "legacy"
    store = RunStore(source)
    store.create_round("run-1")
    store.append_artifact("run-1", "brief", "working-brief", {"goal": "research"})
    destination = tmp_path / "alpha2"
    importer = LegacyRunStoreImporter(source, destination)
    first = importer.import_round("run-1")
    second = importer.import_round("run-1")
    assert first["status"] == "imported"
    assert second["status"] == "already_imported"
    assert SQLiteRunLedger(destination).resolve("run-1", "brief", 1)["status"] == "legacy_unverified"
