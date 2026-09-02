"""Cross-provider comparison stage for one portfolio batch.

After a batch executes, captured results are compared across providers:
captures are deduplicated through the provenance-clustering upstream
identity reused from :mod:`research_tree.claims`, relevance is scored per
provider against the intent terms, and the measured values are written back
into the batch outcomes' ``novelty``, ``coverage``, ``source_quality``, and
``contradictions`` fields.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from .claims import ProvenanceDescriptor, cluster_provenance_components
from .domain import canonical_json_bytes

CROSS_COMPARISON_KIND = "batch-cross-comparison"
CROSS_COMPARISON_SCHEMA_VERSION = 2
SOURCE_KIND_QUALITY = {"snippet": "low", "summary": "medium", "full-source": "high", "experiment": "high"}
SNIPPET_MAX_BYTES = 2048
FULL_SOURCE_MIN_BYTES = 32768


class CrossComparisonError(ValueError):
    """Raised when cross-comparison inputs fail validation."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CrossComparisonError(f"{label} must be a non-empty string")
    return value.strip()


def _identifier(value: object, label: str) -> str:
    result = _text(value, label)
    if not result.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise CrossComparisonError(f"{label} must be an identifier: {result!r}")
    return result


def _quality_from_size(size_bytes: int) -> str:
    if size_bytes >= FULL_SOURCE_MIN_BYTES:
        return "high"
    if size_bytes >= SNIPPET_MAX_BYTES:
        return "medium"
    return "low"


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    """One captured result submitted to the batch cross-comparison stage."""

    capture_ref: str
    outcome_id: str
    method_id: str
    provider_id: str
    upstream_id: str | None = None
    content_fingerprint: str | None = None
    matched_terms: tuple[str, ...] = ()
    source_kind: str = "snippet"
    size_bytes: int = 0
    mechanism_summary: str | None = None

    @property
    def provenance(self) -> ProvenanceDescriptor | None:
        if self.upstream_id is None and self.content_fingerprint is None:
            return None
        return ProvenanceDescriptor(upstream_id=self.upstream_id, content_fingerprint=self.content_fingerprint)

    @property
    def measured_source_quality(self) -> str:
        declared = SOURCE_KIND_QUALITY.get(self.source_kind)
        return declared or _quality_from_size(self.size_bytes)

    @property
    def mechanism_key(self) -> str | None:
        """Stable identity of the declared mechanism (None when undeclared)."""

        if self.mechanism_summary is None:
            return None
        normalized = " ".join(self.mechanism_summary.lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_ref": self.capture_ref,
            "outcome_id": self.outcome_id,
            "method_id": self.method_id,
            "provider_id": self.provider_id,
            "upstream_id": self.upstream_id,
            "content_fingerprint": self.content_fingerprint,
            "matched_terms": list(self.matched_terms),
            "source_kind": self.source_kind,
            "size_bytes": self.size_bytes,
            "mechanism_summary": self.mechanism_summary,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "CaptureRecord":
        if not isinstance(value, Mapping):
            raise CrossComparisonError("capture record must be a mapping")
        upstream = value.get("upstream_id")
        fingerprint = value.get("content_fingerprint")
        if upstream is not None:
            upstream = _text(upstream, "upstream_id")
        if fingerprint is not None:
            fingerprint = _text(fingerprint, "content_fingerprint")
        if upstream is None and fingerprint is None:
            raise CrossComparisonError("capture record requires a resolved upstream identity")
        mechanism_summary = value.get("mechanism_summary")
        if mechanism_summary is not None:
            mechanism_summary = _text(mechanism_summary, "mechanism_summary")
        matched = tuple(_text(item, "matched term").lower() for item in value.get("matched_terms", ()))
        size = value.get("size_bytes", 0)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise CrossComparisonError("size_bytes must be a non-negative integer")
        return cls(
            capture_ref=_identifier(value.get("capture_ref"), "capture_ref"),
            outcome_id=_identifier(value.get("outcome_id"), "outcome_id"),
            method_id=_identifier(value.get("method_id"), "method_id"),
            provider_id=_identifier(value.get("provider_id"), "provider_id"),
            upstream_id=upstream,
            content_fingerprint=fingerprint,
            matched_terms=matched,
            source_kind=_text(value.get("source_kind", "snippet"), "source_kind"),
            size_bytes=size,
            mechanism_summary=mechanism_summary,
        )


@dataclass(frozen=True, slots=True)
class UpstreamIdentityGroup:
    """One provenance cluster shared by one or more provider captures."""

    identity: str
    capture_refs: tuple[str, ...]
    provider_ids: tuple[str, ...]
    content_conflict: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "capture_refs": list(self.capture_refs),
            "provider_ids": list(self.provider_ids),
            "content_conflict": self.content_conflict,
        }


@dataclass(frozen=True, slots=True)
class DuplicateCapture:
    """A capture that duplicated an earlier provider's upstream identity."""

    capture_ref: str
    provider_id: str
    outcome_id: str
    origin_capture_ref: str
    origin_provider_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_ref": self.capture_ref,
            "provider_id": self.provider_id,
            "outcome_id": self.outcome_id,
            "origin_capture_ref": self.origin_capture_ref,
            "origin_provider_id": self.origin_provider_id,
        }


@dataclass(frozen=True, slots=True)
class MechanismCluster:
    """One mechanism-level cluster (issue #494).

    Captures whose declared mechanism summaries are equivalent collapse into
    one cluster regardless of upstream identity, so N same-mechanism
    different-URL projects count as one distinct implementation.
    """

    mechanism_key: str
    mechanism_summary: str
    capture_refs: tuple[str, ...]
    provider_ids: tuple[str, ...]
    origin_capture_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism_key": self.mechanism_key,
            "mechanism_summary": self.mechanism_summary,
            "capture_refs": list(self.capture_refs),
            "provider_ids": list(self.provider_ids),
            "origin_capture_ref": self.origin_capture_ref,
        }


@dataclass(frozen=True, slots=True)
class OutcomeMeasurement:
    """Measured outcome fields for one method/provider boundary."""

    outcome_id: str
    novelty: str
    coverage: str
    source_quality: str
    contradictions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "novelty": self.novelty,
            "coverage": self.coverage,
            "source_quality": self.source_quality,
            "contradictions": list(self.contradictions),
        }


@dataclass(frozen=True, slots=True)
class BatchCrossComparison:
    """Measured cross-provider result for one portfolio batch."""

    comparison_id: str
    portfolio_id: str
    batch_id: str
    identity_groups: tuple[UpstreamIdentityGroup, ...]
    duplicates: tuple[DuplicateCapture, ...]
    provider_relevance: Mapping[str, float]
    measured_outcomes: tuple[OutcomeMeasurement, ...]
    dedup_ratio: float
    provider_fanout: int
    mechanism_clusters: tuple[MechanismCluster, ...] = ()
    mechanism_duplicates: tuple[DuplicateCapture, ...] = ()
    undeclared_mechanism_capture_refs: tuple[str, ...] = ()
    distinct_implementations: int = 0
    schema_version: int = CROSS_COMPARISON_SCHEMA_VERSION
    kind: str = CROSS_COMPARISON_KIND

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "comparison_id": self.comparison_id,
            "portfolio_id": self.portfolio_id,
            "batch_id": self.batch_id,
            "identity_groups": [item.to_dict() for item in self.identity_groups],
            "duplicates": [item.to_dict() for item in self.duplicates],
            "provider_relevance": dict(sorted(self.provider_relevance.items())),
            "measured_outcomes": [item.to_dict() for item in self.measured_outcomes],
            "dedup_ratio": self.dedup_ratio,
            "provider_fanout": self.provider_fanout,
            "mechanism_clusters": [item.to_dict() for item in self.mechanism_clusters],
            "mechanism_duplicates": [item.to_dict() for item in self.mechanism_duplicates],
            "undeclared_mechanism_capture_refs": list(self.undeclared_mechanism_capture_refs),
            "distinct_implementations": self.distinct_implementations,
        }

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> "BatchCrossComparison":
        base_required = {
            "schema_version",
            "kind",
            "comparison_id",
            "portfolio_id",
            "batch_id",
            "identity_groups",
            "duplicates",
            "provider_relevance",
            "measured_outcomes",
            "dedup_ratio",
            "provider_fanout",
        }
        mechanism_required = {
            "mechanism_clusters",
            "mechanism_duplicates",
            "undeclared_mechanism_capture_refs",
            "distinct_implementations",
        }
        version = value.get("schema_version") if isinstance(value, Mapping) else None
        required = base_required | mechanism_required if version != 1 else base_required
        if not isinstance(value, Mapping) or set(value) != required:
            raise CrossComparisonError("cross comparison payload has unexpected keys")
        if value["kind"] != CROSS_COMPARISON_KIND:
            raise CrossComparisonError("cross comparison kind is invalid")
        if isinstance(value["schema_version"], bool) or value["schema_version"] not in (
            1,
            CROSS_COMPARISON_SCHEMA_VERSION,
        ):
            raise CrossComparisonError("unsupported cross comparison schema_version")
        groups = tuple(
            UpstreamIdentityGroup(
                identity=_text(item.get("identity"), "identity"),
                capture_refs=tuple(_identifier(ref, "capture_ref") for ref in item.get("capture_refs", ())),
                provider_ids=tuple(_identifier(pid, "provider_id") for pid in item.get("provider_ids", ())),
                content_conflict=bool(item.get("content_conflict", False)),
            )
            for item in value["identity_groups"]
        )
        duplicates = tuple(
            DuplicateCapture(
                capture_ref=_identifier(item.get("capture_ref"), "capture_ref"),
                provider_id=_identifier(item.get("provider_id"), "provider_id"),
                outcome_id=_identifier(item.get("outcome_id"), "outcome_id"),
                origin_capture_ref=_identifier(item.get("origin_capture_ref"), "origin_capture_ref"),
                origin_provider_id=_identifier(item.get("origin_provider_id"), "origin_provider_id"),
            )
            for item in value["duplicates"]
        )
        measured = tuple(
            OutcomeMeasurement(
                outcome_id=_identifier(item.get("outcome_id"), "outcome_id"),
                novelty=_text(item.get("novelty"), "novelty"),
                coverage=_text(item.get("coverage"), "coverage"),
                source_quality=_text(item.get("source_quality"), "source_quality"),
                contradictions=tuple(_text(ref, "contradiction") for ref in item.get("contradictions", ())),
            )
            for item in value["measured_outcomes"]
        )
        relevance_raw = value["provider_relevance"]
        if not isinstance(relevance_raw, Mapping):
            raise CrossComparisonError("provider_relevance must be a mapping")
        mechanism_clusters = (
            tuple(
                MechanismCluster(
                    mechanism_key=_text(item.get("mechanism_key"), "mechanism_key"),
                    mechanism_summary=_text(item.get("mechanism_summary"), "mechanism_summary"),
                    capture_refs=tuple(_identifier(ref, "capture_ref") for ref in item.get("capture_refs", ())),
                    provider_ids=tuple(_identifier(pid, "provider_id") for pid in item.get("provider_ids", ())),
                    origin_capture_ref=_identifier(item.get("origin_capture_ref"), "origin_capture_ref"),
                )
                for item in value["mechanism_clusters"]
            )
            if version != 1
            else ()
        )
        mechanism_duplicates = (
            tuple(
                DuplicateCapture(
                    capture_ref=_identifier(item.get("capture_ref"), "capture_ref"),
                    provider_id=_identifier(item.get("provider_id"), "provider_id"),
                    outcome_id=_identifier(item.get("outcome_id"), "outcome_id"),
                    origin_capture_ref=_identifier(item.get("origin_capture_ref"), "origin_capture_ref"),
                    origin_provider_id=_identifier(item.get("origin_provider_id"), "origin_provider_id"),
                )
                for item in value["mechanism_duplicates"]
            )
            if version != 1
            else ()
        )
        undeclared_refs = (
            tuple(_identifier(ref, "capture_ref") for ref in value["undeclared_mechanism_capture_refs"])
            if version != 1
            else ()
        )
        distinct = int(value["distinct_implementations"]) if version != 1 else 0
        if isinstance(distinct, bool) or distinct < 0 or distinct != len(mechanism_clusters):
            raise CrossComparisonError("distinct_implementations must equal the mechanism cluster count")
        return cls(
            comparison_id=_identifier(value["comparison_id"], "comparison_id"),
            portfolio_id=_identifier(value["portfolio_id"], "portfolio_id"),
            batch_id=_identifier(value["batch_id"], "batch_id"),
            identity_groups=groups,
            duplicates=duplicates,
            provider_relevance={_identifier(key, "provider_id"): float(item) for key, item in relevance_raw.items()},
            measured_outcomes=measured,
            dedup_ratio=float(value["dedup_ratio"]),
            provider_fanout=int(value["provider_fanout"]),
            mechanism_clusters=mechanism_clusters,
            mechanism_duplicates=mechanism_duplicates,
            undeclared_mechanism_capture_refs=undeclared_refs,
            distinct_implementations=distinct,
            schema_version=CROSS_COMPARISON_SCHEMA_VERSION,
        )


def _normalized_outcomes(outcomes: Sequence[Any]) -> tuple[Any, ...]:
    from .search_portfolio import InvalidSearchPortfolioError, MethodExecutionOutcome

    normalized: list[Any] = []
    for item in outcomes:
        if isinstance(item, MethodExecutionOutcome):
            normalized.append(item)
            continue
        try:
            normalized.append(MethodExecutionOutcome.from_dict(item))
        except InvalidSearchPortfolioError as exc:
            raise CrossComparisonError(f"invalid outcome payload: {exc}") from exc
    return tuple(normalized)


def compare_portfolio_batch(
    *,
    comparison_id: str,
    portfolio_id: str,
    batch_id: str,
    outcomes: Sequence[Any],
    captures: Sequence[Any],
    intent_terms: Sequence[str] = (),
) -> BatchCrossComparison:
    """Compare one batch's captures across providers and measure outcomes.

    Deduplication reuses the provenance-clustering upstream identity from
    :mod:`research_tree.claims`: captures whose resolved identities overlap
    collapse into one upstream identity group, the first capture names the
    group, and later captures are duplicates tagged with the origin provider.
    On top of that provenance layer, captures that declare a
    ``mechanism_summary`` are clustered by mechanism equivalence regardless of
    upstream identity (issue #494): provenance-distinct captures with an
    equivalent mechanism are tagged as mechanism duplicates, and
    ``distinct_implementations`` counts mechanism clusters, not raw sources.
    Relevance is scored per provider against the intent terms; novelty,
    coverage, source quality, and content-conflict contradictions are
    measured per outcome.
    """

    comparison_id = _identifier(comparison_id, "comparison_id")
    portfolio_id = _identifier(portfolio_id, "portfolio_id")
    batch_id = _identifier(batch_id, "batch_id")
    normalized_outcomes = _normalized_outcomes(outcomes)
    outcome_ids = {item.outcome_id for item in normalized_outcomes}
    declared_capture_refs = {ref for outcome in normalized_outcomes for ref in getattr(outcome, "capture_refs", ())}
    records = tuple(CaptureRecord.from_dict(item) for item in captures)
    for record in records:
        if record.outcome_id not in outcome_ids:
            raise CrossComparisonError(f"capture references unknown outcome: {record.outcome_id}")
        if declared_capture_refs and record.capture_ref not in declared_capture_refs:
            raise CrossComparisonError(f"capture is not declared on its outcome: {record.capture_ref}")
    terms = tuple(dict.fromkeys(_text(term, "intent term").lower() for term in intent_terms))

    grouped = _cluster_captures(records)
    duplicates: list[DuplicateCapture] = []
    groups: list[UpstreamIdentityGroup] = []
    for label, members in grouped:
        providers = tuple(dict.fromkeys(record.provider_id for record in members))
        fingerprints = {record.content_fingerprint for record in members if record.content_fingerprint}
        groups.append(
            UpstreamIdentityGroup(
                identity=label,
                capture_refs=tuple(record.capture_ref for record in members),
                provider_ids=providers,
                content_conflict=len(fingerprints) > 1,
            )
        )
        for duplicate in members[1:]:
            origin = members[0]
            duplicates.append(
                DuplicateCapture(
                    capture_ref=duplicate.capture_ref,
                    provider_id=duplicate.provider_id,
                    outcome_id=duplicate.outcome_id,
                    origin_capture_ref=origin.capture_ref,
                    origin_provider_id=origin.provider_id,
                )
            )

    relevance_by_provider: dict[str, list[float]] = {}
    for record in records:
        relevance_by_provider.setdefault(record.provider_id, []).append(_capture_relevance(record, terms))
    provider_relevance = {
        provider: round(sum(values) / len(values), 6) for provider, values in relevance_by_provider.items()
    }

    mechanism_clusters, mechanism_duplicate_captures, undeclared_refs = _cluster_mechanisms(records, duplicates)
    measured = tuple(
        item
        for item in (
            _measure_outcome(
                outcome,
                records,
                grouped,
                terms,
                mechanism_duplicate_refs=frozenset(item.capture_ref for item in mechanism_duplicate_captures),
            )
            for outcome in normalized_outcomes
        )
        if item is not None
    )
    total = len(records)
    return BatchCrossComparison(
        comparison_id=comparison_id,
        portfolio_id=portfolio_id,
        batch_id=batch_id,
        identity_groups=tuple(groups),
        duplicates=tuple(duplicates),
        provider_relevance=provider_relevance,
        measured_outcomes=measured,
        dedup_ratio=round(len(duplicates) / total, 6) if total else 0.0,
        provider_fanout=len({record.provider_id for record in records}),
        mechanism_clusters=mechanism_clusters,
        mechanism_duplicates=mechanism_duplicate_captures,
        undeclared_mechanism_capture_refs=undeclared_refs,
        distinct_implementations=len(mechanism_clusters),
    )


def _cluster_mechanisms(
    records: Sequence[CaptureRecord],
    duplicates: Sequence[DuplicateCapture],
) -> tuple[tuple[MechanismCluster, ...], tuple[DuplicateCapture, ...], tuple[str, ...]]:
    """Cluster declared mechanism summaries and tag mechanism-level duplicates.

    Captures with equivalent normalized summaries collapse into one cluster
    regardless of upstream identity. A capture that is already a provenance
    duplicate is not re-tagged (one honest duplicate tag per capture);
    provenance-distinct captures with an equivalent mechanism are tagged
    against the cluster's first capture. Captures without a declared summary
    are reported as undeclared and never inflate the implementation count.
    """

    order: list[str] = []
    members: dict[str, list[CaptureRecord]] = {}
    summaries: dict[str, str] = {}
    for record in records:
        key = record.mechanism_key
        if key is None:
            continue
        if key not in members:
            members[key] = []
            order.append(key)
            summaries[key] = " ".join((record.mechanism_summary or "").lower().split())
        members[key].append(record)
    provenance_duplicate_refs = {item.capture_ref for item in duplicates}
    clusters: list[MechanismCluster] = []
    mechanism_duplicates: list[DuplicateCapture] = []
    for key in order:
        cluster_members = members[key]
        origin = cluster_members[0]
        clusters.append(
            MechanismCluster(
                mechanism_key=key,
                mechanism_summary=summaries[key],
                capture_refs=tuple(record.capture_ref for record in cluster_members),
                provider_ids=tuple(dict.fromkeys(record.provider_id for record in cluster_members)),
                origin_capture_ref=origin.capture_ref,
            )
        )
        for duplicate in cluster_members[1:]:
            if duplicate.capture_ref in provenance_duplicate_refs:
                continue
            mechanism_duplicates.append(
                DuplicateCapture(
                    capture_ref=duplicate.capture_ref,
                    provider_id=duplicate.provider_id,
                    outcome_id=duplicate.outcome_id,
                    origin_capture_ref=origin.capture_ref,
                    origin_provider_id=origin.provider_id,
                )
            )
    undeclared = tuple(sorted(record.capture_ref for record in records if record.mechanism_key is None))
    return tuple(clusters), tuple(mechanism_duplicates), undeclared


def _cluster_captures(records: Sequence[CaptureRecord]) -> list[tuple[str, list[CaptureRecord]]]:
    descriptors = [record.provenance for record in records]
    provenance_positions = [index for index, descriptor in enumerate(descriptors) if descriptor is not None]
    components = cluster_provenance_components(descriptors[index] for index in provenance_positions)
    member_lists: list[list[CaptureRecord]] = [[] for _ in components]
    labels = [label for label, _identities in components]
    capture_to_component: dict[int, int] = {}
    for order, index in enumerate(provenance_positions):
        record = records[index]
        identities = descriptors[index].identities
        component_index = next(position for position, (_label, merged) in enumerate(components) if identities & merged)
        member_lists[component_index].append(record)
        capture_to_component[index] = component_index
    grouped = [(labels[position], members) for position, members in enumerate(member_lists) if members]
    for index, record in enumerate(records):
        if index not in capture_to_component:
            grouped.append((f"unresolved:{record.capture_ref}", [record]))
    return grouped


def _capture_relevance(record: CaptureRecord, terms: Sequence[str]) -> float:
    if not terms:
        return 0.0
    matched = set(record.matched_terms) & set(terms)
    return round(len(matched) / len(terms), 6)


def _measure_outcome(
    outcome: Any,
    records: Sequence[CaptureRecord],
    grouped: Sequence[tuple[str, Sequence[CaptureRecord]]],
    terms: Sequence[str],
    *,
    mechanism_duplicate_refs: frozenset[str] = frozenset(),
) -> Any:
    from .search_portfolio import _metric_max

    owned = [record for record in records if record.outcome_id == outcome.outcome_id]
    if not owned:
        return None
    owned_refs = {record.capture_ref for record in owned}
    contradiction_refs: list[str] = []
    unique_identities = 0
    for label, members in grouped:
        member_refs = {record.capture_ref for record in members}
        if not member_refs & owned_refs:
            continue
        # A mechanism-duplicate capture does not count as a new unique
        # identity for its outcome (issue #494): same mechanism, different URL.
        if members[0].capture_ref in owned_refs and members[0].capture_ref not in mechanism_duplicate_refs:
            unique_identities += 1
        fingerprints = {record.content_fingerprint for record in members if record.content_fingerprint}
        if len(fingerprints) > 1:
            contradiction_refs.append(f"cross-comparison:{label}:content-conflict")
    matched_terms: set[str] = set()
    for record in owned:
        matched_terms.update(set(record.matched_terms) & set(terms))
    coverage_ratio = len(matched_terms) / len(terms) if terms else 0.0
    coverage = "complete" if coverage_ratio >= 1.0 else ("partial" if coverage_ratio > 0.0 else "none")
    novelty = "new" if unique_identities else ("low" if owned else "none")
    source_quality = _metric_max(
        tuple(record.measured_source_quality for record in owned),
        {"unknown": 0, "low": 1, "medium": 2, "high": 3},
        "unknown",
    )
    return OutcomeMeasurement(
        outcome_id=outcome.outcome_id,
        novelty=novelty,
        coverage=coverage,
        source_quality=source_quality,
        contradictions=tuple(contradiction_refs),
    )


def apply_cross_comparison(
    comparison: BatchCrossComparison,
    outcomes: Sequence[Any],
) -> tuple[Any, ...]:
    """Write measured comparison values back into batch outcomes.

    Only outcomes the comparison measured (those with captures) change;
    their ``novelty``, ``coverage``, ``source_quality``, and
    ``contradictions`` fields are replaced by measured values, keeping
    any explicitly declared contradictions.
    """

    from .search_portfolio import MethodExecutionOutcome

    measurements = {item.outcome_id: item for item in comparison.measured_outcomes}
    measured: list[Any] = []
    for outcome in outcomes:
        if not isinstance(outcome, MethodExecutionOutcome):
            raise CrossComparisonError("apply_cross_comparison requires MethodExecutionOutcome values")
        measurement = measurements.get(outcome.outcome_id)
        if measurement is None:
            measured.append(outcome)
            continue
        contradictions = tuple(dict.fromkeys((*outcome.contradictions, *measurement.contradictions)))
        measured.append(
            replace(
                outcome,
                novelty=measurement.novelty,
                coverage=measurement.coverage,
                source_quality=measurement.source_quality,
                contradictions=contradictions,
            )
        )
    return tuple(measured)


__all__ = [
    "CROSS_COMPARISON_KIND",
    "CROSS_COMPARISON_SCHEMA_VERSION",
    "BatchCrossComparison",
    "CaptureRecord",
    "CrossComparisonError",
    "DuplicateCapture",
    "MechanismCluster",
    "OutcomeMeasurement",
    "UpstreamIdentityGroup",
    "apply_cross_comparison",
    "compare_portfolio_batch",
]
