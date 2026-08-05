"""Typed Evidence Artifact and Evidence Anchor records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


HASH_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
ANCHOR_KINDS = frozenset({"repository", "document", "image", "input", "experiment", "source", "cas"})
SELECTOR_TYPES = frozenset({"line", "symbol", "fragment", "page_section", "image_region", "input_revision", "experiment_field"})
CONFIDENCES = frozenset({"low", "medium", "high"})


class EvidenceError(ValueError):
    pass


def provenance_group_for(origin: str, acquisition_method: str) -> str:
    """Return a stable provenance group for independence accounting."""

    if not isinstance(origin, str) or not origin.strip() or not isinstance(acquisition_method, str) or not acquisition_method.strip():
        raise EvidenceError("provenance origin and acquisition method are required")
    digest = hashlib.sha256(f"{origin.strip()}\0{acquisition_method.strip()}".encode("utf-8")).hexdigest()
    return f"prov-{digest[:24]}"


@dataclass(frozen=True, slots=True)
class ResolvableEvidenceAnchor:
    """Alpha2 anchor bound to one immutable artifact revision and selector."""

    artifact_digest: str
    artifact_revision: int
    selector_type: str
    selector_value: Mapping[str, Any]
    extractor_version: str
    applicability: str
    confidence: str
    limitations: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ResolvableEvidenceAnchor":
        required = {
            "artifact_digest", "artifact_revision", "selector_type", "selector_value",
            "extractor_version", "applicability", "confidence", "limitations",
        }
        if set(value) != required:
            raise EvidenceError(
                "resolvable evidence anchor fields mismatch; "
                f"missing={sorted(required - set(value))}, extra={sorted(set(value) - required)}"
            )
        digest = value["artifact_digest"]
        if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
            raise EvidenceError("artifact_digest must be SHA-256")
        revision = value["artifact_revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise EvidenceError("artifact_revision must be positive")
        selector_type = value["selector_type"]
        if selector_type not in SELECTOR_TYPES:
            raise EvidenceError("unsupported selector_type")
        selector_value = value["selector_value"]
        if not isinstance(selector_value, Mapping) or not selector_value:
            raise EvidenceError("selector_value must be a nonempty object")
        if not isinstance(value["extractor_version"], str) or not value["extractor_version"].strip():
            raise EvidenceError("extractor_version must be nonempty")
        if not isinstance(value["applicability"], str) or not value["applicability"].strip():
            raise EvidenceError("applicability must be nonempty")
        if value["confidence"] not in CONFIDENCES:
            raise EvidenceError("unsupported evidence confidence")
        limitations = value["limitations"]
        if not isinstance(limitations, list) or not all(isinstance(item, str) and item.strip() for item in limitations):
            raise EvidenceError("limitations must be a string list")
        _validate_selector(selector_type, selector_value)
        return cls(
            digest,
            revision,
            str(selector_type),
            dict(selector_value),
            str(value["extractor_version"]),
            str(value["applicability"]),
            str(value["confidence"]),
            tuple(limitations),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_digest": self.artifact_digest,
            "artifact_revision": self.artifact_revision,
            "selector_type": self.selector_type,
            "selector_value": dict(self.selector_value),
            "extractor_version": self.extractor_version,
            "applicability": self.applicability,
            "confidence": self.confidence,
            "limitations": list(self.limitations),
        }


class EvidenceResolver:
    """Resolve an alpha2 anchor against an exact artifact and optional CAS."""

    def __init__(self, *, cas: Any | None = None, workspace: str | Path | None = None) -> None:
        self.cas = cas
        self.workspace = Path(workspace).resolve() if workspace is not None else None

    def resolve(
        self,
        anchor: Mapping[str, Any] | ResolvableEvidenceAnchor,
        artifact: Mapping[str, Any],
    ) -> dict[str, Any]:
        parsed = anchor if isinstance(anchor, ResolvableEvidenceAnchor) else ResolvableEvidenceAnchor.from_mapping(anchor)
        if not isinstance(artifact, Mapping):
            raise EvidenceError("evidence artifact must be an object")
        if (artifact.get("content_digest") or artifact.get("artifact_digest")) != parsed.artifact_digest:
            raise EvidenceError("evidence anchor digest does not match artifact")
        if int(artifact.get("revision", 1)) != parsed.artifact_revision:
            raise EvidenceError("evidence anchor revision does not match artifact")
        if artifact.get("status") in {"rejected", "quarantined", "superseded"}:
            raise EvidenceError("evidence artifact is not resolvable in its current status")
        if self.cas is not None:
            self.cas.verify(parsed.artifact_digest)
        locator = artifact.get("locator")
        if isinstance(locator, Mapping):
            _validate_locator_scope(locator, workspace=self.workspace)
        return {
            "resolved": True,
            "artifact_digest": parsed.artifact_digest,
            "artifact_revision": parsed.artifact_revision,
            "selector_type": parsed.selector_type,
            "provenance_group": artifact.get("provenance_group"),
        }


def _validate_selector(selector_type: str, value: Mapping[str, Any]) -> None:
    required = {
        "line": {"path", "line"},
        "symbol": {"path", "symbol"},
        "fragment": {"fragment"},
        "page_section": {"page"},
        "image_region": {"x", "y", "width", "height"},
        "input_revision": {"input_id", "revision"},
        "experiment_field": {"run_id", "field"},
    }[selector_type]
    if not required <= set(value):
        raise EvidenceError(f"{selector_type} selector is missing {sorted(required - set(value))}")
    if selector_type in {"line", "page_section", "input_revision"}:
        number = value.get("line", value.get("page", value.get("revision")))
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise EvidenceError(f"{selector_type} selector number must be positive")
    if selector_type == "image_region" and any(
        isinstance(value.get(key), bool) or not isinstance(value.get(key), (int, float)) or value.get(key) < 0
        for key in ("x", "y", "width", "height")
    ):
        raise EvidenceError("image_region selector coordinates must be nonnegative numbers")


def _validate_locator_scope(locator: Mapping[str, Any], *, workspace: Path | None) -> None:
    path = locator.get("path")
    if path is None or workspace is None:
        return
    resolved = (workspace / str(path)).resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise EvidenceError("evidence locator escapes workspace") from exc


@dataclass(frozen=True, slots=True)
class EvidenceAnchor:
    kind: str
    ref: str
    selector: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceAnchor":
        if set(value) != {"kind", "ref", "selector"}:
            raise EvidenceError("EvidenceAnchor requires kind, ref, and selector")
        if value["kind"] not in ANCHOR_KINDS or not isinstance(value["ref"], str) or not value["ref"].strip():
            raise EvidenceError("EvidenceAnchor kind/ref is invalid")
        if not isinstance(value["selector"], Mapping):
            raise EvidenceError("EvidenceAnchor selector must be an object")
        return cls(str(value["kind"]), str(value["ref"]), dict(value["selector"]))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "ref": self.ref, "selector": dict(self.selector)}


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    evidence_id: str
    run_id: str
    artifact_digest: str
    media_type: str
    provenance_group: str
    acquisition: Mapping[str, Any]
    anchors: tuple[EvidenceAnchor, ...]
    status: str = "candidate"

    @classmethod
    def create(cls, evidence_id: str, run_id: str, artifact_digest: str, media_type: str, provenance_group: str, acquisition: Mapping[str, Any], anchors: Sequence[Mapping[str, Any]], status: str = "candidate") -> "EvidenceArtifact":
        if not HASH_RE.fullmatch(artifact_digest):
            raise EvidenceError("artifact_digest must be SHA-256")
        parsed = tuple(EvidenceAnchor.from_mapping(anchor) for anchor in anchors)
        if not parsed:
            raise EvidenceError("EvidenceArtifact requires an EvidenceAnchor")
        if status not in {"candidate", "verified", "active", "superseded", "rejected", "quarantined", "legacy_unverified"}:
            raise EvidenceError("unsupported EvidenceArtifact status")
        return cls(evidence_id, run_id, artifact_digest, media_type, provenance_group, dict(acquisition), parsed, status)

    def ref(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "evidence_id": self.evidence_id, "artifact_digest": self.artifact_digest}

    def to_dict(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "run_id": self.run_id, "artifact_digest": self.artifact_digest, "media_type": self.media_type, "provenance_group": self.provenance_group, "acquisition": dict(self.acquisition), "anchors": [anchor.to_dict() for anchor in self.anchors], "status": self.status}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceArtifact":
        """Parse the canonical alpha2 artifact contract without dropping legacy fields."""

        required = {
            "evidence_id", "run_id", "revision", "media_type", "locator", "content_digest",
            "size_bytes", "acquired_at", "acquisition_method", "provenance_group", "applicability",
            "confidence", "limitations", "status", "extractor_version",
        }
        if set(value) - required - {"source_revision", "license_note", "anchors"}:
            raise EvidenceError("EvidenceArtifact has unexpected fields")
        if not required <= set(value):
            raise EvidenceError(f"EvidenceArtifact is missing {sorted(required - set(value))}")
        for field in ("evidence_id", "run_id", "media_type", "acquisition_method", "provenance_group", "applicability", "extractor_version"):
            if not isinstance(value[field], str) or not value[field].strip():
                raise EvidenceError(f"{field} must be nonempty")
        for field in ("evidence_id", "run_id"):
            if not IDENTIFIER_RE.fullmatch(value[field]):
                raise EvidenceError(f"{field} has an invalid identifier")
        if isinstance(value["revision"], bool) or not isinstance(value["revision"], int) or value["revision"] < 1:
            raise EvidenceError("revision must be positive")
        if isinstance(value["size_bytes"], bool) or not isinstance(value["size_bytes"], int) or value["size_bytes"] < 0:
            raise EvidenceError("size_bytes must be nonnegative")
        if not isinstance(value["acquired_at"], str):
            raise EvidenceError("acquired_at must be ISO-8601")
        try:
            datetime.fromisoformat(value["acquired_at"].replace("Z", "+00:00"))
        except ValueError as error:
            raise EvidenceError("acquired_at must be ISO-8601") from error
        if not HASH_RE.fullmatch(value["content_digest"]):
            raise EvidenceError("content_digest must be SHA-256")
        if not isinstance(value["locator"], Mapping) or not value["locator"]:
            raise EvidenceError("locator must be a nonempty object")
        if value["confidence"] not in CONFIDENCES:
            raise EvidenceError("unsupported evidence confidence")
        if not isinstance(value["limitations"], list) or not all(isinstance(item, str) for item in value["limitations"]):
            raise EvidenceError("limitations must be a string list")
        if value["status"] not in {"active", "superseded", "rejected", "quarantined", "legacy_unverified"}:
            raise EvidenceError("unsupported EvidenceArtifact status")
        anchors = value.get("anchors") or [{
            "kind": "source",
            "ref": str(value["locator"].get("path", value["evidence_id"])),
            "selector": {},
        }]
        # Canonical artifacts are accepted by the resolver as mappings; this object
        # remains the backwards-compatible legacy value object.
        return cls.create(
            evidence_id=value["evidence_id"],
            run_id=value["run_id"],
            artifact_digest=value["content_digest"],
            media_type=value["media_type"],
            provenance_group=value["provenance_group"],
            acquisition={
                "revision": value["revision"],
                "locator": dict(value["locator"]),
                "size_bytes": value["size_bytes"],
                "acquired_at": value["acquired_at"],
                "acquisition_method": value["acquisition_method"],
                "applicability": value["applicability"],
                "confidence": value["confidence"],
                "limitations": list(value["limitations"]),
                "extractor_version": value["extractor_version"],
            },
            anchors=anchors,
            status=value["status"],
        )

    def to_contract_dict(self) -> dict[str, Any]:
        """Return a canonical artifact mapping suitable for EvidenceResolver."""

        acquisition = dict(self.acquisition)
        return {
            "evidence_id": self.evidence_id,
            "run_id": self.run_id,
            "revision": int(acquisition.get("revision", 1)),
            "media_type": self.media_type,
            "locator": dict(acquisition.get("locator", {})),
            "content_digest": self.artifact_digest,
            "size_bytes": int(acquisition.get("size_bytes", 0)),
            "acquired_at": acquisition.get("acquired_at", "1970-01-01T00:00:00Z"),
            "acquisition_method": acquisition.get("acquisition_method", "legacy"),
            "provenance_group": self.provenance_group,
            "applicability": acquisition.get("applicability", "legacy artifact"),
            "confidence": acquisition.get("confidence", "medium"),
            "limitations": list(acquisition.get("limitations", [])),
            "extractor_version": acquisition.get("extractor_version", "legacy"),
            "status": "active" if self.status in {"candidate", "verified"} else self.status,
        }
