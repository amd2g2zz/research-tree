"""Claim-level grounding and provenance admission.

Capture integrity is necessary but does not establish that a normalized claim
is supported or independently corroborated.  This module keeps that admission
decision deterministic and separate from worker-reported confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from .domain import ArtifactRef

if TYPE_CHECKING:
    from .evidence import EvidenceResolver


class ClaimValidationError(ValueError):
    """Raised when a claim-admission value is malformed."""


class ClaimState(StrEnum):
    CANDIDATE = "candidate"
    ISOLATED = "isolated"
    CORROBORATED = "corroborated"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    CONTESTED = "contested"


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClaimValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _texts(value: Iterable[str], field: str) -> tuple[str, ...]:
    result = tuple(_text(item, f"{field} item") for item in value)
    if len(set(result)) != len(result):
        raise ClaimValidationError(f"{field} must not contain duplicates")
    return result


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


@dataclass(frozen=True, slots=True)
class Claim:
    """An atomic externally grounded assertion with its applicable scope."""

    claim_id: str
    subject: str
    predicate: str
    value: str
    polarity: str
    scope: str
    version: str
    time_range: str
    conditions: tuple[str, ...] = ()
    platform: str = "unspecified"
    modality: str = "unspecified"

    def __post_init__(self) -> None:
        for field in (
            "claim_id",
            "subject",
            "predicate",
            "value",
            "scope",
            "version",
            "time_range",
            "platform",
            "modality",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        if self.polarity not in {"positive", "negative"}:
            raise ClaimValidationError("polarity must be positive or negative")
        object.__setattr__(self, "conditions", _texts(self.conditions, "conditions"))

    @property
    def normalized_statement(self) -> str:
        return _normalized(f"{self.subject} {self.predicate} {self.value}")


@dataclass(frozen=True, slots=True)
class ProvenanceDescriptor:
    """Resolved upstream identity used for true provenance clustering."""

    upstream_id: str | None = None
    owner_id: str | None = None
    dataset_id: str | None = None
    content_fingerprint: str | None = None

    def __post_init__(self) -> None:
        values = (self.upstream_id, self.owner_id, self.dataset_id, self.content_fingerprint)
        if not any(values):
            raise ClaimValidationError("provenance descriptor requires a resolved identity")
        for field in ("upstream_id", "owner_id", "dataset_id", "content_fingerprint"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _text(value, field))

    @property
    def cluster_id(self) -> str:
        for value in (self.upstream_id, self.dataset_id, self.content_fingerprint, self.owner_id):
            if value is not None:
                return value
        raise AssertionError("validated descriptor has a cluster identity")

    @property
    def identities(self) -> frozenset[str]:
        """All independently resolved clustering keys for union-find grouping."""

        return frozenset(
            f"{name}:{value}"
            for name, value in (
                ("upstream", self.upstream_id),
                ("dataset", self.dataset_id),
                ("content", self.content_fingerprint),
            )
            if value is not None
        )


@dataclass(frozen=True, slots=True)
class ClaimGrounding:
    """A claim binding to one exact canonical evidence selector.

    Source wording, scope and provenance are intentionally not caller-owned
    fields.  ``ClaimAdmissionEvaluator`` derives them from the resolved
    ``EvidenceAnchor`` and its immutable evidence artifact.
    """

    grounding_id: str
    claim_id: str
    anchor: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field in ("grounding_id", "claim_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        try:
            from .evidence import EvidenceAnchor

            typed = EvidenceAnchor.from_dict(self.anchor)
        except (TypeError, ValueError) as error:
            raise ClaimValidationError(f"anchor must be a canonical EvidenceAnchor: {error}") from error
        object.__setattr__(self, "anchor", typed.to_dict())


@dataclass(frozen=True, slots=True)
class ClaimAssessment:
    """Derived admission decision; non-corroborated states have no authority."""

    claim_id: str
    state: ClaimState
    provenance_clusters: tuple[str, ...]
    grounding_ids: tuple[str, ...]
    grounding_refs: tuple[ArtifactRef, ...] = ()
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _text(self.claim_id, "claim_id"))
        if not isinstance(self.state, ClaimState):
            raise ClaimValidationError("state must be a ClaimState")
        object.__setattr__(self, "provenance_clusters", _texts(self.provenance_clusters, "provenance_clusters"))
        object.__setattr__(self, "grounding_ids", _texts(self.grounding_ids, "grounding_ids"))
        if any(not isinstance(reference, ArtifactRef) for reference in self.grounding_refs):
            raise ClaimValidationError("grounding_refs must contain ArtifactRef values")
        object.__setattr__(self, "rejection_reasons", _texts(self.rejection_reasons, "rejection_reasons"))

    @property
    def decision_authority(self) -> bool:
        return self.state is ClaimState.CORROBORATED


class ClaimAdmissionEvaluator:
    """Derive grounding and corroboration without trusting worker confidence."""

    def __init__(self, evidence_resolver: "EvidenceResolver") -> None:
        from .evidence import EvidenceResolver

        if not isinstance(evidence_resolver, EvidenceResolver):
            raise ClaimValidationError("ClaimAdmissionEvaluator requires an EvidenceResolver")
        self._evidence_resolver = evidence_resolver

    def assess(self, claim: Claim, groundings: Iterable[ClaimGrounding]) -> ClaimAssessment:
        if not isinstance(claim, Claim):
            raise ClaimValidationError("claim must be a Claim")
        normalized_groundings = tuple(groundings)
        if any(not isinstance(item, ClaimGrounding) for item in normalized_groundings):
            raise ClaimValidationError("groundings must contain ClaimGrounding values")
        if any(item.claim_id != claim.claim_id for item in normalized_groundings):
            raise ClaimValidationError("grounding claim_id must match claim")

        resolved = tuple(self._resolve(item) for item in normalized_groundings)
        invalid = tuple(item for item in resolved if not self._entails(claim, item))
        if invalid:
            return ClaimAssessment(
                claim_id=claim.claim_id,
                state=ClaimState.REJECTED,
                provenance_clusters=self._clusters(resolved),
                grounding_ids=tuple(item.grounding_id for item in normalized_groundings),
                grounding_refs=tuple(item.reference for item in resolved),
                rejection_reasons=("extract-does-not-entail-claim",),
            )
        if not normalized_groundings:
            return ClaimAssessment(claim.claim_id, ClaimState.CANDIDATE, (), ())

        clusters = self._clusters(resolved)
        state = ClaimState.CORROBORATED if len(clusters) >= 2 else ClaimState.ISOLATED
        return ClaimAssessment(
            claim_id=claim.claim_id,
            state=state,
            provenance_clusters=clusters,
            grounding_ids=tuple(item.grounding_id for item in normalized_groundings),
            grounding_refs=tuple(item.reference for item in resolved),
        )

    def _resolve(self, grounding: ClaimGrounding) -> "ResolvedClaimGrounding":
        from .evidence import EvidenceAnchor, EvidenceValidationError

        try:
            anchor = EvidenceAnchor.from_dict(grounding.anchor)
            evidence = self._evidence_resolver.resolve(anchor)
            wording = _selected_text(anchor.selector_type, anchor.selector_value, evidence.bytes)
            metadata = evidence.artifact.metadata
            return ResolvedClaimGrounding(
                grounding_id=grounding.grounding_id,
                reference=evidence.artifact_ref,
                wording=wording,
                version=_metadata_text(metadata, "claim_version"),
                time_range=_metadata_text(metadata, "claim_time_range"),
                scope=_metadata_text(metadata, "claim_scope"),
                conditions=_metadata_texts(metadata, "claim_conditions"),
                provenance=evidence.artifact.provenance_descriptor,
            )
        except (EvidenceValidationError, TypeError, ValueError, UnicodeDecodeError) as error:
            raise ClaimValidationError(f"grounding {grounding.grounding_id} is not resolvable: {error}") from error

    @staticmethod
    def _entails(claim: Claim, grounding: "ResolvedClaimGrounding") -> bool:
        if claim.normalized_statement not in _normalized(grounding.wording):
            return False
        if claim.version != grounding.version or claim.time_range != grounding.time_range:
            return False
        if claim.scope != grounding.scope:
            return False
        return set(claim.conditions).issubset(grounding.conditions)

    @staticmethod
    def _clusters(groundings: tuple["ResolvedClaimGrounding", ...]) -> tuple[str, ...]:
        """Cluster all sources sharing any resolved upstream identity.

        A mirror can carry a different URL or canonical label but still share a
        content fingerprint, dataset, or citation-origin identity. Ownership
        remains auditable but does not collapse a release record and an
        independent installed-behavior observation into one source. The
        first resolved source names the connected component for stable audit
        output; it does not choose a preferred source.
        """

        components: list[tuple[set[str], str]] = []
        for grounding in groundings:
            identities = set(grounding.provenance.identities)
            matches = [index for index, (known, _label) in enumerate(components) if known & identities]
            if not matches:
                components.append((identities, grounding.provenance.cluster_id))
                continue
            first = matches[0]
            merged_identities, label = components[first]
            merged_identities.update(identities)
            for index in reversed(matches[1:]):
                extra_identities, _extra_label = components.pop(index)
                merged_identities.update(extra_identities)
            components[first] = (merged_identities, label)
        return tuple(label for _identities, label in components)


@dataclass(frozen=True, slots=True)
class ResolvedClaimGrounding:
    grounding_id: str
    reference: ArtifactRef
    wording: str
    version: str
    time_range: str
    scope: str
    conditions: tuple[str, ...]
    provenance: ProvenanceDescriptor


def _selected_text(selector_type: str, selector: Mapping[str, object], data: bytes) -> str:
    if selector_type == "line":
        lines = data.decode("utf-8").splitlines()
        start = int(selector["start"]) - 1
        end = int(selector["end"])
        return "\n".join(lines[start:end])
    if selector_type == "fragment":
        start = int(selector["start"])
        end = start + int(selector["length"]) if "length" in selector else int(selector["end"])
        return data[start:end].decode("utf-8")
    raise ClaimValidationError("claim grounding selector must be line or fragment")


def _metadata_text(metadata: Mapping[str, object], field: str) -> str:
    value = metadata.get(field)
    try:
        return _text(value, field)
    except ClaimValidationError as error:
        raise ClaimValidationError(f"evidence metadata requires {field}") from error


def _metadata_texts(metadata: Mapping[str, object], field: str) -> tuple[str, ...]:
    value = metadata.get(field)
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ClaimValidationError(f"evidence metadata requires {field}")
    return _texts(value, field)


__all__ = [
    "Claim",
    "ClaimAdmissionEvaluator",
    "ClaimAssessment",
    "ClaimGrounding",
    "ClaimState",
    "ClaimValidationError",
    "ProvenanceDescriptor",
]
