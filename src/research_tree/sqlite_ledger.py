"""SQLite artifact ledger sharing the coordinator's canonical workspace DB."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from .contracts import canonical_json_bytes
from .coordinator import ResearchRunCoordinator


class SQLiteLedgerError(ValueError):
    def __init__(self, message: str, *, code: str = "ledger_error") -> None:
        super().__init__(message)
        self.code = code


class SQLiteRunLedger:
    """Append-only artifact revisions with exact parent lineage."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        coordinator = ResearchRunCoordinator(workspace)
        self.coordinator = coordinator
        self._fault_injector = fault_injector
        self.database = coordinator.database
        with self._connect() as connection:
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL,migration_digest TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS artifacts(
              run_id TEXT NOT NULL REFERENCES runs(run_id),artifact_id TEXT NOT NULL,revision INTEGER NOT NULL,
              kind TEXT NOT NULL,schema_version INTEGER NOT NULL,created_at TEXT NOT NULL,actor_kind TEXT NOT NULL,
              actor_id TEXT NOT NULL,status TEXT NOT NULL,payload_json TEXT NOT NULL,content_hash TEXT NOT NULL,
              PRIMARY KEY(run_id,artifact_id,revision),UNIQUE(run_id,content_hash));
            CREATE TABLE IF NOT EXISTS artifact_parents(
              run_id TEXT NOT NULL,artifact_id TEXT NOT NULL,revision INTEGER NOT NULL,parent_run_id TEXT NOT NULL,
              parent_artifact_id TEXT NOT NULL,parent_revision INTEGER NOT NULL,
              PRIMARY KEY(run_id,artifact_id,revision,parent_run_id,parent_artifact_id,parent_revision),
              FOREIGN KEY(run_id,artifact_id,revision) REFERENCES artifacts(run_id,artifact_id,revision),
              FOREIGN KEY(parent_run_id,parent_artifact_id,parent_revision) REFERENCES artifacts(run_id,artifact_id,revision));
            """)
            schema = canonical_json_bytes({"version": 1, "tables": ["runs", "events", "artifacts", "artifact_parents"]})
            connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES(1,?,?)", (datetime.now(timezone.utc).isoformat(), hashlib.sha256(schema).hexdigest()))
            schema_v2 = canonical_json_bytes({"version": 2, "tables": ["runs", "events", "artifacts", "artifact_parents", "action_attempts", "run_obligations", "run_revisions", "host_events"]})
            connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES(2,?,?)", (datetime.now(timezone.utc).isoformat(), hashlib.sha256(schema_v2).hexdigest()))
            schema_v3 = canonical_json_bytes({"version": 3, "tables": ["oracle_runs", "slot_closure_assessments"]})
            connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES(3,?,?)", (datetime.now(timezone.utc).isoformat(), hashlib.sha256(schema_v3).hexdigest()))
            schema_v4 = canonical_json_bytes({"version": 4, "tables": ["oracle_specs", "oracle_attempts", "oracle_runs"]})
            connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES(4,?,?)", (datetime.now(timezone.utc).isoformat(), hashlib.sha256(schema_v4).hexdigest()))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _fault(self, boundary: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(boundary)

    def append_artifact(self, *, run_id: str, artifact_id: str, kind: str, payload: Mapping[str, Any], actor_kind: str, actor_id: str, status: str, parent_refs: Sequence[Mapping[str, Any]] = (), expected_revision: int | None = None, created_at: str | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run_row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run_row is None:
                raise SQLiteLedgerError("run does not exist", code="run_not_found")
            current = int(connection.execute("SELECT COALESCE(MAX(revision),0) FROM artifacts WHERE run_id=? AND artifact_id=?", (run_id, artifact_id)).fetchone()[0])
            if expected_revision is not None and current != expected_revision:
                raise SQLiteLedgerError("artifact expected revision is stale", code="stale_revision")
            revision = current + 1
            parents = [dict(item) for item in parent_refs]
            for parent in parents:
                if connection.execute("SELECT 1 FROM artifacts WHERE run_id=? AND artifact_id=? AND revision=?", (parent.get("run_id"), parent.get("artifact_id"), parent.get("revision"))).fetchone() is None:
                    raise SQLiteLedgerError("parent artifact does not resolve", code="dangling_parent")
            stamp = created_at or datetime.now(timezone.utc).isoformat()
            body = {"schema_version": 1, "kind": kind, "id": artifact_id, "run_id": run_id, "revision": revision, "created_at": stamp, "actor": {"kind": actor_kind, "id": actor_id}, "status": status, "payload": dict(payload), "parent_refs": parents}
            content_hash = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
            try:
                connection.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)", (run_id, artifact_id, revision, kind, 1, stamp, actor_kind, actor_id, status, canonical_json_bytes(payload).decode("utf-8"), content_hash))
            except sqlite3.IntegrityError as exc:
                raise SQLiteLedgerError("artifact conflicts with immutable ledger", code="artifact_conflict") from exc
            self._fault("after_artifact")
            for parent in parents:
                connection.execute("INSERT INTO artifact_parents VALUES(?,?,?,?,?,?)", (run_id, artifact_id, revision, parent["run_id"], parent["artifact_id"], parent["revision"]))
            self._fault("after_parents")
            run_revision = int(run_row["revision"]) + 1
            state = {
                "run_id": run_id,
                "revision": run_revision,
                "lifecycle_state": run_row["lifecycle_state"],
                "task_identity": json.loads(run_row["task_identity_json"]),
                "feedback_id": None,
            }
            state_digest = hashlib.sha256(canonical_json_bytes(state)).hexdigest()
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (run_revision, state_digest, datetime.now(timezone.utc).isoformat(), run_id),
            )
            self._fault("after_run_update")
            event_id = f"artifact-appended-{artifact_id}-{revision}"
            event_payload = {
                "artifact_id": artifact_id,
                "artifact_revision": revision,
                "kind": kind,
                "content_hash": content_hash,
            }
            raw_event = canonical_json_bytes(event_payload)
            sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
            )
            connection.execute(
                """INSERT INTO events(
                     run_id,event_id,sequence,event_type,expected_revision,payload_json,
                     payload_digest,accepted,error_code,causation_id,correlation_id,emitted_at
                   ) VALUES(?,?,?,?,?,?,?,1,NULL,NULL,NULL,?)""",
                (
                    run_id,
                    event_id,
                    sequence,
                    "artifact_appended",
                    int(run_row["revision"]),
                    raw_event.decode("utf-8"),
                    hashlib.sha256(raw_event).hexdigest(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._fault("after_event")
            self.coordinator._snapshot_current_revision(
                connection, run_id, source_event_id=event_id
            )
        return {**body, "content_hash": content_hash}

    def resolve(self, run_id: str, artifact_id: str, revision: int) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE run_id=? AND artifact_id=? AND revision=?", (run_id, artifact_id, revision)).fetchone()
            if row is None:
                raise SQLiteLedgerError("artifact revision does not exist", code="artifact_not_found")
            parents = connection.execute("SELECT parent_run_id,parent_artifact_id,parent_revision FROM artifact_parents WHERE run_id=? AND artifact_id=? AND revision=? ORDER BY parent_run_id,parent_artifact_id,parent_revision", (run_id, artifact_id, revision)).fetchall()
        body = {"schema_version": row["schema_version"], "kind": row["kind"], "id": row["artifact_id"], "run_id": row["run_id"], "revision": row["revision"], "created_at": row["created_at"], "actor": {"kind": row["actor_kind"], "id": row["actor_id"]}, "status": row["status"], "payload": json.loads(row["payload_json"]), "parent_refs": [{"run_id": item["parent_run_id"], "artifact_id": item["parent_artifact_id"], "revision": item["parent_revision"]} for item in parents]}
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != row["content_hash"]:
            raise SQLiteLedgerError("artifact content hash mismatch", code="digest_mismatch")
        return {**body, "content_hash": row["content_hash"]}

    def reconstruct(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone() is None:
                raise SQLiteLedgerError("run does not exist", code="run_not_found")
            refs = connection.execute("SELECT artifact_id,revision FROM artifacts WHERE run_id=? ORDER BY artifact_id,revision", (run_id,)).fetchall()
        artifacts = [self.resolve(run_id, row["artifact_id"], row["revision"]) for row in refs]
        digest = hashlib.sha256(canonical_json_bytes(artifacts)).hexdigest()
        return {"run_id": run_id, "artifacts": artifacts, "semantic_digest": digest}
