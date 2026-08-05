import pytest

from research_tree import CASError, ContentAddressedStore, ResearchRunCoordinator, SQLiteLedgerError, SQLiteRunLedger


def test_sqlite_ledger_appends_exact_lineage_and_replays_digest(tmp_path):
    ResearchRunCoordinator(tmp_path).create("run-1")
    ledger = SQLiteRunLedger(tmp_path)
    first = ledger.append_artifact(run_id="run-1", artifact_id="brief", kind="working-brief", payload={"goal": "research"}, actor_kind="coordinator", actor_id="core", status="candidate", expected_revision=0, created_at="2026-08-05T00:00:00+00:00")
    second = ledger.append_artifact(run_id="run-1", artifact_id="strategy", kind="strategy", payload={"method": "recursive"}, actor_kind="coordinator", actor_id="core", status="supported", parent_refs=[{"run_id": "run-1", "artifact_id": "brief", "revision": 1}], expected_revision=0, created_at="2026-08-05T00:00:01+00:00")
    assert ledger.resolve("run-1", "strategy", 1)["parent_refs"][0]["artifact_id"] == "brief"
    assert ledger.reconstruct("run-1")["semantic_digest"] == ledger.reconstruct("run-1")["semantic_digest"]
    assert first["content_hash"] != second["content_hash"]


def test_sqlite_ledger_rejects_stale_write_and_dangling_parent(tmp_path):
    ResearchRunCoordinator(tmp_path).create("run-1")
    ledger = SQLiteRunLedger(tmp_path)
    ledger.append_artifact(run_id="run-1", artifact_id="brief", kind="working-brief", payload={}, actor_kind="coordinator", actor_id="core", status="candidate", expected_revision=0)
    with pytest.raises(SQLiteLedgerError) as stale:
        ledger.append_artifact(run_id="run-1", artifact_id="brief", kind="working-brief", payload={}, actor_kind="coordinator", actor_id="core", status="candidate", expected_revision=0)
    assert stale.value.code == "stale_revision"
    with pytest.raises(SQLiteLedgerError) as dangling:
        ledger.append_artifact(run_id="run-1", artifact_id="strategy", kind="strategy", payload={}, actor_kind="coordinator", actor_id="core", status="candidate", parent_refs=[{"run_id": "run-1", "artifact_id": "missing", "revision": 1}])
    assert dangling.value.code == "dangling_parent"


def test_sqlite_ledger_detects_tampering(tmp_path):
    import sqlite3

    ResearchRunCoordinator(tmp_path).create("run-1")
    ledger = SQLiteRunLedger(tmp_path)
    ledger.append_artifact(run_id="run-1", artifact_id="brief", kind="working-brief", payload={"goal": "a"}, actor_kind="coordinator", actor_id="core", status="candidate")
    with sqlite3.connect(ledger.database) as connection:
        connection.execute("UPDATE artifacts SET payload_json=? WHERE run_id='run-1' AND artifact_id='brief'", ('{"goal":"tampered"}',))
    with pytest.raises(SQLiteLedgerError) as error:
        ledger.resolve("run-1", "brief", 1)
    assert error.value.code == "digest_mismatch"


def test_cas_rejects_file_outside_workspace_and_records_media_metadata(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"secret")
    cas = ContentAddressedStore(workspace)
    with pytest.raises(CASError, match="workspace"):
        cas.put_file(outside)

    stored = cas.put_bytes(b"image", media_type="image/png")
    assert stored["media_type"] == "image/png"
    assert stored["size"] == 5
    assert cas.verify(stored["digest"])["media_type"] == "image/png"


def test_cas_staged_blob_is_inert_until_promoted_and_can_be_quarantined(tmp_path):
    cas = ContentAddressedStore(tmp_path)
    staged = cas.stage_bytes(b"pending", media_type="application/octet-stream")
    with pytest.raises(CASError, match="unavailable"):
        cas.read(staged["digest"])
    promoted = cas.promote(staged["digest"])
    assert promoted["status"] == "committed"
    assert cas.read(staged["digest"]) == b"pending"
    quarantined = cas.quarantine(staged["digest"], reason="database commit failed")
    assert quarantined["status"] == "quarantined"
    with pytest.raises(CASError, match="unavailable"):
        cas.read(staged["digest"])


def test_artifact_append_is_recorded_in_canonical_event_and_revision_ledger(tmp_path):
    coordinator = ResearchRunCoordinator(tmp_path)
    coordinator.create("run-events")
    ledger = SQLiteRunLedger(tmp_path)
    ledger.append_artifact(
        run_id="run-events",
        artifact_id="brief",
        kind="working-brief",
        payload={"goal": "research"},
        actor_kind="coordinator",
        actor_id="core",
        status="candidate",
        expected_revision=0,
        created_at="2026-08-05T00:00:00+00:00",
    )
    event_types = [event["event_type"] for event in coordinator.events("run-events")]
    assert "artifact_appended" in event_types
    assert coordinator.status("run-events")["revision"] == 1
    assert 1 in coordinator.revisions("run-events")


def test_artifact_append_rolls_back_at_each_registered_write_boundary(tmp_path):
    ResearchRunCoordinator(tmp_path).create("run-crash")
    for boundary in ("after_artifact", "after_parents", "after_run_update", "after_event"):
        def inject(current: str, expected: str = boundary) -> None:
            if current == expected:
                raise RuntimeError(current)

        ledger = SQLiteRunLedger(tmp_path, fault_injector=inject)
        with pytest.raises(RuntimeError, match=boundary):
            ledger.append_artifact(
                run_id="run-crash",
                artifact_id=f"artifact-{boundary}",
                kind="finding-pack",
                payload={"boundary": boundary},
                actor_kind="coordinator",
                actor_id="core",
                status="candidate",
            )
        with pytest.raises(SQLiteLedgerError, match="does not exist"):
            ledger.resolve("run-crash", f"artifact-{boundary}", 1)
    assert ResearchRunCoordinator(tmp_path).status("run-crash")["revision"] == 0
