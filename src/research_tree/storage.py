"""Filesystem-backed immutable storage for independent research rounds."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable
from uuid import uuid4

from .domain import (
    ArtifactNotFoundError,
    ArtifactRef,
    ArtifactRevision,
    DataIntegrityError,
    LineageEvent,
    RoundAlreadyExistsError,
    RoundNotFoundError,
    RoundRecord,
    RoundSnapshot,
    canonical_json_bytes,
    validate_identifier,
)


class RunStore:
    """An explicit root for isolated, replayable research-round state."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve(strict=False)

    @property
    def root(self) -> Path:
        return self._root

    def create_round(
        self,
        round_id: str | None = None,
        *,
        parent_round_id: str | None = None,
    ) -> RoundRecord:
        selected_round_id = round_id or f"round-{uuid4().hex}"
        validate_identifier(selected_round_id, "round_id")
        if parent_round_id is not None:
            self.load_round(parent_round_id)

        round_dir = self._round_dir(selected_round_id)
        try:
            round_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise RoundAlreadyExistsError(f"round already exists: {selected_round_id}") from error

        record = RoundRecord.create(selected_round_id, parent_round_id)
        self._write_new_json(round_dir / "round.json", record.to_dict())
        self._write_event(
            round_dir,
            LineageEvent.create(
                round_id=selected_round_id,
                kind="round-created",
                parent_round_id=parent_round_id,
            ),
        )
        return record

    def append_artifact(
        self,
        round_id: str,
        artifact_id: str,
        kind: str,
        payload: Any,
        *,
        parent_refs: Iterable[ArtifactRef] = (),
    ) -> ArtifactRevision:
        record = self._load_round_record(round_id)
        validate_identifier(artifact_id, "artifact_id")
        validate_identifier(kind, "artifact kind")
        references = tuple(parent_refs)
        for reference in references:
            if not isinstance(reference, ArtifactRef):
                raise DataIntegrityError("parent_refs must contain ArtifactRef values")
            self._load_artifact(reference)

        artifact_dir = self._artifact_dir(record.id, artifact_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        while True:
            revision_number = self._next_revision(artifact_dir)
            revision = ArtifactRevision.create(
                artifact_id=artifact_id,
                round_id=record.id,
                revision=revision_number,
                kind=kind,
                payload=payload,
                parent_refs=references,
            )
            destination = artifact_dir / self._revision_filename(revision_number)
            try:
                self._write_new_json(destination, revision.to_dict())
            except FileExistsError:
                continue
            break

        self._write_event(
            self._round_dir(record.id),
            LineageEvent.create(
                round_id=record.id,
                kind="artifact-appended",
                artifact_ref=ArtifactRef(record.id, artifact_id, revision_number),
            ),
        )
        return revision

    def load_round(self, round_id: str) -> RoundSnapshot:
        record = self._load_round_record(round_id)
        round_dir = self._round_dir(record.id)
        artifacts = self._load_artifacts(round_dir, record.id)
        events = self._load_events(round_dir, record.id)
        self._validate_loaded_lineage(artifacts, events)
        return RoundSnapshot(
            record=record,
            artifacts=tuple(sorted(artifacts, key=lambda artifact: (artifact.id, artifact.revision))),
            lineage_events=tuple(sorted(events, key=lambda event: (event.created_at, event.id))),
        )

    def _round_dir(self, round_id: str) -> Path:
        return self._root / "rounds" / validate_identifier(round_id, "round_id")

    def _artifact_dir(self, round_id: str, artifact_id: str) -> Path:
        return self._round_dir(round_id) / "artifacts" / validate_identifier(
            artifact_id, "artifact_id"
        )

    def _load_round_record(self, round_id: str) -> RoundRecord:
        round_dir = self._round_dir(round_id)
        record_path = round_dir / "round.json"
        if not record_path.is_file():
            raise RoundNotFoundError(f"round does not exist: {round_id}")
        record = RoundRecord.from_dict(self._read_json(record_path))
        if record.id != round_id:
            raise DataIntegrityError("round.json id does not match its directory")
        return record

    def _load_artifact(self, reference: ArtifactRef) -> ArtifactRevision:
        self._load_round_record(reference.round_id)
        artifact_path = (
            self._artifact_dir(reference.round_id, reference.artifact_id)
            / self._revision_filename(reference.revision)
        )
        if not artifact_path.is_file():
            raise ArtifactNotFoundError(
                "artifact revision does not exist: "
                f"{reference.round_id}/{reference.artifact_id}@{reference.revision}"
            )
        artifact = ArtifactRevision.from_dict(self._read_json(artifact_path))
        if (
            artifact.round_id != reference.round_id
            or artifact.id != reference.artifact_id
            or artifact.revision != reference.revision
        ):
            raise DataIntegrityError("artifact content does not match its storage path")
        return artifact

    def _load_artifacts(self, round_dir: Path, round_id: str) -> list[ArtifactRevision]:
        artifacts_root = round_dir / "artifacts"
        if not artifacts_root.exists():
            return []
        if not artifacts_root.is_dir():
            raise DataIntegrityError("artifacts path is not a directory")

        artifacts: list[ArtifactRevision] = []
        for artifact_dir in sorted(artifacts_root.iterdir(), key=lambda path: path.name):
            if not artifact_dir.is_dir():
                raise DataIntegrityError("artifact directory contains a non-directory entry")
            artifact_id = validate_identifier(artifact_dir.name, "artifact_id")
            for artifact_path in sorted(artifact_dir.glob("*.json"), key=lambda path: path.name):
                try:
                    revision = int(artifact_path.stem)
                except ValueError as error:
                    raise DataIntegrityError("artifact filename must be a numeric revision") from error
                artifact = self._load_artifact(ArtifactRef(round_id, artifact_id, revision))
                artifacts.append(artifact)
        return artifacts

    def _load_events(self, round_dir: Path, round_id: str) -> list[LineageEvent]:
        events_root = round_dir / "events"
        if not events_root.exists():
            return []
        if not events_root.is_dir():
            raise DataIntegrityError("events path is not a directory")

        events: list[LineageEvent] = []
        for event_path in sorted(events_root.glob("*.json"), key=lambda path: path.name):
            event = LineageEvent.from_dict(self._read_json(event_path))
            if event.round_id != round_id or event.id != event_path.stem:
                raise DataIntegrityError("lineage event does not match its storage path")
            events.append(event)
        return events

    def _validate_loaded_lineage(
        self, artifacts: Iterable[ArtifactRevision], events: Iterable[LineageEvent]
    ) -> None:
        for artifact in artifacts:
            for reference in artifact.parent_refs:
                self._require_stored_reference(reference)
        for event in events:
            if event.kind == "artifact-appended" and event.artifact_ref is not None:
                self._require_stored_reference(event.artifact_ref)

    def _require_stored_reference(self, reference: ArtifactRef) -> None:
        try:
            self._load_artifact(reference)
        except (ArtifactNotFoundError, RoundNotFoundError) as error:
            raise DataIntegrityError(
                "stored lineage reference does not resolve: "
                f"{reference.round_id}/{reference.artifact_id}@{reference.revision}"
            ) from error

    @staticmethod
    def _next_revision(artifact_dir: Path) -> int:
        revisions: list[int] = []
        for path in artifact_dir.glob("*.json"):
            try:
                revisions.append(int(path.stem))
            except ValueError as error:
                raise DataIntegrityError("artifact filename must be a numeric revision") from error
        return max(revisions, default=0) + 1

    @staticmethod
    def _revision_filename(revision: int) -> str:
        return f"{revision:06d}.json"

    def _write_event(self, round_dir: Path, event: LineageEvent) -> None:
        destination = round_dir / "events" / f"{event.id}.json"
        self._write_new_json(destination, event.to_dict())

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            raw = path.read_bytes()
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DataIntegrityError(f"cannot read valid JSON from {path}") from error
        if not isinstance(value, dict):
            raise DataIntegrityError(f"stored JSON must be an object: {path}")
        return value

    @staticmethod
    def _write_new_json(path: Path, value: dict[str, Any]) -> None:
        """Write a new immutable file without allowing an overwrite race."""

        payload = canonical_json_bytes(value)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        try:
            with temporary_path.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary_path, path)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
