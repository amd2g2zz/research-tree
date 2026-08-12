"""Transactional SQLite ledger for the Alpha2 canonical run lineage."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sqlite3
from typing import Any, Iterable, Sequence

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
from .content_store import ContentAddressedStore, ContentObject
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .legacy_import import LegacyImportReceipt


class LedgerError(Exception):
    """Base class for expected ledger boundary failures."""


class LedgerConflictError(LedgerError):
    """Raised when a write uses an obsolete run revision."""


class LedgerIntegrityError(LedgerError, DataIntegrityError):
    """Raised when a persisted row or lineage reference is invalid."""


class RunLedger:
    """Own canonical run lineage in a workspace-scoped SQLite database."""

    SCHEMA_VERSION = 5

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
                CREATE TABLE IF NOT EXISTS legacy_imports (
                    source_digest TEXT PRIMARY KEY,
                    source_locator TEXT NOT NULL,
                    run_id TEXT,
                    disposition TEXT NOT NULL,
                    detail_json BLOB NOT NULL,
                    created_at TEXT NOT NULL
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
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, datetime('now'))",
                (self.SCHEMA_VERSION,),
            )

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

    def record_import_receipt(self, receipt: "LegacyImportReceipt") -> "LegacyImportReceipt":
        self.initialize()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT source_locator, run_id, disposition, detail_json, created_at "
                "FROM legacy_imports WHERE source_digest = ?",
                (receipt.source_digest,),
            ).fetchone()
            if existing is not None:
                return _legacy_import_receipt(receipt.source_digest, *tuple(existing))
            connection.execute(
                "INSERT INTO legacy_imports(source_digest, source_locator, run_id, disposition, detail_json, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (
                    receipt.source_digest,
                    receipt.source_locator,
                    receipt.run_id,
                    receipt.disposition,
                    receipt.detail_json,
                    receipt.created_at,
                ),
            )
        return receipt

    def get_import_receipt(self, source_digest: str) -> "LegacyImportReceipt | None":
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT source_digest, source_locator, run_id, disposition, detail_json, created_at "
                "FROM legacy_imports WHERE source_digest = ?",
                (source_digest,),
            ).fetchone()
        return None if row is None else _legacy_import_receipt(*tuple(row))

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

    @classmethod
    def _require_artifact(cls, connection: sqlite3.Connection, reference: ArtifactRef) -> None:
        if not isinstance(reference, ArtifactRef) or not cls._artifact_exists(connection, reference):
            raise LedgerIntegrityError(f"artifact parent does not exist: {reference}")


def _json(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _legacy_import_receipt(*values: Any) -> "LegacyImportReceipt":
    # Imported lazily to keep the importer dependent on the ledger, not vice versa.
    from .legacy_import import LegacyImportReceipt

    return LegacyImportReceipt(*values)
