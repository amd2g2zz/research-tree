"""Immutable records and validation at the run-store boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, TypeAlias, cast
from uuid import uuid4


SCHEMA_VERSION = 1
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")

JsonValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | tuple["JsonValue", ...]
    | Mapping[str, "JsonValue"]
)


class RuntimeStoreError(Exception):
    """Base error for an expected run-store boundary failure."""


class InvalidIdentifierError(RuntimeStoreError):
    """Raised when an identifier is not safe to use as a storage component."""


class InvalidPayloadError(RuntimeStoreError):
    """Raised when a payload cannot be represented as canonical JSON."""


class DataIntegrityError(RuntimeStoreError):
    """Raised when persisted data is malformed or does not match its digest."""


class RoundAlreadyExistsError(RuntimeStoreError):
    """Raised when a new round would overwrite an existing round."""


class RoundNotFoundError(RuntimeStoreError):
    """Raised when a requested round does not exist in this store."""


class ArtifactNotFoundError(RuntimeStoreError):
    """Raised when an exact parent artifact revision cannot be resolved."""


def utc_now() -> str:
    """Return a timezone-aware timestamp suitable for lexical event ordering."""

    return datetime.now(timezone.utc).isoformat()


def validate_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        raise InvalidIdentifierError(
            f"{label} must match {IDENTIFIER_PATTERN.pattern!r}; got {value!r}"
        )
    return value


def validate_timestamp(value: str, label: str = "created_at") -> str:
    if not isinstance(value, str):
        raise DataIntegrityError(f"{label} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DataIntegrityError(f"{label} is not a valid ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise DataIntegrityError(f"{label} must include a timezone")
    return value


def freeze_json(value: Any) -> JsonValue:
    """Create a recursively immutable representation of a JSON value."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidPayloadError("JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, JsonValue] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise InvalidPayloadError("JSON object keys must be strings")
            frozen[key] = freeze_json(child)
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(freeze_json(child) for child in value)
    raise InvalidPayloadError(f"value is not JSON-compatible: {type(value).__name__}")


def freeze_payload(payload: Any) -> Mapping[str, JsonValue]:
    frozen = freeze_json(payload)
    if not isinstance(frozen, Mapping):
        raise InvalidPayloadError("artifact payload must be a JSON object")
    return frozen


def thaw_json(value: JsonValue) -> Any:
    """Return an ordinary JSON-compatible value without exposing stored state."""

    if isinstance(value, Mapping):
        return {key: thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(child) for child in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise InvalidPayloadError("value cannot be canonically serialized as JSON") from error
    return encoded.encode("utf-8")


def _require_object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DataIntegrityError(f"{label} must be a JSON object")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value.keys())
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise DataIntegrityError(f"{label} has unexpected keys; missing={missing}, extra={extra}")


def _require_schema_version(value: Any, label: str) -> int:
    if value != SCHEMA_VERSION:
        raise DataIntegrityError(
            f"{label} schema_version must be {SCHEMA_VERSION}; got {value!r}"
        )
    return SCHEMA_VERSION


def _require_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DataIntegrityError(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """An exact immutable artifact revision in a run store."""

    round_id: str
    artifact_id: str
    revision: int

    def __post_init__(self) -> None:
        validate_identifier(self.round_id, "round_id")
        validate_identifier(self.artifact_id, "artifact_id")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise DataIntegrityError("artifact revision must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "artifact_id": self.artifact_id,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ArtifactRef":
        data = _require_object(value, "artifact reference")
        _require_exact_keys(data, {"round_id", "artifact_id", "revision"}, "artifact reference")
        return cls(
            round_id=validate_identifier(data["round_id"], "round_id"),
            artifact_id=validate_identifier(data["artifact_id"], "artifact_id"),
            revision=_require_positive_int(data["revision"], "revision"),
        )


@dataclass(frozen=True, slots=True)
class RoundRecord:
    """The immutable record created once for a research round."""

    id: str
    created_at: str
    parent_round_id: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_identifier(self.id, "round_id")
        validate_timestamp(self.created_at)
        if self.parent_round_id is not None:
            validate_identifier(self.parent_round_id, "parent_round_id")
        _require_schema_version(self.schema_version, "round record")

    @classmethod
    def create(cls, round_id: str, parent_round_id: str | None = None) -> "RoundRecord":
        return cls(id=round_id, created_at=utc_now(), parent_round_id=parent_round_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "created_at": self.created_at,
            "parent_round_id": self.parent_round_id,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "RoundRecord":
        data = _require_object(value, "round record")
        _require_exact_keys(
            data,
            {"schema_version", "id", "created_at", "parent_round_id"},
            "round record",
        )
        _require_schema_version(data["schema_version"], "round record")
        parent_round_id = data["parent_round_id"]
        if parent_round_id is not None:
            validate_identifier(parent_round_id, "parent_round_id")
        return cls(
            id=validate_identifier(data["id"], "round_id"),
            created_at=validate_timestamp(data["created_at"]),
            parent_round_id=parent_round_id,
        )


@dataclass(frozen=True, slots=True)
class ArtifactRevision:
    """A content-addressed, immutable version of a generic contract artifact."""

    id: str
    round_id: str
    revision: int
    kind: str
    created_at: str
    payload: Mapping[str, JsonValue]
    parent_refs: tuple[ArtifactRef, ...]
    content_hash: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_identifier(self.id, "artifact_id")
        validate_identifier(self.round_id, "round_id")
        _require_positive_int(self.revision, "revision")
        validate_identifier(self.kind, "artifact kind")
        validate_timestamp(self.created_at)
        if not isinstance(self.payload, Mapping):
            raise InvalidPayloadError("artifact payload must be a JSON object")
        if not isinstance(self.parent_refs, tuple) or not all(
            isinstance(reference, ArtifactRef) for reference in self.parent_refs
        ):
            raise DataIntegrityError("parent_refs must be a tuple of artifact references")
        if not isinstance(self.content_hash, str) or not HASH_PATTERN.fullmatch(self.content_hash):
            raise DataIntegrityError("content_hash must be a SHA-256 hex digest")
        _require_schema_version(self.schema_version, "artifact revision")

    @classmethod
    def create(
        cls,
        *,
        artifact_id: str,
        round_id: str,
        revision: int,
        kind: str,
        payload: Any,
        parent_refs: tuple[ArtifactRef, ...],
    ) -> "ArtifactRevision":
        frozen_payload = freeze_payload(payload)
        created_at = utc_now()
        body = {
            "schema_version": SCHEMA_VERSION,
            "id": artifact_id,
            "round_id": round_id,
            "revision": revision,
            "kind": kind,
            "created_at": created_at,
            "payload": thaw_json(frozen_payload),
            "parent_refs": [reference.to_dict() for reference in parent_refs],
        }
        content_hash = sha256(canonical_json_bytes(body)).hexdigest()
        return cls(
            id=artifact_id,
            round_id=round_id,
            revision=revision,
            kind=kind,
            created_at=created_at,
            payload=frozen_payload,
            parent_refs=parent_refs,
            content_hash=content_hash,
        )

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "round_id": self.round_id,
            "revision": self.revision,
            "kind": self.kind,
            "created_at": self.created_at,
            "payload": thaw_json(self.payload),
            "parent_refs": [reference.to_dict() for reference in self.parent_refs],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_hash": self.content_hash}

    @classmethod
    def from_dict(cls, value: Any) -> "ArtifactRevision":
        data = _require_object(value, "artifact revision")
        _require_exact_keys(
            data,
            {
                "schema_version",
                "id",
                "round_id",
                "revision",
                "kind",
                "created_at",
                "payload",
                "parent_refs",
                "content_hash",
            },
            "artifact revision",
        )
        _require_schema_version(data["schema_version"], "artifact revision")
        parent_refs_raw = data["parent_refs"]
        if not isinstance(parent_refs_raw, list):
            raise DataIntegrityError("parent_refs must be a JSON array")
        revision = cls(
            id=validate_identifier(data["id"], "artifact_id"),
            round_id=validate_identifier(data["round_id"], "round_id"),
            revision=_require_positive_int(data["revision"], "revision"),
            kind=validate_identifier(data["kind"], "artifact kind"),
            created_at=validate_timestamp(data["created_at"]),
            payload=freeze_payload(data["payload"]),
            parent_refs=tuple(ArtifactRef.from_dict(reference) for reference in parent_refs_raw),
            content_hash=data["content_hash"],
        )
        expected_hash = sha256(canonical_json_bytes(revision.content_dict())).hexdigest()
        if revision.content_hash != expected_hash:
            raise DataIntegrityError("artifact revision content_hash does not match its content")
        return revision


@dataclass(frozen=True, slots=True)
class LineageEvent:
    """An append-only record of how a round or artifact entered the store."""

    id: str
    round_id: str
    kind: str
    created_at: str
    artifact_ref: ArtifactRef | None = None
    parent_round_id: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_identifier(self.id, "event_id")
        validate_identifier(self.round_id, "round_id")
        validate_identifier(self.kind, "event kind")
        validate_timestamp(self.created_at)
        if self.parent_round_id is not None:
            validate_identifier(self.parent_round_id, "parent_round_id")
        _require_schema_version(self.schema_version, "lineage event")

    @classmethod
    def create(
        cls,
        *,
        round_id: str,
        kind: str,
        artifact_ref: ArtifactRef | None = None,
        parent_round_id: str | None = None,
    ) -> "LineageEvent":
        return cls(
            id=f"event-{uuid4().hex}",
            round_id=round_id,
            kind=kind,
            created_at=utc_now(),
            artifact_ref=artifact_ref,
            parent_round_id=parent_round_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "round_id": self.round_id,
            "kind": self.kind,
            "created_at": self.created_at,
            "artifact_ref": None if self.artifact_ref is None else self.artifact_ref.to_dict(),
            "parent_round_id": self.parent_round_id,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "LineageEvent":
        data = _require_object(value, "lineage event")
        _require_exact_keys(
            data,
            {
                "schema_version",
                "id",
                "round_id",
                "kind",
                "created_at",
                "artifact_ref",
                "parent_round_id",
            },
            "lineage event",
        )
        _require_schema_version(data["schema_version"], "lineage event")
        artifact_ref_raw = data["artifact_ref"]
        parent_round_id = data["parent_round_id"]
        if parent_round_id is not None:
            validate_identifier(parent_round_id, "parent_round_id")
        return cls(
            id=validate_identifier(data["id"], "event_id"),
            round_id=validate_identifier(data["round_id"], "round_id"),
            kind=validate_identifier(data["kind"], "event kind"),
            created_at=validate_timestamp(data["created_at"]),
            artifact_ref=(
                None
                if artifact_ref_raw is None
                else ArtifactRef.from_dict(artifact_ref_raw)
            ),
            parent_round_id=parent_round_id,
        )


@dataclass(frozen=True, slots=True)
class RoundSnapshot:
    """A reconstructed projection of immutable files for one round."""

    record: RoundRecord
    artifacts: tuple[ArtifactRevision, ...]
    lineage_events: tuple[LineageEvent, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record": self.record.to_dict(),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "lineage_events": [event.to_dict() for event in self.lineage_events],
        }
