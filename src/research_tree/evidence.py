"""Immutable, resolvable evidence artifacts and typed anchors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Mapping

from .content_store import ContentAddressedStore, ContentObject, ContentStoreError
from .domain import ArtifactRef
from .run_ledger import LedgerError, RunLedger


SELECTOR_TYPES = {"line", "symbol", "fragment", "page_section", "image_region", "input_revision", "experiment_field"}
CONFIDENCES = {"low", "medium", "high"}
STATUSES = {"active", "superseded", "rejected", "quarantined", "legacy_unverified"}
EVIDENCE_ARTIFACT_KIND = "evidence-artifact"
EVIDENCE_SCHEMA_VERSION = 1


class EvidenceValidationError(ValueError):
    """Evidence metadata or selector is malformed or cannot be resolved."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _digest(value: object, name: str) -> str:
    value = _text(value, name)
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise EvidenceValidationError(f"{name} must be lowercase SHA-256 hex")
    return value


@dataclass(frozen=True)
class EvidenceArtifact:
    evidence_id: str
    run_id: str
    revision: int
    media_type: str
    locator: Mapping[str, str]
    content_digest: str
    size_bytes: int
    acquired_at: str
    acquisition_method: str
    provenance_group: str
    applicability: str
    confidence: str
    limitations: tuple[str, ...]
    status: str
    extractor_version: str
    source_revision: str | None = None
    license_note: str | None = None
    evidence_class: str = "legacy_unspecified"
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.evidence_id, "evidence_id")
        _text(self.run_id, "run_id")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise EvidenceValidationError("revision must be positive")
        _text(self.media_type, "media_type")
        if not isinstance(self.locator, Mapping) or not self.locator:
            raise EvidenceValidationError("locator must be a non-empty mapping")
        for key, value in self.locator.items():
            _text(key, "locator key")
            _text(value, f"locator[{key}]")
        _digest(self.content_digest, "content_digest")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise EvidenceValidationError("size_bytes must be non-negative")
        try:
            datetime.fromisoformat(self.acquired_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as error:
            raise EvidenceValidationError("acquired_at must be ISO-8601") from error
        _text(self.acquisition_method, "acquisition_method")
        _text(self.provenance_group, "provenance_group")
        _text(self.applicability, "applicability")
        if self.confidence not in CONFIDENCES:
            raise EvidenceValidationError("invalid confidence")
        if not isinstance(self.limitations, tuple) or any(not isinstance(x, str) for x in self.limitations):
            raise EvidenceValidationError("limitations must be a tuple of strings")
        if self.status not in STATUSES:
            raise EvidenceValidationError("invalid status")
        _text(self.extractor_version, "extractor_version")
        if self.source_revision is not None:
            _text(self.source_revision, "source_revision")
        if self.license_note is not None:
            _text(self.license_note, "license_note")
        _text(self.evidence_class, "evidence_class")
        if not isinstance(self.metadata, Mapping):
            raise EvidenceValidationError("metadata must be a mapping")

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical payload stored in an evidence revision."""

        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "evidence_id": self.evidence_id,
            "run_id": self.run_id,
            "revision": self.revision,
            "media_type": self.media_type,
            "locator": dict(self.locator),
            "content_digest": self.content_digest,
            "size_bytes": self.size_bytes,
            "acquired_at": self.acquired_at,
            "acquisition_method": self.acquisition_method,
            "provenance_group": self.provenance_group,
            "applicability": self.applicability,
            "confidence": self.confidence,
            "limitations": list(self.limitations),
            "status": self.status,
            "extractor_version": self.extractor_version,
            "source_revision": self.source_revision,
            "license_note": self.license_note,
            "evidence_class": self.evidence_class,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceArtifact":
        if not isinstance(value, Mapping):
            raise EvidenceValidationError("evidence artifact payload must be a mapping")
        required = {
            "schema_version", "evidence_id", "run_id", "revision", "media_type", "locator",
            "content_digest", "size_bytes", "acquired_at", "acquisition_method",
            "provenance_group", "applicability", "confidence", "limitations", "status",
            "extractor_version", "source_revision", "license_note", "evidence_class", "metadata",
        }
        if set(value) != required or value.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
            raise EvidenceValidationError("unsupported or non-canonical evidence artifact payload")
        limitations = value["limitations"]
        if isinstance(limitations, (str, bytes)) or not isinstance(limitations, (list, tuple)):
            raise EvidenceValidationError("limitations must be a sequence in stored evidence")
        return cls(
            evidence_id=value["evidence_id"],
            run_id=value["run_id"],
            revision=value["revision"],
            media_type=value["media_type"],
            locator=value["locator"],
            content_digest=value["content_digest"],
            size_bytes=value["size_bytes"],
            acquired_at=value["acquired_at"],
            acquisition_method=value["acquisition_method"],
            provenance_group=value["provenance_group"],
            applicability=value["applicability"],
            confidence=value["confidence"],
            limitations=tuple(limitations),
            status=value["status"],
            extractor_version=value["extractor_version"],
            source_revision=value["source_revision"],
            license_note=value["license_note"],
            evidence_class=value["evidence_class"],
            metadata=value["metadata"],
        )

    @classmethod
    def from_revision(cls, reference: ArtifactRef, revision: Any) -> "EvidenceArtifact":
        if not hasattr(revision, "kind") or revision.kind != EVIDENCE_ARTIFACT_KIND:
            raise EvidenceValidationError("artifact ref does not identify an evidence artifact")
        artifact = cls.from_dict(revision.payload)
        if (
            artifact.evidence_id != reference.artifact_id
            or artifact.run_id != reference.round_id
            or artifact.revision != reference.revision
        ):
            raise EvidenceValidationError("evidence identity does not match its ArtifactRef")
        return artifact


@dataclass(frozen=True)
class EvidenceAnchor:
    artifact_digest: str
    artifact_revision: int
    selector_type: str
    selector_value: Mapping[str, object]
    extractor_version: str
    applicability: str
    confidence: str
    limitations: tuple[str, ...]
    artifact_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        _digest(self.artifact_digest, "artifact_digest")
        if isinstance(self.artifact_revision, bool) or not isinstance(self.artifact_revision, int) or self.artifact_revision < 1:
            raise EvidenceValidationError("artifact_revision must be positive")
        if self.selector_type not in SELECTOR_TYPES:
            raise EvidenceValidationError(f"unsupported selector_type: {self.selector_type}")
        if not isinstance(self.selector_value, Mapping):
            raise EvidenceValidationError("selector_value must be a mapping")
        _validate_selector(self.selector_type, self.selector_value)
        _text(self.extractor_version, "extractor_version")
        _text(self.applicability, "applicability")
        if self.confidence not in CONFIDENCES:
            raise EvidenceValidationError("invalid confidence")
        if not isinstance(self.limitations, tuple) or any(not isinstance(x, str) for x in self.limitations):
            raise EvidenceValidationError("limitations must be a tuple of strings")
        if self.artifact_ref is not None:
            if not isinstance(self.artifact_ref, ArtifactRef):
                raise EvidenceValidationError("artifact_ref must be an ArtifactRef")
            if self.artifact_ref.revision != self.artifact_revision:
                raise EvidenceValidationError("artifact_ref revision does not match artifact_revision")

    @property
    def is_strict(self) -> bool:
        return self.artifact_ref is not None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "artifact_digest": self.artifact_digest,
            "artifact_revision": self.artifact_revision,
            "selector_type": self.selector_type,
            "selector_value": dict(self.selector_value),
            "extractor_version": self.extractor_version,
            "applicability": self.applicability,
            "confidence": self.confidence,
            "limitations": list(self.limitations),
        }
        if self.artifact_ref is None:
            payload["legacy_unverified"] = True
        else:
            payload["artifact_ref"] = self.artifact_ref.to_dict()
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, allow_legacy: bool = False) -> "EvidenceAnchor":
        if not isinstance(value, Mapping):
            raise EvidenceValidationError("evidence anchor must be a mapping")
        common = {
            "artifact_digest", "artifact_revision", "selector_type", "selector_value",
            "extractor_version", "applicability", "confidence", "limitations",
        }
        keys = set(value)
        if keys == common | {"artifact_ref"}:
            artifact_ref = ArtifactRef.from_dict(value["artifact_ref"])
        elif keys == common | {"legacy_unverified"} and value["legacy_unverified"] is True:
            if not allow_legacy:
                raise EvidenceValidationError("legacy anchor requires an explicit compatibility reader")
            artifact_ref = None
        else:
            raise EvidenceValidationError("evidence anchor has unexpected fields")
        limitations = value["limitations"]
        if isinstance(limitations, (str, bytes)) or not isinstance(limitations, (list, tuple)):
            raise EvidenceValidationError("anchor limitations must be a sequence")
        return cls(
            artifact_ref=artifact_ref,
            artifact_digest=value["artifact_digest"],
            artifact_revision=value["artifact_revision"],
            selector_type=value["selector_type"],
            selector_value=value["selector_value"],
            extractor_version=value["extractor_version"],
            applicability=value["applicability"],
            confidence=value["confidence"],
            limitations=tuple(limitations),
        )


def _positive(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EvidenceValidationError(f"{name} must be a positive integer")


def _nonnegative(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceValidationError(f"{name} must be a non-negative integer")


def _validate_selector(kind: str, value: Mapping[str, object]) -> None:
    if kind == "line":
        _positive(value.get("start"), "line.start")
        _positive(value.get("end"), "line.end")
        if value["end"] < value["start"]:
            raise EvidenceValidationError("line.end precedes start")
    elif kind == "symbol":
        _text(value.get("name"), "symbol.name")
    elif kind == "fragment":
        _nonnegative(value.get("start"), "fragment.start")
        _positive(value.get("length", value.get("end", 0)), "fragment.length")
    elif kind == "page_section":
        _positive(value.get("page"), "page_section.page")
        _text(value.get("section"), "page_section.section")
    elif kind == "image_region":
        for field in ("x", "y"):
            _nonnegative(value.get(field), f"image_region.{field}")
        for field in ("width", "height"):
            _positive(value.get(field), f"image_region.{field}")
    elif kind == "input_revision":
        _positive(value.get("revision"), "input_revision.revision")
    elif kind == "experiment_field":
        _text(value.get("field"), "experiment_field.field")


def provenance_group_for(locator: str, explicit: str | None = None) -> str:
    """Normalize same-origin URLs and their derivatives into one provenance group."""
    if explicit:
        return _text(explicit, "provenance_group")
    parsed = urlsplit(_text(locator, "locator"))
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    return sha256(locator.encode("utf-8")).hexdigest()[:16]


class EvidenceResolver:
    def __init__(
        self,
        store: ContentAddressedStore,
        artifacts: Mapping[str, EvidenceArtifact],
        *,
        workspace: str | Path | None = None,
        repository_revisions: Mapping[str, str] | None = None,
    ) -> None:
        self.store = store
        self.artifacts = dict(artifacts)
        self.workspace = Path(workspace or store.workspace).resolve()
        self.repository_revisions = dict(repository_revisions or {})

    def resolve(self, anchor: EvidenceAnchor):
        artifact = self.artifacts.get(anchor.artifact_digest)
        if artifact is None or artifact.revision != anchor.artifact_revision:
            raise EvidenceValidationError("anchor does not reference an exact artifact revision")
        if artifact.status != "active":
            raise EvidenceValidationError("anchor references inactive evidence")
        if artifact.extractor_version != anchor.extractor_version:
            raise EvidenceValidationError("extractor version mismatch")
        locator_path = artifact.locator.get("path") if isinstance(artifact.locator, Mapping) else None
        if locator_path:
            path = (self.workspace / locator_path).resolve()
            try:
                path.relative_to(self.workspace)
            except ValueError as error:
                raise EvidenceValidationError("repository locator escapes workspace") from error
            expected_revision = self.repository_revisions.get(locator_path)
            if expected_revision is not None and artifact.source_revision != expected_revision:
                raise EvidenceValidationError("repository anchor does not bind inspected revision")
        try:
            data = self.store.read(artifact.content_digest)
        except (ContentStoreError, OSError) as error:
            raise EvidenceValidationError("evidence content is missing or changed") from error
        if len(data) != artifact.size_bytes or sha256(data).hexdigest() != artifact.content_digest:
            raise EvidenceValidationError("evidence content integrity check failed")
        return type("ResolvedEvidence", (), {"digest": artifact.content_digest, "bytes": data})()


class EvidenceRepository:
    """Publish canonical evidence through the atomic RunLedger boundary."""

    def __init__(self, ledger: RunLedger, store: ContentAddressedStore) -> None:
        if not isinstance(ledger, RunLedger):
            raise EvidenceValidationError("EvidenceRepository requires a RunLedger")
        if not isinstance(store, ContentAddressedStore):
            raise EvidenceValidationError("EvidenceRepository requires a ContentAddressedStore")
        self.ledger = ledger
        self.store = store

    def record(
        self,
        artifact: EvidenceArtifact,
        content: ContentObject,
        *,
        expected_run_revision: int,
        parent_refs: tuple[ArtifactRef, ...] = (),
    ) -> ArtifactRef:
        if not isinstance(artifact, EvidenceArtifact):
            raise EvidenceValidationError("artifact must be an EvidenceArtifact")
        if not isinstance(content, ContentObject):
            raise EvidenceValidationError("content must be a ContentObject")
        if artifact.evidence_class == "legacy_unspecified":
            raise EvidenceValidationError("evidence_class must be explicit")
        if (
            artifact.content_digest != content.digest
            or artifact.size_bytes != content.byte_size
            or artifact.media_type != content.media_type
        ):
            raise EvidenceValidationError("evidence metadata does not match CAS content")
        try:
            revision = self.ledger.append_artifact_with_content(
                artifact.run_id,
                artifact.evidence_id,
                EVIDENCE_ARTIFACT_KIND,
                artifact.to_dict(),
                content,
                self.store,
                parent_refs=parent_refs,
                expected_revision=expected_run_revision,
                expected_artifact_revision=artifact.revision,
            )
        except (ContentStoreError, OSError, LedgerError) as error:
            raise EvidenceValidationError("evidence persistence failed") from error
        return ArtifactRef(revision.round_id, revision.id, revision.revision)
