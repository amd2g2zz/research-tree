"""Typed Evidence Artifact and Evidence Anchor records."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


HASH_RE = re.compile(r"^[0-9a-f]{64}$")
ANCHOR_KINDS = frozenset({"repository", "document", "image", "input", "experiment", "source", "cas"})


class EvidenceError(ValueError):
    pass


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
        if status not in {"candidate", "verified", "superseded", "rejected"}:
            raise EvidenceError("unsupported EvidenceArtifact status")
        return cls(evidence_id, run_id, artifact_digest, media_type, provenance_group, dict(acquisition), parsed, status)

    def ref(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "evidence_id": self.evidence_id, "artifact_digest": self.artifact_digest}

    def to_dict(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "run_id": self.run_id, "artifact_digest": self.artifact_digest, "media_type": self.media_type, "provenance_group": self.provenance_group, "acquisition": dict(self.acquisition), "anchors": [anchor.to_dict() for anchor in self.anchors], "status": self.status}
