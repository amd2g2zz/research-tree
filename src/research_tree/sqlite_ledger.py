"""Durable SQLite implementation of the Alpha2 run-ledger boundary."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from .cas import ContentAddressedStore


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SQLiteLedgerError("value is not canonical JSON", code="invalid_json") from exc


class SQLiteLedgerError(ValueError):
    def __init__(self, message: str, *, code: str = "ledger_error") -> None:
        super().__init__(message)
        self.code = code


class SQLiteRunLedger:
    """Single durable owner for run, event, artifact, attempt, and content state."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.state_directory = self.workspace / ".research-tree"
        self.state_directory.mkdir(parents=True, exist_ok=True)
        self.database = self.state_directory / "run-ledger.sqlite3"
        self.cas = ContentAddressedStore(self.workspace)
        self._fault_injector = fault_injector
        with self._connect() as connection:
            self._schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @staticmethod
    def _schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations(
              version INTEGER PRIMARY KEY,
              applied_at TEXT NOT NULL,
              migration_digest TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS runs(
              run_id TEXT PRIMARY KEY,
              revision INTEGER NOT NULL,
              task_identity_json TEXT NOT NULL,
              authority_json TEXT NOT NULL,
              parent_run_id TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events(
              run_id TEXT NOT NULL REFERENCES runs(run_id),
              event_id TEXT NOT NULL,
              sequence INTEGER NOT NULL,
              event_type TEXT NOT NULL,
              expected_revision INTEGER NOT NULL,
              payload_json TEXT NOT NULL,
              payload_digest TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY(run_id,event_id),
              UNIQUE(run_id,sequence)
            );
            CREATE TABLE IF NOT EXISTS artifacts(
              run_id TEXT NOT NULL REFERENCES runs(run_id),
              artifact_id TEXT NOT NULL,
              revision INTEGER NOT NULL,
              kind TEXT NOT NULL,
              schema_version INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              actor_kind TEXT NOT NULL,
              actor_id TEXT NOT NULL,
              status TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              content_hash TEXT NOT NULL,
              PRIMARY KEY(run_id,artifact_id,revision),
              UNIQUE(run_id,content_hash)
            );
            CREATE TABLE IF NOT EXISTS artifact_parents(
              run_id TEXT NOT NULL,
              artifact_id TEXT NOT NULL,
              revision INTEGER NOT NULL,
              parent_run_id TEXT NOT NULL,
              parent_artifact_id TEXT NOT NULL,
              parent_revision INTEGER NOT NULL,
              PRIMARY KEY(
                run_id,artifact_id,revision,
                parent_run_id,parent_artifact_id,parent_revision
              ),
              FOREIGN KEY(run_id,artifact_id,revision)
                REFERENCES artifacts(run_id,artifact_id,revision),
              FOREIGN KEY(parent_run_id,parent_artifact_id,parent_revision)
                REFERENCES artifacts(run_id,artifact_id,revision)
            );
            CREATE TABLE IF NOT EXISTS action_attempts(
              run_id TEXT NOT NULL REFERENCES runs(run_id),
              attempt_id TEXT NOT NULL,
              lease_json TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(run_id,attempt_id)
            );
            CREATE TABLE IF NOT EXISTS evidence_artifacts(
              run_id TEXT NOT NULL REFERENCES runs(run_id),
              evidence_id TEXT NOT NULL,
              revision INTEGER NOT NULL,
              artifact_id TEXT NOT NULL,
              artifact_revision INTEGER NOT NULL,
              record_json TEXT NOT NULL,
              PRIMARY KEY(run_id,evidence_id,revision),
              FOREIGN KEY(run_id,artifact_id,artifact_revision)
                REFERENCES artifacts(run_id,artifact_id,revision)
            );
            CREATE TABLE IF NOT EXISTS oracle_runs(
              run_id TEXT NOT NULL REFERENCES runs(run_id),
              oracle_run_id TEXT NOT NULL,
              attempt_id TEXT NOT NULL,
              record_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY(run_id,oracle_run_id)
            );
            CREATE TABLE IF NOT EXISTS host_events(
              run_id TEXT NOT NULL REFERENCES runs(run_id),
              event_id TEXT NOT NULL,
              event_json TEXT NOT NULL,
              payload_digest TEXT NOT NULL,
              PRIMARY KEY(run_id,event_id)
            );
            CREATE TABLE IF NOT EXISTS content_objects(
              run_id TEXT NOT NULL REFERENCES runs(run_id),
              digest TEXT NOT NULL,
              media_type TEXT NOT NULL,
              size_bytes INTEGER NOT NULL,
              metadata_json TEXT NOT NULL,
              record_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY(run_id,digest)
            );
            CREATE TABLE IF NOT EXISTS legacy_imports(
              source_digest TEXT PRIMARY KEY,
              source_root TEXT NOT NULL,
              round_id TEXT NOT NULL,
              artifact_count INTEGER NOT NULL,
              imported_at TEXT NOT NULL
            );
            """
        )
        schema = _canonical_json_bytes(
            {
                "version": 1,
                "tables": [
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
                ],
            }
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations VALUES(1,?,?)",
            (
                datetime.now(timezone.utc).isoformat(),
                hashlib.sha256(schema).hexdigest(),
            ),
        )

    def _fault(self, boundary: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(boundary)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_run(
        self,
        run_id: str,
        *,
        task_identity: Mapping[str, Any] | None = None,
        authority: Mapping[str, Any] | None = None,
        parent_run_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(run_id, str) or not run_id.strip():
            raise SQLiteLedgerError("run_id must be nonempty", code="invalid_run_id")
        now = self._now()
        identity = dict(task_identity or {})
        authority_value = dict(authority or {})
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                    (
                        run_id,
                        0,
                        _canonical_json_bytes(identity).decode("utf-8"),
                        _canonical_json_bytes(authority_value).decode("utf-8"),
                        parent_run_id,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise SQLiteLedgerError("run already exists", code="duplicate_run") from exc
            self._append_event(
                connection,
                run_id=run_id,
                event_id="run-initialized",
                event_type="run_initialized",
                expected_revision=0,
                payload={"task_identity": identity},
                created_at=now,
            )
        return self.run(run_id)

    def run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise SQLiteLedgerError("run does not exist", code="run_not_found")
        return {
            "run_id": row["run_id"],
            "revision": int(row["revision"]),
            "task_identity": json.loads(row["task_identity_json"]),
            "authority": json.loads(row["authority_json"]),
            "parent_run_id": row["parent_run_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def events(self, run_id: str) -> list[dict[str, Any]]:
        self.run(run_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id=? ORDER BY sequence", (run_id,)
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "sequence": int(row["sequence"]),
                "event_type": row["event_type"],
                "expected_revision": int(row["expected_revision"]),
                "payload": json.loads(row["payload_json"]),
                "payload_digest": row["payload_digest"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def append_artifact(
        self,
        *,
        run_id: str,
        artifact_id: str,
        kind: str,
        payload: Mapping[str, Any],
        actor_kind: str,
        actor_id: str,
        status: str,
        parent_refs: Sequence[Mapping[str, Any]] = (),
        expected_revision: int | None = None,
        expected_run_revision: int | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT revision FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise SQLiteLedgerError("run does not exist", code="run_not_found")
            run_revision = int(run["revision"])
            if expected_run_revision is not None and run_revision != expected_run_revision:
                raise SQLiteLedgerError(
                    "run expected revision is stale", code="stale_run_revision"
                )
            current = int(
                connection.execute(
                    "SELECT COALESCE(MAX(revision),0) FROM artifacts "
                    "WHERE run_id=? AND artifact_id=?",
                    (run_id, artifact_id),
                ).fetchone()[0]
            )
            if expected_revision is not None and current != expected_revision:
                raise SQLiteLedgerError(
                    "artifact expected revision is stale", code="stale_revision"
                )
            revision = current + 1
            parents = [dict(item) for item in parent_refs]
            for parent in parents:
                if connection.execute(
                    "SELECT 1 FROM artifacts WHERE run_id=? AND artifact_id=? AND revision=?",
                    (
                        parent.get("run_id"),
                        parent.get("artifact_id"),
                        parent.get("revision"),
                    ),
                ).fetchone() is None:
                    raise SQLiteLedgerError(
                        "parent artifact does not resolve", code="dangling_parent"
                    )
            stamp = created_at or self._now()
            body = {
                "schema_version": 1,
                "kind": kind,
                "id": artifact_id,
                "run_id": run_id,
                "revision": revision,
                "created_at": stamp,
                "actor": {"kind": actor_kind, "id": actor_id},
                "status": status,
                "payload": dict(payload),
                "parent_refs": parents,
            }
            content_hash = hashlib.sha256(_canonical_json_bytes(body)).hexdigest()
            try:
                connection.execute(
                    "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        artifact_id,
                        revision,
                        kind,
                        1,
                        stamp,
                        actor_kind,
                        actor_id,
                        status,
                        _canonical_json_bytes(payload).decode("utf-8"),
                        content_hash,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise SQLiteLedgerError(
                    "artifact conflicts with immutable ledger",
                    code="artifact_conflict",
                ) from exc
            self._fault("after_artifact")
            for parent in parents:
                connection.execute(
                    "INSERT INTO artifact_parents VALUES(?,?,?,?,?,?)",
                    (
                        run_id,
                        artifact_id,
                        revision,
                        parent["run_id"],
                        parent["artifact_id"],
                        parent["revision"],
                    ),
                )
            self._fault("after_parents")
            next_run_revision = run_revision + 1
            connection.execute(
                "UPDATE runs SET revision=?,updated_at=? WHERE run_id=?",
                (next_run_revision, stamp, run_id),
            )
            self._fault("after_run_update")
            self._append_event(
                connection,
                run_id=run_id,
                event_id=f"artifact-{artifact_id}-{revision}",
                event_type="artifact_appended",
                expected_revision=run_revision,
                payload={"artifact_id": artifact_id, "revision": revision},
                created_at=stamp,
            )
            self._fault("after_event")
        return {**body, "content_hash": content_hash}

    def resolve(self, run_id: str, artifact_id: str, revision: int) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE run_id=? AND artifact_id=? AND revision=?",
                (run_id, artifact_id, revision),
            ).fetchone()
            if row is None:
                raise SQLiteLedgerError(
                    "artifact revision does not exist", code="artifact_not_found"
                )
            parents = connection.execute(
                "SELECT parent_run_id,parent_artifact_id,parent_revision "
                "FROM artifact_parents WHERE run_id=? AND artifact_id=? AND revision=? "
                "ORDER BY parent_run_id,parent_artifact_id,parent_revision",
                (run_id, artifact_id, revision),
            ).fetchall()
        body = {
            "schema_version": int(row["schema_version"]),
            "kind": row["kind"],
            "id": row["artifact_id"],
            "run_id": row["run_id"],
            "revision": int(row["revision"]),
            "created_at": row["created_at"],
            "actor": {"kind": row["actor_kind"], "id": row["actor_id"]},
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
            "parent_refs": [
                {
                    "run_id": item["parent_run_id"],
                    "artifact_id": item["parent_artifact_id"],
                    "revision": int(item["parent_revision"]),
                }
                for item in parents
            ],
        }
        if hashlib.sha256(_canonical_json_bytes(body)).hexdigest() != row["content_hash"]:
            raise SQLiteLedgerError(
                "artifact content hash mismatch", code="digest_mismatch"
            )
        return {**body, "content_hash": row["content_hash"]}

    def put_content(
        self,
        *,
        run_id: str,
        data: bytes,
        media_type: str,
        metadata: Mapping[str, Any] | None = None,
        expected_revision: int,
    ) -> dict[str, Any]:
        staged = self.cas.stage_bytes(
            data, media_type=media_type, metadata=dict(metadata or {})
        )
        digest = str(staged["digest"])
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT revision FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
                if row is None:
                    raise SQLiteLedgerError("run does not exist", code="run_not_found")
                if int(row["revision"]) != expected_revision:
                    raise SQLiteLedgerError(
                        "run expected revision is stale", code="stale_run_revision"
                    )
                prior = connection.execute(
                    "SELECT record_json FROM content_objects WHERE run_id=? AND digest=?",
                    (run_id, digest),
                ).fetchone()
                if prior is not None:
                    return json.loads(prior["record_json"])
                record = {
                    **staged,
                    "status": "committed",
                    "locator": self.cas.path_for(digest).as_posix(),
                }
                connection.execute(
                    "INSERT INTO content_objects VALUES(?,?,?,?,?,?,?)",
                    (
                        run_id,
                        digest,
                        media_type,
                        len(data),
                        _canonical_json_bytes(metadata or {}).decode("utf-8"),
                        _canonical_json_bytes(record).decode("utf-8"),
                        self._now(),
                    ),
                )
                connection.execute(
                    "UPDATE runs SET revision=revision+1,updated_at=? WHERE run_id=?",
                    (self._now(), run_id),
                )
                self._append_event(
                    connection,
                    run_id=run_id,
                    event_id=f"content-{digest}",
                    event_type="content_committed",
                    expected_revision=expected_revision,
                    payload={"digest": digest, "media_type": media_type},
                    created_at=self._now(),
                )
            promoted = self.cas.promote(digest)
            return {**record, **promoted}
        except Exception:
            self.cas.quarantine(digest, reason="ledger transaction failed")
            raise

    def reconstruct(self, run_id: str) -> dict[str, Any]:
        run = self.run(run_id)
        with self._connect() as connection:
            refs = connection.execute(
                "SELECT artifact_id,revision FROM artifacts WHERE run_id=? "
                "ORDER BY artifact_id,revision",
                (run_id,),
            ).fetchall()
            content = [
                json.loads(row["record_json"])
                for row in connection.execute(
                    "SELECT record_json FROM content_objects WHERE run_id=? ORDER BY digest",
                    (run_id,),
                ).fetchall()
            ]
        artifacts = [
            self.resolve(run_id, row["artifact_id"], int(row["revision"]))
            for row in refs
        ]
        projection = {
            "run": run,
            "artifacts": artifacts,
            "content_objects": content,
            "events": self.events(run_id),
        }
        return {
            "run_id": run_id,
            **projection,
            "semantic_digest": hashlib.sha256(
                _canonical_json_bytes(projection)
            ).hexdigest(),
        }

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        event_id: str,
        event_type: str,
        expected_revision: int,
        payload: Mapping[str, Any],
        created_at: str,
    ) -> None:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
        )
        raw = _canonical_json_bytes(payload)
        connection.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
            (
                run_id,
                event_id,
                sequence,
                event_type,
                expected_revision,
                raw.decode("utf-8"),
                hashlib.sha256(raw).hexdigest(),
                created_at,
            ),
        )
