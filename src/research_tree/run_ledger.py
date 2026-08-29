"""Transactional SQLite ledger for the Alpha2 canonical run lineage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from .content_store import ContentAddressedStore, ContentObject
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    DataIntegrityError,
    LineageEvent,
    RoundRecord,
    RoundSnapshot,
    canonical_json_bytes,
    thaw_json,
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

    SCHEMA_VERSION = 7

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
                CREATE TABLE IF NOT EXISTS content_objects (
                    digest TEXT PRIMARY KEY,
                    media_type TEXT NOT NULL,
                    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
                    locator TEXT NOT NULL,
                    availability TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifact_contents (
                    run_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    digest TEXT NOT NULL,
                    PRIMARY KEY (run_id, artifact_id, revision),
                    FOREIGN KEY (run_id, artifact_id, revision)
                      REFERENCES artifacts(run_id, artifact_id, revision),
                    FOREIGN KEY (digest) REFERENCES content_objects(digest)
                );
                CREATE TABLE IF NOT EXISTS decision_frames (
                    run_id TEXT NOT NULL,
                    frame_id TEXT NOT NULL,
                    artifact_revision INTEGER NOT NULL CHECK (artifact_revision > 0),
                    status TEXT NOT NULL,
                    primary_decision_id TEXT NOT NULL,
                    requester_wording_digest TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, frame_id, artifact_revision),
                    FOREIGN KEY (run_id, frame_id, artifact_revision)
                      REFERENCES artifacts(run_id, artifact_id, revision)
                );
                CREATE TABLE IF NOT EXISTS strategy_projections (
                    run_id TEXT NOT NULL,
                    projection_id TEXT NOT NULL,
                    artifact_revision INTEGER NOT NULL CHECK (artifact_revision > 0),
                    strategy_revision INTEGER NOT NULL CHECK (strategy_revision > 0),
                    status TEXT NOT NULL,
                    display_digest TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, projection_id, artifact_revision),
                    FOREIGN KEY (run_id, projection_id, artifact_revision)
                      REFERENCES artifacts(run_id, artifact_id, revision)
                );
                CREATE TABLE IF NOT EXISTS preference_observations (
                    project_id TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    turn_number INTEGER NOT NULL CHECK (turn_number > 0),
                    observation_json BLOB NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, observation_id)
                );
                CREATE TABLE IF NOT EXISTS user_preference_profiles (
                    project_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    profile_json BLOB NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, revision)
                );
                CREATE TABLE IF NOT EXISTS completion_input_registrations (
                    run_id TEXT NOT NULL,
                    input_role TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    artifact_revision INTEGER NOT NULL CHECK (artifact_revision > 0),
                    registered_run_revision INTEGER NOT NULL CHECK (registered_run_revision >= 0),
                    issuer TEXT NOT NULL,
                    issuer_evidence_json BLOB NOT NULL,
                    PRIMARY KEY (run_id, input_role, registered_run_revision),
                    FOREIGN KEY (run_id, artifact_id, artifact_revision)
                      REFERENCES artifacts(run_id, artifact_id, revision)
                );
                CREATE INDEX IF NOT EXISTS completion_inputs_by_run_role
                  ON completion_input_registrations(run_id, input_role, registered_run_revision DESC);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, datetime('now'))",
                (self.SCHEMA_VERSION,),
            )

    def append_preference_state(self, observation: dict[str, Any], profile: dict[str, Any]) -> None:
        """Atomically append one observation and its resulting profile revision."""

        self.initialize()
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT content_hash FROM preference_observations WHERE project_id = ? AND observation_id = ?",
                    (observation["project_id"], observation["observation_id"]),
                ).fetchone()
                if existing is not None:
                    if existing[0] != observation["content_hash"]:
                        raise LedgerIntegrityError("preference observation id conflict")
                    return
                connection.execute(
                    "INSERT INTO preference_observations(project_id, observation_id, turn_number, observation_json, "
                    "content_hash, created_at) VALUES(?, ?, ?, ?, ?, datetime('now'))",
                    (
                        observation["project_id"],
                        observation["observation_id"],
                        observation["turn_number"],
                        _json(observation),
                        observation["content_hash"],
                    ),
                )
                self._insert_preference_profile(connection, profile)
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("preference state append violated a ledger constraint") from error

    def append_preference_profile(self, profile: dict[str, Any]) -> None:
        """Append a reset or administrative profile revision."""

        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._insert_preference_profile(connection, profile)

    @staticmethod
    def _insert_preference_profile(connection: sqlite3.Connection, profile: dict[str, Any]) -> None:
        connection.execute(
            "INSERT INTO user_preference_profiles(project_id, revision, profile_json, content_hash, created_at) "
            "VALUES(?, ?, ?, ?, datetime('now'))",
            (profile["project_id"], profile["revision"], _json(profile), profile["content_hash"]),
        )

    def load_preference_profile(self, project_id: str) -> dict[str, Any] | None:
        self.initialize()
        project_id = validate_identifier(project_id, "project_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT profile_json FROM user_preference_profiles WHERE project_id = ? ORDER BY revision DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return None if row is None else json.loads(row[0])

    def load_preference_observations(self, project_id: str) -> tuple[dict[str, Any], ...]:
        self.initialize()
        project_id = validate_identifier(project_id, "project_id")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT observation_json FROM preference_observations WHERE project_id = ? "
                "ORDER BY turn_number, observation_id",
                (project_id,),
            ).fetchall()
        return tuple(json.loads(row[0]) for row in rows)

    def delete_preference_project(self, project_id: str) -> None:
        self.initialize()
        project_id = validate_identifier(project_id, "project_id")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM user_preference_profiles WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM preference_observations WHERE project_id = ?", (project_id,))

    def append_decision_frame(
        self,
        run_id: str,
        frame_id: str,
        payload: Any,
        *,
        parent_refs: Iterable[ArtifactRef] = (),
        expected_revision: int,
    ) -> ArtifactRevision:
        """Atomically append a canonical DecisionFrame and its v4 projection."""

        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        frame_id = validate_identifier(frame_id, "frame_id")
        if not isinstance(payload, dict):
            raise LedgerIntegrityError("decision frame payload must be a mapping")
        parent_refs = tuple(parent_refs)
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._require_expected_revision(connection, run_id, expected_revision)
                for reference in parent_refs:
                    self._require_artifact(connection, reference)
                next_revision = self._next_artifact_revision(connection, run_id, frame_id)
                artifact = ArtifactRevision.create(
                    artifact_id=frame_id,
                    round_id=run_id,
                    revision=next_revision,
                    kind="decision-frame",
                    payload=payload,
                    parent_refs=parent_refs,
                )
                artifact_json = _json(artifact.to_dict())
                connection.execute(
                    "INSERT INTO artifacts(run_id, artifact_id, revision, artifact_json, content_hash) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (run_id, frame_id, next_revision, artifact_json, artifact.content_hash),
                )
                for reference in parent_refs:
                    connection.execute(
                        "INSERT INTO artifact_parents(run_id, artifact_id, revision, parent_run_id, "
                        "parent_artifact_id, parent_revision) VALUES(?, ?, ?, ?, ?, ?)",
                        (
                            run_id,
                            frame_id,
                            next_revision,
                            reference.round_id,
                            reference.artifact_id,
                            reference.revision,
                        ),
                    )
                connection.execute(
                    "INSERT INTO decision_frames(run_id, frame_id, artifact_revision, status, primary_decision_id, "
                    "requester_wording_digest, content_hash, payload_json, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        frame_id,
                        next_revision,
                        payload["status"],
                        payload["primary_decision"]["id"],
                        _hash(_json(payload["requester_wording"])),
                        payload["content_hash"],
                        _json(payload),
                        artifact.created_at,
                    ),
                )
                self._insert_event(
                    connection,
                    LineageEvent.create(
                        round_id=run_id,
                        kind="artifact-appended",
                        artifact_ref=ArtifactRef(run_id, frame_id, next_revision),
                    ),
                )
                self._increment_revision(connection, run_id, current)
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("decision frame append violated a ledger constraint") from error
        return artifact

    def append_strategy_projection(
        self,
        run_id: str,
        projection_id: str,
        payload: Any,
        *,
        parent_refs: Iterable[ArtifactRef],
        expected_revision: int,
    ) -> ArtifactRevision:
        """Atomically append a StrategyProjection and its v5 read model."""

        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        projection_id = validate_identifier(projection_id, "projection_id")
        if not isinstance(payload, dict):
            raise LedgerIntegrityError("strategy projection payload must be a mapping")
        parent_refs = tuple(parent_refs)
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._require_expected_revision(connection, run_id, expected_revision)
                for reference in parent_refs:
                    self._require_artifact(connection, reference)
                next_revision = self._next_artifact_revision(connection, run_id, projection_id)
                artifact = ArtifactRevision.create(
                    artifact_id=projection_id,
                    round_id=run_id,
                    revision=next_revision,
                    kind="strategy-projection",
                    payload=payload,
                    parent_refs=parent_refs,
                )
                connection.execute(
                    "INSERT INTO artifacts(run_id, artifact_id, revision, artifact_json, content_hash) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (run_id, projection_id, next_revision, _json(artifact.to_dict()), artifact.content_hash),
                )
                for reference in parent_refs:
                    connection.execute(
                        "INSERT INTO artifact_parents(run_id, artifact_id, revision, parent_run_id, "
                        "parent_artifact_id, parent_revision) VALUES(?, ?, ?, ?, ?, ?)",
                        (
                            run_id,
                            projection_id,
                            next_revision,
                            reference.round_id,
                            reference.artifact_id,
                            reference.revision,
                        ),
                    )
                connection.execute(
                    "INSERT INTO strategy_projections(run_id, projection_id, artifact_revision, strategy_revision, "
                    "status, display_digest, content_hash, payload_json, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        projection_id,
                        next_revision,
                        payload["revision"],
                        payload["status"],
                        payload["display_digest"],
                        payload["content_hash"],
                        _json(payload),
                        artifact.created_at,
                    ),
                )
                self._insert_event(
                    connection,
                    LineageEvent.create(
                        round_id=run_id,
                        kind="artifact-appended",
                        artifact_ref=ArtifactRef(run_id, projection_id, next_revision),
                    ),
                )
                self._increment_revision(connection, run_id, current)
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("strategy projection append violated a ledger constraint") from error
        return artifact

    def register_content(self, content: ContentObject) -> ContentObject:
        """Register verified CAS metadata; repeated identical registration is idempotent."""
        self.initialize()
        with self._connect() as connection:
            return self._register_content_row(connection, content)

    def bind_content(self, reference: ArtifactRef, content: ContentObject) -> None:
        """Bind a registered digest to one immutable artifact revision."""
        self.initialize()
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if not self._artifact_exists(connection, reference):
                    raise LedgerIntegrityError(f"artifact does not exist: {reference}")
                row = connection.execute(
                    "SELECT digest FROM content_objects WHERE digest = ?", (content.digest,)
                ).fetchone()
                if row is None:
                    raise LedgerIntegrityError(f"content is not registered: {content.digest}")
                current = connection.execute(
                    "SELECT digest FROM artifact_contents WHERE run_id = ? AND artifact_id = ? AND revision = ?",
                    (reference.round_id, reference.artifact_id, reference.revision),
                ).fetchone()
                if current is not None:
                    if current[0] != content.digest:
                        raise LedgerIntegrityError(f"artifact content conflict: {reference}")
                    return
                connection.execute(
                    "INSERT INTO artifact_contents(run_id, artifact_id, revision, digest) VALUES(?, ?, ?, ?)",
                    (reference.round_id, reference.artifact_id, reference.revision, content.digest),
                )
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("content binding violated a ledger constraint") from error

    def get_content(self, digest: str) -> ContentObject:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT digest, media_type, byte_size, locator, availability, created_at "
                "FROM content_objects WHERE digest = ?",
                (digest,),
            ).fetchone()
        if row is None:
            raise LedgerIntegrityError(f"content does not exist: {digest}")
        return ContentObject(*tuple(row))

    def get_artifact(self, reference: ArtifactRef) -> ArtifactRevision:
        """Load one immutable artifact revision by exact identity."""

        self.initialize()
        if not isinstance(reference, ArtifactRef):
            raise LedgerIntegrityError("artifact reference must be an ArtifactRef")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT artifact_json FROM artifacts WHERE run_id = ? AND artifact_id = ? AND revision = ?",
                (reference.round_id, reference.artifact_id, reference.revision),
            ).fetchone()
        if row is None:
            raise LedgerIntegrityError(f"artifact does not exist: {reference}")
        try:
            artifact = ArtifactRevision.from_dict(json.loads(row[0]))
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise LedgerIntegrityError(f"corrupt artifact row: {reference}") from error
        if ArtifactRef(artifact.round_id, artifact.id, artifact.revision) != reference:
            raise LedgerIntegrityError(f"artifact identity does not match its row: {reference}")
        return artifact

    def list_artifacts(self, run_id: str) -> tuple[ArtifactRevision, ...]:
        """Return all immutable artifact revisions for a run in insertion order."""
        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT artifact_json FROM artifacts WHERE run_id = ? ORDER BY rowid", (run_id,)
            ).fetchall()
        try:
            return tuple(ArtifactRevision.from_dict(json.loads(row[0])) for row in rows)
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise LedgerIntegrityError(f"corrupt artifact row in run: {run_id}") from error

    def is_latest_artifact(self, reference: ArtifactRef) -> bool:
        """Return whether an exact artifact revision is current for its identity."""

        self.initialize()
        if not isinstance(reference, ArtifactRef):
            raise LedgerIntegrityError("artifact reference must be an ArtifactRef")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT MAX(revision) FROM artifacts WHERE run_id = ? AND artifact_id = ?",
                (reference.round_id, reference.artifact_id),
            ).fetchone()
        if row is None or row[0] is None:
            raise LedgerIntegrityError(f"artifact does not exist: {reference}")
        return int(row[0]) == reference.revision

    def get_bound_content(self, reference: ArtifactRef) -> ContentObject:
        """Load the content metadata bound to one immutable artifact revision."""

        self.initialize()
        if not isinstance(reference, ArtifactRef):
            raise LedgerIntegrityError("artifact reference must be an ArtifactRef")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT object.digest, object.media_type, object.byte_size, object.locator, "
                "object.availability, object.created_at "
                "FROM artifact_contents binding "
                "JOIN content_objects object ON object.digest = binding.digest "
                "WHERE binding.run_id = ? AND binding.artifact_id = ? AND binding.revision = ?",
                (reference.round_id, reference.artifact_id, reference.revision),
            ).fetchone()
        if row is None:
            raise LedgerIntegrityError(f"artifact has no bound content: {reference}")
        return ContentObject(*tuple(row))

    def resolve_content(self, reference: ArtifactRef, store: ContentAddressedStore) -> bytes:
        """Resolve an artifact's bound content through metadata and CAS verification."""
        content = self.get_bound_content(reference)
        if content.availability != "available":
            raise LedgerIntegrityError(f"content is not available: {content.digest}")
        return store.read(content)

    def create_run(self, run_id: str, parent_run_id: str | None = None) -> RoundRecord:
        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        if parent_run_id is not None:
            parent_run_id = validate_identifier(parent_run_id, "parent_run_id")
        record = RoundRecord.create(run_id, parent_run_id)
        event = LineageEvent.create(round_id=run_id, kind="run-created", parent_round_id=parent_run_id)
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if parent_run_id is not None and not self._run_exists(connection, parent_run_id):
                    raise LedgerIntegrityError(f"parent run does not exist: {parent_run_id}")
                connection.execute(
                    "INSERT INTO runs(run_id, record_json, created_at, parent_run_id, revision) VALUES(?, ?, ?, ?, 0)",
                    (run_id, _json(record.to_dict()), record.created_at, parent_run_id),
                )
                self._insert_event(connection, event)
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerConflictError(f"run already exists: {run_id}") from error
        return record

    def create_successor_with_artifact_batches(
        self,
        *,
        predecessor_run_id: str,
        successor_run_id: str,
        successor_parent_run_id: str | None,
        expected_predecessor_revision: int,
        successor_entries: Iterable[tuple[str, str, Any, Iterable[ArtifactRef]]],
        predecessor_entries: Iterable[tuple[str, str, Any, Iterable[ArtifactRef]]],
    ) -> tuple[RoundRecord, tuple[ArtifactRevision, ...], tuple[ArtifactRevision, ...]]:
        """Atomically create one successor and append artifacts to both runs.

        This restricted operation exists for feedback lineage: it compares one
        predecessor revision, creates one new child or root successor, and
        appends ordered batches to both runs under a single SQLite transaction.
        """

        self.initialize()
        predecessor_run_id = validate_identifier(predecessor_run_id, "predecessor_run_id")
        successor_run_id = validate_identifier(successor_run_id, "successor_run_id")
        if predecessor_run_id == successor_run_id:
            raise LedgerIntegrityError("successor_run_id must differ from predecessor_run_id")
        if successor_parent_run_id is not None:
            successor_parent_run_id = validate_identifier(successor_parent_run_id, "successor_parent_run_id")
        if successor_parent_run_id not in {None, predecessor_run_id}:
            raise LedgerIntegrityError("successor parent must be the predecessor or None")
        if (
            isinstance(expected_predecessor_revision, bool)
            or not isinstance(expected_predecessor_revision, int)
            or expected_predecessor_revision < 0
        ):
            raise LedgerIntegrityError("expected_predecessor_revision must be a non-negative integer")
        normalized_successor = tuple(successor_entries)
        normalized_predecessor = tuple(predecessor_entries)
        if not normalized_successor:
            raise LedgerIntegrityError("successor artifact batch must contain at least one entry")
        if not normalized_predecessor:
            raise LedgerIntegrityError("predecessor artifact batch must contain at least one entry")
        record = RoundRecord.create(successor_run_id, successor_parent_run_id)

        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current_predecessor = self._require_expected_revision(
                    connection,
                    predecessor_run_id,
                    expected_predecessor_revision,
                )
                if self._run_exists(connection, successor_run_id):
                    raise LedgerConflictError(f"run already exists: {successor_run_id}")
                connection.execute(
                    "INSERT INTO runs(run_id, record_json, created_at, parent_run_id, revision) VALUES(?, ?, ?, ?, 0)",
                    (successor_run_id, _json(record.to_dict()), record.created_at, successor_parent_run_id),
                )
                self._insert_event(
                    connection,
                    LineageEvent.create(
                        round_id=successor_run_id,
                        kind="run-created",
                        parent_round_id=successor_parent_run_id,
                    ),
                )
                created: set[ArtifactRef] = set()
                successor_artifacts = self._append_transaction_artifacts(
                    connection,
                    successor_run_id,
                    normalized_successor,
                    created,
                    "successor",
                )
                predecessor_artifacts = self._append_transaction_artifacts(
                    connection,
                    predecessor_run_id,
                    normalized_predecessor,
                    created,
                    "predecessor",
                )
                successor_update = connection.execute(
                    "UPDATE runs SET revision = ? WHERE run_id = ? AND revision = 0",
                    (len(successor_artifacts), successor_run_id),
                )
                predecessor_update = connection.execute(
                    "UPDATE runs SET revision = ? WHERE run_id = ? AND revision = ?",
                    (
                        current_predecessor + len(predecessor_artifacts),
                        predecessor_run_id,
                        expected_predecessor_revision,
                    ),
                )
                if successor_update.rowcount != 1 or predecessor_update.rowcount != 1:
                    raise LedgerConflictError("run revision changed during successor transaction")
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("successor transaction violated a ledger constraint") from error
        return record, successor_artifacts, predecessor_artifacts

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
                        (
                            run_id,
                            artifact.id,
                            artifact.revision,
                            reference.round_id,
                            reference.artifact_id,
                            reference.revision,
                        ),
                    )
                self._insert_event(
                    connection,
                    LineageEvent.create(
                        round_id=run_id,
                        kind="artifact-appended",
                        artifact_ref=ArtifactRef(run_id, artifact.id, artifact.revision),
                    ),
                )
                self._increment_revision(connection, run_id, current)
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("artifact append violated a ledger constraint") from error
        return artifact

    def append_completion_input(
        self,
        run_id: str,
        artifact_id: str,
        input_role: str,
        kind: str,
        payload: Any,
        *,
        parent_refs: Iterable[ArtifactRef],
        issuer: str,
        issuer_evidence: dict[str, Any],
        expected_revision: int,
    ) -> ArtifactRevision:
        """Atomically write one validated completion input and its registration."""

        return self.append_completion_input_batch(
            run_id,
            (
                (
                    artifact_id,
                    input_role,
                    kind,
                    payload,
                    parent_refs,
                    issuer,
                    issuer_evidence,
                ),
            ),
            expected_revision=expected_revision,
        )[0]

    def append_completion_input_batch(
        self,
        run_id: str,
        entries: Iterable[tuple[str, str, str, Any, Iterable[ArtifactRef], str, dict[str, Any]]],
        *,
        expected_revision: int,
    ) -> tuple[ArtifactRevision, ...]:
        """Atomically append typed completion inputs and their registrations.

        A matching complete batch is replay-safe.  A partial or conflicting
        batch is rejected so a delivery pair can never leave one authoritative
        surface without the other.
        """

        allowed_kinds = {
            "closure": "slot-closure-assessment",
            "insight": "insight-digest",
            "readiness": "readiness-record",
            "evaluation": "blueprint-evaluation",
            "technical_delivery": "technical-research-package",
            "human_delivery": "human-research-report",
            "acceptance": "delivery-acceptance",
        }
        required_issuers = {
            "technical_delivery": "canonical-delivery-compiler-v1",
            "human_delivery": "canonical-delivery-compiler-v1",
            "acceptance": "human-delivery-acceptance-v1",
        }
        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise LedgerIntegrityError("expected_revision must be a non-negative integer")
        normalized = tuple(entries)
        if not normalized:
            raise LedgerIntegrityError("completion input batch must contain at least one entry")
        prepared: list[tuple[str, str, str, Any, tuple[ArtifactRef, ...], str, dict[str, Any]]] = []
        seen_roles: set[str] = set()
        seen_ids: set[str] = set()
        for index, entry in enumerate(normalized):
            if not isinstance(entry, Sequence) or isinstance(entry, (str, bytes)) or len(entry) != 7:
                raise LedgerIntegrityError(
                    f"completion input batch entry {index} must contain id, role, kind, payload, parents, issuer, and evidence"
                )
            artifact_id, input_role, kind, payload, raw_parent_refs, issuer, issuer_evidence = entry
            artifact_id = validate_identifier(artifact_id, f"completion input batch entry {index} id")
            if allowed_kinds.get(input_role) != kind:
                raise LedgerIntegrityError("unsupported completion input role or kind")
            if input_role in seen_roles or artifact_id in seen_ids:
                raise LedgerIntegrityError("completion input batch roles and artifact ids must be distinct")
            seen_roles.add(input_role)
            seen_ids.add(artifact_id)
            if not isinstance(issuer, str) or not issuer.strip() or not isinstance(issuer_evidence, dict):
                raise LedgerIntegrityError("completion input issuer evidence is malformed")
            if input_role in required_issuers and issuer != required_issuers[input_role]:
                raise LedgerIntegrityError("completion input issuer is not canonical")
            if not isinstance(raw_parent_refs, Iterable) or isinstance(raw_parent_refs, (str, bytes)):
                raise LedgerIntegrityError("completion input parents must be iterable")
            parent_refs = tuple(raw_parent_refs)
            if any(not isinstance(reference, ArtifactRef) for reference in parent_refs):
                raise LedgerIntegrityError("completion input parents must be ArtifactRef values")
            if len(set(parent_refs)) != len(parent_refs):
                raise LedgerIntegrityError("completion input parents must be distinct")
            prepared.append((artifact_id, input_role, kind, payload, parent_refs, issuer, issuer_evidence))

        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                prior_rows = []
                for artifact_id, input_role, kind, payload, parent_refs, issuer, issuer_evidence in prepared:
                    existing = connection.execute(
                        "SELECT artifact_json, issuer, issuer_evidence_json FROM completion_input_registrations registration "
                        "JOIN artifacts artifact ON artifact.run_id = registration.run_id "
                        "AND artifact.artifact_id = registration.artifact_id "
                        "AND artifact.revision = registration.artifact_revision "
                        "WHERE registration.run_id = ? AND registration.input_role = ? "
                        "AND registration.artifact_id = ? ORDER BY registration.registered_run_revision DESC LIMIT 1",
                        (run_id, input_role, artifact_id),
                    ).fetchone()
                    prior_rows.append(existing)
                if any(row is not None for row in prior_rows):
                    if not all(row is not None for row in prior_rows):
                        raise LedgerIntegrityError("completion input batch conflicts with a partial registration")
                    replayed: list[ArtifactRevision] = []
                    for row, (_, _, kind, payload, parent_refs, issuer, issuer_evidence) in zip(
                        prior_rows, prepared, strict=True
                    ):
                        prior = ArtifactRevision.from_dict(json.loads(row[0]))
                        if not (
                            prior.kind == kind
                            and prior.parent_refs == parent_refs
                            and _json(thaw_json(prior.payload)) == _json(payload)
                            and row[1] == issuer
                            and row[2] == _json(issuer_evidence)
                        ):
                            raise LedgerIntegrityError("completion input id conflicts with an existing registration")
                        replayed.append(prior)
                    return tuple(replayed)

                current = self._require_expected_revision(connection, run_id, expected_revision)
                quarantined = self._quarantined_refs(connection, run_id)
                created: set[ArtifactRef] = set()
                result: list[ArtifactRevision] = []
                for artifact_id, input_role, kind, payload, parent_refs, issuer, issuer_evidence in prepared:
                    for reference in parent_refs:
                        if reference in created:
                            continue
                        if reference.round_id != run_id:
                            raise LedgerIntegrityError("completion input lineage belongs to another run")
                        self._require_artifact(connection, reference)
                        if not self._is_latest_artifact(connection, reference) or reference in quarantined:
                            raise LedgerIntegrityError("completion input lineage is stale or quarantined")
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
                            (
                                run_id,
                                artifact.id,
                                artifact.revision,
                                reference.round_id,
                                reference.artifact_id,
                                reference.revision,
                            ),
                        )
                    connection.execute(
                        "INSERT INTO completion_input_registrations("
                        "run_id, input_role, artifact_id, artifact_revision, registered_run_revision, issuer, "
                        "issuer_evidence_json) VALUES(?, ?, ?, ?, ?, ?, ?)",
                        (run_id, input_role, artifact.id, artifact.revision, current, issuer, _json(issuer_evidence)),
                    )
                    artifact_ref = ArtifactRef(run_id, artifact.id, artifact.revision)
                    self._insert_event(
                        connection,
                        LineageEvent.create(
                            round_id=run_id,
                            kind="completion-input-registered",
                            artifact_ref=artifact_ref,
                        ),
                    )
                    created.add(artifact_ref)
                    result.append(artifact)
                    current += 1
                connection.execute(
                    "UPDATE runs SET revision = ? WHERE run_id = ? AND revision = ?",
                    (current, run_id, expected_revision),
                )
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("completion input registration violated a ledger constraint") from error
        return tuple(result)

    def list_completion_inputs(self, run_id: str) -> tuple[ArtifactRevision, ...]:
        """Return the newest registered, current completion input for each role."""

        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        with self._connect() as connection:
            quarantined = self._quarantined_refs(connection, run_id)
            rows = connection.execute(
                "SELECT artifact_json FROM completion_input_registrations registration "
                "JOIN artifacts artifact ON artifact.run_id = registration.run_id "
                "AND artifact.artifact_id = registration.artifact_id "
                "AND artifact.revision = registration.artifact_revision "
                "WHERE registration.run_id = ? ORDER BY registration.input_role, registration.registered_run_revision DESC",
                (run_id,),
            ).fetchall()
        selected: dict[str, ArtifactRevision] = {}
        for row in rows:
            artifact = ArtifactRevision.from_dict(json.loads(row[0]))
            reference = ArtifactRef(artifact.round_id, artifact.id, artifact.revision)
            if reference in quarantined or artifact.kind not in {
                "slot-closure-assessment",
                "insight-digest",
                "readiness-record",
                "blueprint-evaluation",
                "technical-research-package",
                "human-research-report",
                "delivery-acceptance",
            }:
                continue
            if self.is_latest_artifact(reference):
                role = {
                    "slot-closure-assessment": "closure",
                    "insight-digest": "insight",
                    "readiness-record": "readiness",
                    "blueprint-evaluation": "evaluation",
                    "technical-research-package": "technical_delivery",
                    "human-research-report": "human_delivery",
                    "delivery-acceptance": "acceptance",
                }.get(artifact.kind)
                if role is None:
                    continue
                selected.setdefault(role, artifact)
        return tuple(selected[role] for role in sorted(selected))

    def list_completion_input_registrations(self, run_id: str) -> dict[str, tuple[ArtifactRevision, ...]]:
        """Return every current registered artifact grouped by its typed role."""

        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        with self._connect() as connection:
            quarantined = self._quarantined_refs(connection, run_id)
            rows = connection.execute(
                "SELECT registration.input_role, artifact.artifact_json "
                "FROM completion_input_registrations registration "
                "JOIN artifacts artifact ON artifact.run_id = registration.run_id "
                "AND artifact.artifact_id = registration.artifact_id "
                "AND artifact.revision = registration.artifact_revision "
                "WHERE registration.run_id = ? "
                "ORDER BY registration.input_role, registration.registered_run_revision DESC",
                (run_id,),
            ).fetchall()
        grouped: dict[str, list[ArtifactRevision]] = {}
        seen_refs: set[ArtifactRef] = set()
        for row in rows:
            artifact = ArtifactRevision.from_dict(json.loads(row[1]))
            reference = ArtifactRef(artifact.round_id, artifact.id, artifact.revision)
            if reference in seen_refs or reference in quarantined or not self.is_latest_artifact(reference):
                continue
            seen_refs.add(reference)
            grouped.setdefault(str(row[0]), []).append(artifact)
        return {role: tuple(items) for role, items in grouped.items()}

    def append_artifact_batch(
        self,
        run_id: str,
        entries: Iterable[tuple[str, str, Any, Iterable[ArtifactRef]]],
        *,
        expected_revision: int,
    ) -> tuple[ArtifactRevision, ...]:
        """Append an ordered artifact batch under one run revision.

        Parents may reference artifacts already in the ledger or an earlier
        entry in this batch. The run revision is advanced only after every
        artifact, parent row, and lineage event has been prepared.
        """

        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise LedgerIntegrityError("expected_revision must be a non-negative integer")
        normalized = tuple(entries)
        if not normalized:
            raise LedgerIntegrityError("artifact batch must contain at least one entry")

        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._require_expected_revision(connection, run_id, expected_revision)
                created: set[ArtifactRef] = set()
                result: list[ArtifactRevision] = []
                for index, entry in enumerate(normalized):
                    if not isinstance(entry, Sequence) or isinstance(entry, (str, bytes)) or len(entry) != 4:
                        raise LedgerIntegrityError(
                            f"artifact batch entry {index} must contain id, kind, payload, and parent_refs"
                        )
                    artifact_id, kind, payload, raw_parent_refs = entry
                    artifact_id = validate_identifier(artifact_id, f"artifact batch entry {index} id")
                    if not isinstance(raw_parent_refs, Iterable) or isinstance(raw_parent_refs, (str, bytes)):
                        raise LedgerIntegrityError(f"artifact batch entry {index} parent_refs must be iterable")
                    parent_refs = tuple(raw_parent_refs)
                    for reference in parent_refs:
                        if not isinstance(reference, ArtifactRef):
                            raise LedgerIntegrityError(
                                f"artifact batch entry {index} parent_refs must contain ArtifactRef values"
                            )
                        if reference in created:
                            continue
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
                            (
                                run_id,
                                artifact.id,
                                artifact.revision,
                                reference.round_id,
                                reference.artifact_id,
                                reference.revision,
                            ),
                        )
                    artifact_ref = ArtifactRef(run_id, artifact.id, artifact.revision)
                    self._insert_event(
                        connection,
                        LineageEvent.create(
                            round_id=run_id,
                            kind="artifact-appended",
                            artifact_ref=artifact_ref,
                        ),
                    )
                    created.add(artifact_ref)
                    result.append(artifact)
                    current += 1
                connection.execute(
                    "UPDATE runs SET revision = ? WHERE run_id = ? AND revision = ?",
                    (current, run_id, expected_revision),
                )
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("artifact batch append violated a ledger constraint") from error
        return tuple(result)

    def append_artifact_with_content(
        self,
        run_id: str,
        artifact_id: str,
        kind: str,
        payload: Any,
        content: ContentObject,
        store: ContentAddressedStore,
        *,
        parent_refs: Iterable[ArtifactRef] = (),
        expected_revision: int,
        expected_artifact_revision: int | None = None,
    ) -> ArtifactRevision:
        """Atomically append an artifact and bind verified CAS content.

        CAS publication predates this operation, so a failed transaction can
        leave an unbound object on disk. That object is not authoritative until
        this transaction commits its metadata and exact artifact binding.
        """

        self.initialize()
        run_id = validate_identifier(run_id, "run_id")
        if not isinstance(content, ContentObject):
            raise LedgerIntegrityError("content must be a ContentObject")
        if not isinstance(store, ContentAddressedStore):
            raise LedgerIntegrityError("store must be a ContentAddressedStore")
        if content.availability != "available":
            raise LedgerIntegrityError(f"content is not available: {content.digest}")
        if expected_artifact_revision is not None:
            if (
                isinstance(expected_artifact_revision, bool)
                or not isinstance(expected_artifact_revision, int)
                or expected_artifact_revision < 1
            ):
                raise LedgerIntegrityError("expected_artifact_revision must be a positive integer")

        verified_bytes = store.read(content)
        if len(verified_bytes) != content.byte_size:
            raise LedgerIntegrityError(f"CAS byte-size mismatch: {content.digest}")
        parent_refs = tuple(parent_refs)
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._require_expected_revision(connection, run_id, expected_revision)
                registered = self._register_content_row(connection, content)
                for reference in parent_refs:
                    self._require_artifact(connection, reference)
                next_revision = self._next_artifact_revision(connection, run_id, artifact_id)
                if expected_artifact_revision is not None and next_revision != expected_artifact_revision:
                    raise LedgerConflictError(
                        f"stale artifact revision: expected {expected_artifact_revision}, current {next_revision}"
                    )
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
                        (
                            run_id,
                            artifact.id,
                            artifact.revision,
                            reference.round_id,
                            reference.artifact_id,
                            reference.revision,
                        ),
                    )
                artifact_ref = ArtifactRef(run_id, artifact.id, artifact.revision)
                connection.execute(
                    "INSERT INTO artifact_contents(run_id, artifact_id, revision, digest) VALUES(?, ?, ?, ?)",
                    (run_id, artifact.id, artifact.revision, registered.digest),
                )
                self._insert_event(
                    connection,
                    LineageEvent.create(
                        round_id=run_id,
                        kind="artifact-content-appended",
                        artifact_ref=artifact_ref,
                    ),
                )
                self._increment_revision(connection, run_id, current)
                self._before_commit()
            except sqlite3.IntegrityError as error:
                raise LedgerIntegrityError("artifact content append violated a ledger constraint") from error
        return artifact

    def append_event(self, run_id: str, event: LineageEvent, *, expected_revision: int) -> LineageEvent:
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
                if event.artifact_ref is not None:
                    self._require_artifact(connection, event.artifact_ref)
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
            run_row = connection.execute("SELECT record_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if run_row is None:
                raise LedgerIntegrityError(f"run does not exist: {run_id}")
            try:
                record = RoundRecord.from_dict(json.loads(run_row[0]))
                artifact_rows = connection.execute(
                    "SELECT artifact_json FROM artifacts WHERE run_id = ? ORDER BY artifact_id, revision", (run_id,)
                ).fetchall()
                artifacts = tuple(ArtifactRevision.from_dict(json.loads(row[0])) for row in artifact_rows)
                by_ref = {ArtifactRef(item.round_id, item.id, item.revision) for item in artifacts}
                for artifact in artifacts:
                    for reference in artifact.parent_refs:
                        if reference not in by_ref and not self._artifact_exists(connection, reference):
                            raise LedgerIntegrityError(f"dangling artifact parent: {reference}")
                event_rows = connection.execute(
                    "SELECT event_json FROM events WHERE run_id = ? ORDER BY rowid", (run_id,)
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
    def _register_content_row(connection: sqlite3.Connection, content: ContentObject) -> ContentObject:
        existing = connection.execute(
            "SELECT media_type, byte_size, locator, availability, created_at FROM content_objects WHERE digest = ?",
            (content.digest,),
        ).fetchone()
        if existing is not None:
            if tuple(existing[:4]) != (
                content.media_type,
                content.byte_size,
                content.locator,
                content.availability,
            ):
                raise LedgerIntegrityError(f"content metadata conflict: {content.digest}")
            return ContentObject(content.digest, *tuple(existing))
        connection.execute(
            "INSERT INTO content_objects(digest, media_type, byte_size, locator, availability, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (
                content.digest,
                content.media_type,
                content.byte_size,
                content.locator,
                content.availability,
                content.created_at,
            ),
        )
        return content

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
        connection.execute(
            "UPDATE runs SET revision = ? WHERE run_id = ? AND revision = ?", (current + 1, run_id, current)
        )

    @staticmethod
    def _next_artifact_revision(connection: sqlite3.Connection, run_id: str, artifact_id: str) -> int:
        artifact_id = validate_identifier(artifact_id, "artifact_id")
        row = connection.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM artifacts WHERE run_id = ? AND artifact_id = ?",
            (run_id, artifact_id),
        ).fetchone()
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
        return (
            connection.execute(
                "SELECT 1 FROM artifacts WHERE run_id = ? AND artifact_id = ? AND revision = ?",
                (reference.round_id, reference.artifact_id, reference.revision),
            ).fetchone()
            is not None
        )

    @staticmethod
    def _is_latest_artifact(connection: sqlite3.Connection, reference: ArtifactRef) -> bool:
        row = connection.execute(
            "SELECT MAX(revision) FROM artifacts WHERE run_id = ? AND artifact_id = ?",
            (reference.round_id, reference.artifact_id),
        ).fetchone()
        return row is not None and row[0] is not None and int(row[0]) == reference.revision

    @staticmethod
    def _quarantined_refs(connection: sqlite3.Connection, run_id: str) -> set[ArtifactRef]:
        rows = connection.execute(
            "SELECT artifact_json FROM artifacts WHERE run_id = ? AND artifact_json LIKE '%stale-state-quarantine%'",
            (run_id,),
        ).fetchall()
        result: set[ArtifactRef] = set()
        for row in rows:
            try:
                payload = json.loads(row[0])["payload"]
                for value in payload.get("dependent_refs", ()):
                    result.add(ArtifactRef.from_dict(value))
                for value in payload.get("stale_bindings", {}).values():
                    result.add(ArtifactRef.from_dict(value["artifact_ref"]))
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
        return result

    @classmethod
    def _require_artifact(cls, connection: sqlite3.Connection, reference: ArtifactRef) -> None:
        if not isinstance(reference, ArtifactRef) or not cls._artifact_exists(connection, reference):
            raise LedgerIntegrityError(f"artifact parent does not exist: {reference}")

    def _append_transaction_artifacts(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        entries: Sequence[tuple[str, str, Any, Iterable[ArtifactRef]]],
        created: set[ArtifactRef],
        batch_name: str,
    ) -> tuple[ArtifactRevision, ...]:
        """Append validated ordered entries inside an active successor transaction."""

        result: list[ArtifactRevision] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, Sequence) or isinstance(entry, (str, bytes)) or len(entry) != 4:
                raise LedgerIntegrityError(
                    f"{batch_name} artifact batch entry {index} must contain id, kind, payload, and parent_refs"
                )
            artifact_id, kind, payload, raw_parent_refs = entry
            artifact_id = validate_identifier(artifact_id, f"{batch_name} artifact batch entry {index} id")
            if not isinstance(raw_parent_refs, Iterable) or isinstance(raw_parent_refs, (str, bytes)):
                raise LedgerIntegrityError(f"{batch_name} artifact batch entry {index} parent_refs must be iterable")
            parent_refs = tuple(raw_parent_refs)
            for reference in parent_refs:
                if not isinstance(reference, ArtifactRef):
                    raise LedgerIntegrityError(
                        f"{batch_name} artifact batch entry {index} parent_refs must contain ArtifactRef values"
                    )
                if reference not in created:
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
                    (
                        run_id,
                        artifact.id,
                        artifact.revision,
                        reference.round_id,
                        reference.artifact_id,
                        reference.revision,
                    ),
                )
            artifact_ref = ArtifactRef(run_id, artifact.id, artifact.revision)
            self._insert_event(
                connection,
                LineageEvent.create(
                    round_id=run_id,
                    kind="artifact-appended",
                    artifact_ref=artifact_ref,
                ),
            )
            created.add(artifact_ref)
            result.append(artifact)
        return tuple(result)


def _json(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
