from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3

import pytest

from research_tree import (
    AttemptLease,
    CASError,
    ContentAddressedStore,
    LeaseError,
    LegacyRunStoreImporter,
    MigrationError,
    MigrationManager,
    ReplayError,
    RunLedgerProtocol,
    RunStore,
    SQLiteLedgerError,
    SQLiteRunLedger,
    ordered_events,
    replay_events,
    semantic_state_digest,
)


def _digest(value: bytes = b"dispatch") -> str:
    return hashlib.sha256(value).hexdigest()


def test_sqlite_ledger_implements_storage_protocol_and_durable_pragmas(tmp_path):
    ledger = SQLiteRunLedger(tmp_path)
    assert isinstance(ledger, RunLedgerProtocol)
    ledger.create_run("run-protocol")

    with ledger._connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2

    assert {
        "runs",
        "events",
        "artifacts",
        "artifact_parents",
        "action_attempts",
        "evidence_artifacts",
        "oracle_runs",
        "host_events",
        "content_objects",
        "legacy_imports",
    } <= tables
    assert ledger.events("run-protocol")[0]["event_type"] == "run_initialized"


def test_artifact_lineage_reconstructs_and_rejects_stale_or_dangling_writes(tmp_path):
    ledger = SQLiteRunLedger(tmp_path)
    ledger.create_run("run-1")
    first = ledger.append_artifact(
        run_id="run-1",
        artifact_id="brief",
        kind="working-brief",
        payload={"goal": "research"},
        actor_kind="coordinator",
        actor_id="core",
        status="candidate",
        expected_revision=0,
        expected_run_revision=0,
        created_at="2026-08-05T00:00:00+00:00",
    )
    second = ledger.append_artifact(
        run_id="run-1",
        artifact_id="strategy",
        kind="strategy",
        payload={"method": "recursive"},
        actor_kind="coordinator",
        actor_id="core",
        status="supported",
        parent_refs=[
            {"run_id": "run-1", "artifact_id": "brief", "revision": 1}
        ],
        expected_revision=0,
        expected_run_revision=1,
        created_at="2026-08-05T00:00:01+00:00",
    )
    assert first["content_hash"] != second["content_hash"]
    assert ledger.resolve("run-1", "strategy", 1)["parent_refs"][0]["artifact_id"] == "brief"
    assert ledger.reconstruct("run-1")["semantic_digest"] == ledger.reconstruct("run-1")["semantic_digest"]

    with pytest.raises(SQLiteLedgerError) as stale:
        ledger.append_artifact(
            run_id="run-1",
            artifact_id="brief",
            kind="working-brief",
            payload={},
            actor_kind="coordinator",
            actor_id="core",
            status="candidate",
            expected_revision=0,
        )
    assert stale.value.code == "stale_revision"

    with pytest.raises(SQLiteLedgerError) as dangling:
        ledger.append_artifact(
            run_id="run-1",
            artifact_id="orphan",
            kind="finding-pack",
            payload={},
            actor_kind="coordinator",
            actor_id="core",
            status="candidate",
            parent_refs=[
                {"run_id": "run-1", "artifact_id": "missing", "revision": 1}
            ],
        )
    assert dangling.value.code == "dangling_parent"


def test_ledger_detects_tampering_and_rolls_back_registered_boundaries(tmp_path):
    ledger = SQLiteRunLedger(tmp_path)
    ledger.create_run("run-tamper")
    ledger.append_artifact(
        run_id="run-tamper",
        artifact_id="brief",
        kind="working-brief",
        payload={"goal": "a"},
        actor_kind="coordinator",
        actor_id="core",
        status="candidate",
    )
    with sqlite3.connect(ledger.database) as connection:
        connection.execute(
            "UPDATE artifacts SET payload_json=? "
            "WHERE run_id='run-tamper' AND artifact_id='brief'",
            ('{"goal":"tampered"}',),
        )
    with pytest.raises(SQLiteLedgerError) as error:
        ledger.resolve("run-tamper", "brief", 1)
    assert error.value.code == "digest_mismatch"

    for boundary in (
        "after_artifact",
        "after_parents",
        "after_run_update",
        "after_event",
    ):
        workspace = tmp_path / boundary
        base = SQLiteRunLedger(workspace)
        base.create_run("run-crash")

        def inject(current: str, expected: str = boundary) -> None:
            if current == expected:
                raise RuntimeError(current)

        faulted = SQLiteRunLedger(workspace, fault_injector=inject)
        with pytest.raises(RuntimeError, match=boundary):
            faulted.append_artifact(
                run_id="run-crash",
                artifact_id="finding",
                kind="finding-pack",
                payload={"boundary": boundary},
                actor_kind="coordinator",
                actor_id="core",
                status="candidate",
            )
        assert SQLiteRunLedger(workspace).run("run-crash")["revision"] == 0
        with pytest.raises(SQLiteLedgerError):
            SQLiteRunLedger(workspace).resolve("run-crash", "finding", 1)


def test_concurrent_writers_commit_one_run_revision(tmp_path):
    SQLiteRunLedger(tmp_path).create_run("run-concurrent")

    def append(actor_id: str):
        ledger = SQLiteRunLedger(tmp_path)
        try:
            artifact = ledger.append_artifact(
                run_id="run-concurrent",
                artifact_id="brief",
                kind="working-brief",
                payload={"actor": actor_id},
                actor_kind="coordinator",
                actor_id=actor_id,
                status="candidate",
                expected_revision=0,
                expected_run_revision=0,
            )
            return ("committed", artifact["content_hash"])
        except SQLiteLedgerError as error:
            return (error.code, None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(append, ("writer-a", "writer-b")))
    assert sorted(item[0] for item in outcomes) == ["committed", "stale_run_revision"]
    assert SQLiteRunLedger(tmp_path).run("run-concurrent")["revision"] == 1


def test_cas_is_workspace_bounded_and_content_survives_restart(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"secret")
    cas = ContentAddressedStore(workspace)
    with pytest.raises(CASError, match="workspace"):
        cas.put_file(outside)

    ledger = SQLiteRunLedger(workspace)
    ledger.create_run("run-content")
    committed = ledger.put_content(
        run_id="run-content",
        data=b"binary evidence",
        media_type="application/octet-stream",
        metadata={"source": "fixture"},
        expected_revision=0,
    )
    restarted = SQLiteRunLedger(workspace)
    assert restarted.cas.read(committed["digest"]) == b"binary evidence"
    assert restarted.reconstruct("run-content")["content_objects"][0]["digest"] == committed["digest"]


def test_attempt_leases_and_replay_are_deterministic():
    lease = AttemptLease.create(
        attempt_id="attempt-1",
        work_item_id="work-1",
        run_id="run-1",
        owner="worker-a",
        dispatch_digest=_digest(),
        started_at="2026-08-05T00:00:00+00:00",
        lease_expires_at="2026-08-05T00:01:00+00:00",
    )
    renewed = lease.heartbeat(
        now="2026-08-05T00:00:20+00:00", lease_seconds=60
    )
    assert renewed.heartbeat_sequence == 1
    assert renewed.expire(now="2026-08-05T00:02:00+00:00").status == "unknown"
    with pytest.raises(LeaseError):
        AttemptLease.create(
            attempt_id="attempt-2",
            work_item_id="work-1",
            run_id="run-1",
            owner="worker-a",
            dispatch_digest=_digest(),
            started_at="not-a-date",
            lease_expires_at="2026-08-05T00:01:00+00:00",
        )

    events = [
        {"event_id": "b", "sequence": 2, "payload": {"value": 2}},
        {"event_id": "a", "sequence": 1, "payload": {"value": 1}},
    ]
    assert [event["event_id"] for event in ordered_events(events)] == ["a", "b"]
    assert replay_events({}, events)["value"] == 2
    assert semantic_state_digest({"b": 1}) == semantic_state_digest({"b": 1})
    with pytest.raises(ReplayError):
        ordered_events([{"event_id": "a", "sequence": 2}])


def test_migration_is_confirmed_idempotent_and_legacy_closure_is_untrusted(tmp_path):
    source = tmp_path / "legacy.json"
    source.write_text('{"legacy":true}\n', encoding="utf-8")
    manager = MigrationManager(tmp_path)
    assert manager.dry_run([source])["mode"] == "dry-run"
    with pytest.raises(MigrationError):
        manager.apply([source])
    manager.apply([source], confirmation="CONFIRM-MIGRATION")
    assert manager.verify()["status"] == "verified"
    assert manager.dry_run([source])["entries"][0]["disposition"] == "already_imported"
    assert manager.rollback()["status"] == "rolled_back"

    alpha1 = tmp_path / "alpha1"
    store = RunStore(alpha1)
    store.create_round("run-legacy")
    store.append_artifact(
        "run-legacy", "brief", "working-brief", {"goal": "research"}
    )
    destination = tmp_path / "alpha2"
    importer = LegacyRunStoreImporter(alpha1, destination)
    first = importer.import_round("run-legacy")
    second = importer.import_round("run-legacy")
    assert first["closure_disposition"] == "legacy_unverified"
    assert second["status"] == "already_imported"
    assert (
        SQLiteRunLedger(destination)
        .resolve("run-legacy", "brief", 1)["status"]
        == "legacy_unverified"
    )
