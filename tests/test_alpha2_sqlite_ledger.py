import pytest

from research_tree import ResearchRunCoordinator, SQLiteLedgerError, SQLiteRunLedger


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
