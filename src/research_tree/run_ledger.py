"""Transactional SQLite ledger for the Alpha2 canonical run lineage."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sqlite3
from typing import Any, Iterable

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    DataIntegrityError,
    LineageEvent,
    RoundRecord,
    RoundSnapshot,
    canonical_json_bytes,
    validate_identifier,
)


class LedgerError(Exception):
    """Base class for expected ledger boundary failures."""


class LedgerConflictError(LedgerError):
    """Raised when a write uses an obsolete run revision."""


class LedgerIntegrityError(LedgerError, DataIntegrityError):
    """Raised when a persisted row or lineage reference is invalid."""


class RunLedger:
    """Own canonical run lineage in a workspace-scoped SQLite database."""

    SCHEMA_VERSION = 1

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.database = self.workspace / ".research-tree" / "run-ledger.sqlite3"

    def initialize(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    record_json BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    parent_run_id TEXT,
                    revision INTEGER NOT NULL CHECK (revision >= 0)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    artifact_json BLOB NOT NULL,
                    content_hash TEXT NOT NULL,
                    PRIMARY KEY (run_id, artifact_id, revision),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS artifact_parents (
                    run_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    parent_run_id TEXT NOT NULL,
                    parent_artifact_id TEXT NOT NULL,
                    parent_revision INTEGER NOT NULL CHECK (parent_revision > 0),
                    PRIMARY KEY (run_id, artifact_id, revision, parent_run_id,
                                 parent_artifact_id, parent_revision),
                    FOREIGN KEY (run_id, artifact_id, revision)
                      REFERENCES artifacts(run_id, artifact_id, revision)
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    event_json BLOB NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, event_id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS events_by_run
                  ON events(run_id, created_at, event_id);
                CREATE INDEX IF NOT EXISTS artifacts_by_run
                  ON artifacts(run_id, artifact_id, revision);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
                "VALUES(?, datetime('now'))",
                (self.SCHEMA_VERSION,),
            )

    def create_run(self, run_id: str, parent_run_id: str | None = None) -> RoundRecord:
        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        if parent_run_id is not None:
            parent_run_id = validate_identifier(parent_run_id, "parent_run_id")
        record = RoundRecord.create(run_id, parent_run_id)
        event = LineageEvent.create(
            round_id=run_id, kind="run-created", parent_round_id=parent_run_id
        )
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if parent_run_id is not None and not self._run_exists(connection, parent_run_id):
                    raise LedgerIntegrityError(f"parent run does not exist: {parent_run_id}")
                connection.execute(
                    "INSERT INTO runs(run_id, record_json, created_at, parent_run_id, revision) "
                    "VALUES(?, ?, ?, ?, 0)",
                    (run_id, _json(record.to_dict()), record.created_at, parent_run_id),
                )
                self._insert_event(connection, event)
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerConflictError(f"run already exists: {run_id}") from error
        return record

    def get_revision(self, run_id: str) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT revision FROM runs WHERE run_id = ?", (validate_identifier(run_id, "run_id"),)
            ).fetchone()
        if row is None:
            raise LedgerIntegrityError(f"run does not exist: {run_id}")
        return int(row[0])

    def append_artifact(
        self,
        run_id: str,
        artifact_id: str,
        kind: str,
        payload: Any,
        *,
        parent_refs: Iterable[ArtifactRef] = (),
        expected_revision: int,
    ) -> ArtifactRevision:
        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        parent_refs = tuple(parent_refs)
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._require_expected_revision(connection, run_id, expected_revision)
                for reference in parent_refs:
                    self._require_artifact(connection, reference)
                next_revision = self._next_artifact_revision(connection, run_id, artifact_id)
                artifact = ArtifactRevision.create(
                    artifact_id=artifact_id,
                    round_id=run_id,
                    revision=next_revision,
                    kind=kind,
                    payload=payload,
                    parent_refs=parent_refs,
                )
                connection.execute(
                    "INSERT INTO artifacts(run_id, artifact_id, revision, artifact_json, content_hash) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (run_id, artifact.id, artifact.revision, _json(artifact.to_dict()), artifact.content_hash),
                )
                for reference in parent_refs:
                    connection.execute(
                        "INSERT INTO artifact_parents(run_id, artifact_id, revision, parent_run_id, "
                        "parent_artifact_id, parent_revision) VALUES(?, ?, ?, ?, ?, ?)",
                        (run_id, artifact.id, artifact.revision, reference.round_id, reference.artifact_id, reference.revision),
                    )
                self._insert_event(connection, LineageEvent.create(
                    round_id=run_id,
                    kind="artifact-appended",
                    artifact_ref=ArtifactRef(run_id, artifact.id, artifact.revision),
                ))
                self._increment_revision(connection, run_id, current)
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("artifact append violated a ledger constraint") from error
        return artifact

    def append_event(
        self, run_id: str, event: LineageEvent, *, expected_revision: int
    ) -> LineageEvent:
        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        if event.round_id != run_id:
            raise LedgerIntegrityError("event round_id does not match target run")
        event_json = _json(event.to_dict())
        event_hash = _hash(event_json)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT event_json, content_hash FROM events WHERE run_id = ? AND event_id = ?",
                (run_id, event.id),
            ).fetchone()
            if existing is not None:
                if existing[1] != event_hash or existing[0] != event_json:
                    raise LedgerIntegrityError(f"event id payload conflict: {event.id}")
                return event
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._require_expected_revision(connection, run_id, expected_revision)
                self._insert_event(connection, event)
                self._increment_revision(connection, run_id, current)
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("event append violated a ledger constraint") from error
        return event

    def load_run(self, run_id: str) -> RoundSnapshot:
        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        with self._connect() as connection:
            run_row = connection.execute(
                "SELECT record_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run_row is None:
                raise LedgerIntegrityError(f"run does not exist: {run_id}")
            try:
                record = RoundRecord.from_dict(json.loads(run_row[0]))
                artifact_rows = connection.execute(
                    "SELECT artifact_json FROM artifacts WHERE run_id = ? "
                    "ORDER BY artifact_id, revision", (run_id,)
                ).fetchall()
                artifacts = tuple(ArtifactRevision.from_dict(json.loads(row[0])) for row in artifact_rows)
                by_ref = {ArtifactRef(item.round_id, item.id, item.revision) for item in artifacts}
                for artifact in artifacts:
                    for reference in artifact.parent_refs:
                        if reference not in by_ref and not self._artifact_exists(connection, reference):
                            raise LedgerIntegrityError(f"dangling artifact parent: {reference}")
                event_rows = connection.execute(
                    "SELECT event_json FROM events WHERE run_id = ? ORDER BY created_at, event_id", (run_id,)
                ).fetchall()
                events = tuple(LineageEvent.from_dict(json.loads(row[0])) for row in event_rows)
                for event in events:
                    if event.artifact_ref is not None and not self._artifact_exists(connection, event.artifact_ref):
                        raise LedgerIntegrityError(f"dangling event artifact reference: {event.artifact_ref}")
            except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
                raise LedgerIntegrityError("corrupt ledger row") from error
        return RoundSnapshot(record=record, artifacts=artifacts, lineage_events=events)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @staticmethod
    def _before_commit() -> None:
        """Fault-injection seam; production has no work here."""

    @staticmethod
    def _run_exists(connection: sqlite3.Connection, run_id: str) -> bool:
        return connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone() is not None

    @classmethod
    def _require_expected_revision(cls, connection: sqlite3.Connection, run_id: str, expected: int) -> int:
        row = connection.execute("SELECT revision FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise LedgerIntegrityError(f"run does not exist: {run_id}")
        current = int(row[0])
        if current != expected:
            raise LedgerConflictError(f"stale run revision: expected {expected}, current {current}")
        return current

    @staticmethod
    def _increment_revision(connection: sqlite3.Connection, run_id: str, current: int) -> None:
        connection.execute("UPDATE runs SET revision = ? WHERE run_id = ? AND revision = ?", (current + 1, run_id, current))

    @staticmethod
    def _next_artifact_revision(connection: sqlite3.Connection, run_id: str, artifact_id: str) -> int:
        artifact_id = validate_identifier(artifact_id, "artifact_id")
        row = connection.execute("SELECT COALESCE(MAX(revision), 0) FROM artifacts WHERE run_id = ? AND artifact_id = ?", (run_id, artifact_id)).fetchone()
        return int(row[0]) + 1

    @classmethod
    def _insert_event(cls, connection: sqlite3.Connection, event: LineageEvent) -> None:
        event_json = _json(event.to_dict())
        connection.execute(
            "INSERT INTO events(run_id, event_id, event_json, content_hash, created_at) VALUES(?, ?, ?, ?, ?)",
            (event.round_id, event.id, event_json, _hash(event_json), event.created_at),
        )

    @staticmethod
    def _artifact_exists(connection: sqlite3.Connection, reference: ArtifactRef) -> bool:
        return connection.execute(
            "SELECT 1 FROM artifacts WHERE run_id = ? AND artifact_id = ? AND revision = ?",
            (reference.round_id, reference.artifact_id, reference.revision),
        ).fetchone() is not None

    @classmethod
    def _require_artifact(cls, connection: sqlite3.Connection, reference: ArtifactRef) -> None:
        if not isinstance(reference, ArtifactRef) or not cls._artifact_exists(connection, reference):
            raise LedgerIntegrityError(f"artifact parent does not exist: {reference}")


def _json(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
