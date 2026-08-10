"""Immutable, resolvable evidence artifacts and typed anchors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
from typing import Mapping

from .content_store import ContentAddressedStore, ContentStoreError


SELECTOR_TYPES = {"line", "symbol", "fragment", "page_section", "image_region", "input_revision", "experiment_field"}
CONFIDENCES = {"low", "medium", "high"}
STATUSES = {"active", "superseded", "rejected", "quarantined", "legacy_unverified"}


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

    def __post_init__(self) -> None:
        _text(self.evidence_id, "evidence_id")
        _text(self.run_id, "run_id")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise EvidenceValidationError("revision must be positive")
        _text(self.media_type, "media_type")
        if not isinstance(self.locator, Mapping) or not self.locator:
            raise EvidenceValidationError("locator must be a non-empty mapping")
        _digest(self.content_digest, "content_digest")
        if isinstance(self.size_bytes, bool) or self.size_bytes < 0:
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

    def __post_init__(self) -> None:
        _digest(self.artifact_digest, "artifact_digest")
        if isinstance(self.artifact_revision, bool) or self.artifact_revision < 1:
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
