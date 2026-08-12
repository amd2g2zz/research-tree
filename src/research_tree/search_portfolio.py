"""Intent-derived, host-neutral acquisition portfolio contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Mapping, Sequence

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    RuntimeStoreError,
    canonical_json_bytes,
    thaw_json,
    validate_identifier,
)
from .policy import DecisionSlotDeficit
from .run_ledger import LedgerConflictError, LedgerIntegrityError, RunLedger
from .source_capture import AnalysisCheckpoint, AcquisitionReceipt, SourceCapture


_BOUNDARY_KINDS = {
    "search_provider",
    "repository_inspection",
    "primary_source",
    "documentation_lookup",
    "scholarly_lookup",
    "experiment",
    "direct_retrieval",
}
_DISPOSITIONS = {"deepen", "broaden", "pivot", "validate", "sufficient_for_slot", "blocked"}
_HIDDEN_FIELDS = {"prompt", "private_prompt", "system_prompt", "chain_of_thought", "private_reasoning"}
_EVIDENCE_DISPOSITIONS = {
    "captured",
    "failed_retrieval",
    "http_404",
    "no_results",
    "parser_failed",
    "rate_limited",
    "unavailable",
    "permission_limited",
}
_AUTHORITY_DISPOSITIONS = {"inside_confirmed_authority", "requires_requester_reopen"}
SEARCH_PORTFOLIO_KIND = "search-portfolio"
BATCH_COVERAGE_ASSESSMENT_KIND = "batch-coverage-assessment"
METHOD_REGISTRY_KIND = "method-registry"


class SearchPortfolioError(ValueError):
    """A portfolio violates its lineage or authority boundary."""


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _artifact_ref(value: ArtifactRevision) -> ArtifactRef:
    return ArtifactRef(value.round_id, value.id, value.revision)


def _reference_label(reference: ArtifactRef) -> str:
    return f"{reference.artifact_id}@{reference.revision}"


def _artifact_payload(value: ArtifactRevision) -> dict[str, Any]:
    return thaw_json(value.payload)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SearchPortfolioError(f"{label} must be a non-empty string")
    return value.strip()


def _strings(value: Sequence[object], label: str, *, required: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SearchPortfolioError(f"{label} must be a sequence")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if required and not result:
        raise SearchPortfolioError(f"{label} must not be empty")
    return result


def _planning_text(value: object) -> tuple[str, ...]:
    """Extract bounded public context from already-persisted planning artifacts."""

    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if isinstance(value, Mapping):
        result: list[str] = []
        for key, child in value.items():
            if str(key).lower() in _HIDDEN_FIELDS:
                continue
            result.extend(_planning_text(child))
        return tuple(result)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result: list[str] = []
        for child in value:
            result.extend(_planning_text(child))
        return tuple(result)
    return ()


@dataclass(frozen=True, slots=True)
class MethodBoundary:
    method_id: str
    provider_id: str
    corpus_id: str
    boundary_kind: str
    permission_profile: str
    expected_evidence_class: str
    available: bool
    provenance_group: str
    limitations: tuple[str, ...] = ()
    limitation_code: str | None = None
    fallback_method_id: str | None = None
    retryable: bool = False
    retry_limit: int = 0
    input_media: tuple[str, ...] = ("text",)
    invocation_adapter: str = "host-neutral"
    output_schema: str = "source-capture-v1"
    timeout_seconds: int = 30
    extraction_path: str = "default"
    failure_boundary: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.method_id, "method_id"),
            (self.provider_id, "provider_id"),
            (self.corpus_id, "corpus_id"),
            (self.permission_profile, "permission_profile"),
            (self.expected_evidence_class, "expected_evidence_class"),
            (self.provenance_group, "provenance_group"),
        ):
            _text(value, label)
        if self.boundary_kind not in _BOUNDARY_KINDS:
            raise SearchPortfolioError("unsupported boundary_kind")
        if not isinstance(self.available, bool):
            raise SearchPortfolioError("available must be bool")
        object.__setattr__(self, "limitations", _strings(self.limitations, "limitations"))
        if not self.available and not self.limitation_code:
            raise SearchPortfolioError("unavailable methods require limitation_code")
        if self.limitation_code is not None:
            _text(self.limitation_code, "limitation_code")
        if self.fallback_method_id is not None:
            _text(self.fallback_method_id, "fallback_method_id")
        if not isinstance(self.retryable, bool):
            raise SearchPortfolioError("retryable must be bool")
        if isinstance(self.retry_limit, bool) or not isinstance(self.retry_limit, int) or self.retry_limit < 0:
            raise SearchPortfolioError("retry_limit must be a non-negative integer")
        if self.retry_limit and not self.retryable:
            raise SearchPortfolioError("retry_limit requires retryable method")
        object.__setattr__(self, "input_media", _strings(self.input_media, "input_media", required=True))
        for value, label in (
            (self.invocation_adapter, "invocation_adapter"),
            (self.output_schema, "output_schema"),
            (self.extraction_path, "extraction_path"),
        ):
            _text(value, label)
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or self.timeout_seconds <= 0
        ):
            raise SearchPortfolioError("timeout_seconds must be a positive integer")
        failure_boundary = self.failure_boundary or f"{self.boundary_kind}:{self.provider_id}:{self.corpus_id}"
        object.__setattr__(self, "failure_boundary", _text(failure_boundary, "failure_boundary"))

    def selection_record(
        self,
        available_by_id: Mapping[str, "MethodBoundary"],
        *,
        registry_version: str,
    ) -> dict[str, Any]:
        """Return an auditable method selection without claiming live execution."""

        fallback = available_by_id.get(self.fallback_method_id or "")
        if fallback is not None and not fallback.available:
            fallback = None
        return {
            "method_id": self.method_id,
            "method_registry_version": registry_version,
            "status": "accepted" if self.available else "rejected",
            "reason": "capability_available" if self.available else self.limitation_code,
            "provider_id": self.provider_id,
            "corpus_id": self.corpus_id,
            "boundary_kind": self.boundary_kind,
            "input_media": list(self.input_media),
            "permission_profile": self.permission_profile,
            "invocation_adapter": self.invocation_adapter,
            "output_schema": self.output_schema,
            "timeout_seconds": self.timeout_seconds,
            "extraction_path": self.extraction_path,
            "failure_boundary": self.failure_boundary,
            "provenance_group": self.provenance_group,
            "expected_evidence_class": self.expected_evidence_class,
            "capability": "available" if self.available else self.limitation_code,
            "retryable": self.retryable,
            "retry_limit": self.retry_limit,
            "limitations": list(self.limitations),
            "fallback_method_id": self.fallback_method_id,
            "alternate_evidence_class": None if fallback is None else fallback.expected_evidence_class,
        }


@dataclass(frozen=True, slots=True)
class MethodRegistry:
    """Versioned host-neutral method declarations used by one portfolio."""

    version: str
    boundaries: tuple[MethodBoundary, ...]
    registry_id: str = ""

    def __post_init__(self) -> None:
        _text(self.version, "version")
        if not isinstance(self.boundaries, tuple) or not self.boundaries:
            raise SearchPortfolioError("boundaries must contain MethodBoundary values")
        if any(not isinstance(item, MethodBoundary) for item in self.boundaries):
            raise SearchPortfolioError("boundaries must contain MethodBoundary values")
        method_ids = tuple(item.method_id for item in self.boundaries)
        if len(set(method_ids)) != len(method_ids):
            raise SearchPortfolioError("method registry contains duplicate method_id")
        if any(item.fallback_method_id and item.fallback_method_id not in method_ids for item in self.boundaries):
            raise SearchPortfolioError("fallback_method_id must exist in method registry")
        registry_id = self.registry_id or f"method-registry-{self.digest[:16]}"
        validate_identifier(registry_id, "registry_id")
        object.__setattr__(self, "registry_id", registry_id)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "version": self.version,
                "boundaries": [_json_value(asdict(item)) for item in self.boundaries],
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "version": self.version,
            "digest": self.digest,
            "boundaries": [_json_value(asdict(item)) for item in self.boundaries],
        }


@dataclass(frozen=True, slots=True)
class SearchPortfolioComparison:
    """Controlled, non-causal comparison of legacy and portfolio outcomes."""

    comparison_id: str
    shared_input_digest: str
    legacy_rediscovery_count: int
    portfolio_rediscovery_count: int
    legacy_coverage: float
    portfolio_coverage: float
    legacy_depth: int
    portfolio_depth: int
    legacy_closed: bool
    portfolio_closed: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.comparison_id, "comparison_id")
        if len(self.shared_input_digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.shared_input_digest
        ):
            raise SearchPortfolioError("shared_input_digest must be a sha256 digest")
        for value, label in (
            (self.legacy_rediscovery_count, "legacy_rediscovery_count"),
            (self.portfolio_rediscovery_count, "portfolio_rediscovery_count"),
            (self.legacy_depth, "legacy_depth"),
            (self.portfolio_depth, "portfolio_depth"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SearchPortfolioError(f"{label} must be a non-negative integer")
        for value, label in (
            (self.legacy_coverage, "legacy_coverage"),
            (self.portfolio_coverage, "portfolio_coverage"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
                raise SearchPortfolioError(f"{label} must be between zero and one")
        if not isinstance(self.legacy_closed, bool) or not isinstance(self.portfolio_closed, bool):
            raise SearchPortfolioError("closure values must be bool")
        object.__setattr__(self, "limitations", _strings(self.limitations, "limitations", required=True))

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "shared_input_digest": self.shared_input_digest,
            "legacy": {
                "rediscovery_count": self.legacy_rediscovery_count,
                "coverage": float(self.legacy_coverage),
                "depth": self.legacy_depth,
                "closed": self.legacy_closed,
            },
            "portfolio": {
                "rediscovery_count": self.portfolio_rediscovery_count,
                "coverage": float(self.portfolio_coverage),
                "depth": self.portfolio_depth,
                "closed": self.portfolio_closed,
            },
            "deltas": {
                "rediscovery": self.portfolio_rediscovery_count - self.legacy_rediscovery_count,
                "coverage": round(float(self.portfolio_coverage) - float(self.legacy_coverage), 6),
                "depth": self.portfolio_depth - self.legacy_depth,
                "decision_closure": int(self.portfolio_closed) - int(self.legacy_closed),
            },
            "limitations": list(self.limitations),
        }


def _method_registry(value: Sequence[MethodBoundary] | MethodRegistry) -> MethodRegistry:
    if isinstance(value, MethodRegistry):
        return value
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SearchPortfolioError("available_methods must be a MethodRegistry or sequence")
    return MethodRegistry(version="inline-v1", boundaries=tuple(value))


def distinct_method_boundaries(boundaries: Sequence[MethodBoundary]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                ":".join(
                    (
                        item.boundary_kind,
                        item.provider_id,
                        item.corpus_id,
                        item.extraction_path,
                        item.failure_boundary or "",
                        item.provenance_group,
                    )
                )
                for item in boundaries
            }
        )
    )


def _records(value: Sequence[Mapping[str, object]], label: str, required: set[str]) -> tuple[dict[str, str], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SearchPortfolioError(f"{label} must be a sequence")
    records: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise SearchPortfolioError(f"{label} entries must be mappings")
        hidden = _HIDDEN_FIELDS.intersection(str(key) for key in item)
        if hidden:
            raise SearchPortfolioError(f"hidden field is not allowed: {sorted(hidden)[0]}")
        if set(item) != required:
            raise SearchPortfolioError(f"{label} entries must contain exactly {sorted(required)}")
        records.append({key: _text(item[key], f"{label}.{key}") for key in required})
    if not records:
        raise SearchPortfolioError(f"{label} must not be empty")
    return tuple(records)


@dataclass(frozen=True, slots=True)
class SearchPortfolio:
    portfolio_id: str
    intent_revision: str
    working_brief_revision: str
    strategy_revision: str
    decision_slot_id: str
    evidence_deficit: str
    authority_envelope: str
    subquestions: tuple[Mapping[str, object], ...]
    query_variants: tuple[Mapping[str, object], ...]
    method_boundaries: tuple[MethodBoundary, ...]
    prior_acquisition_refs: tuple[str, ...]
    stop_criteria: tuple[str, ...]
    replan_triggers: tuple[str, ...]
    method_registry_version: str = "inline-v1"
    method_registry_digest: str = ""
    method_registry_id: str = ""

    def __post_init__(self) -> None:
        for value, label in (
            (self.portfolio_id, "portfolio_id"),
            (self.intent_revision, "intent_revision"),
            (self.working_brief_revision, "working_brief_revision"),
            (self.strategy_revision, "strategy_revision"),
            (self.decision_slot_id, "decision_slot_id"),
            (self.evidence_deficit, "evidence_deficit"),
            (self.authority_envelope, "authority_envelope"),
            (self.method_registry_version, "method_registry_version"),
        ):
            _text(value, label)
        if self.method_registry_digest:
            _text(self.method_registry_digest, "method_registry_digest")
        if self.method_registry_id:
            validate_identifier(self.method_registry_id, "method_registry_id")
        subquestions = _records(
            self.subquestions,
            "subquestions",
            {
                "subquestion_id",
                "category",
                "question",
                "question_origin",
                "originating_deficit",
                "expected_decision_effect",
                "stop_or_replan_trigger",
            },
        )
        queries = _records(
            self.query_variants,
            "query_variants",
            {
                "query_id",
                "subquestion_id",
                "originating_slot_id",
                "query",
                "method_id",
                "provider_id",
                "target_evidence_class",
                "expected_decision_effect",
                "query_rewrite_reason",
            },
        )
        if not isinstance(self.method_boundaries, tuple) or not self.method_boundaries:
            raise SearchPortfolioError("method_boundaries must not be empty")
        if any(not isinstance(item, MethodBoundary) for item in self.method_boundaries):
            raise SearchPortfolioError("method_boundaries must contain MethodBoundary values")
        method_ids = {item.method_id for item in self.method_boundaries}
        if any(query["method_id"] not in method_ids for query in queries):
            raise SearchPortfolioError("query method_id must exist in method_boundaries")
        subquestion_ids = {item["subquestion_id"] for item in subquestions}
        if any(query["subquestion_id"] not in subquestion_ids for query in queries):
            raise SearchPortfolioError("query subquestion_id must exist in subquestions")
        if any(query["originating_slot_id"] != self.decision_slot_id for query in queries):
            raise SearchPortfolioError("query originating_slot_id must match decision_slot_id")
        if any(
            item.fallback_method_id and item.fallback_method_id not in method_ids for item in self.method_boundaries
        ):
            raise SearchPortfolioError("fallback_method_id must exist in method_boundaries")
        object.__setattr__(self, "subquestions", subquestions)
        object.__setattr__(self, "query_variants", queries)
        object.__setattr__(
            self, "prior_acquisition_refs", _strings(self.prior_acquisition_refs, "prior_acquisition_refs")
        )
        object.__setattr__(self, "stop_criteria", _strings(self.stop_criteria, "stop_criteria", required=True))
        object.__setattr__(self, "replan_triggers", _strings(self.replan_triggers, "replan_triggers", required=True))

    def satisfies_independent_methods(self, *, required: int) -> bool:
        return (
            len(distinct_method_boundaries(tuple(item for item in self.method_boundaries if item.available)))
            >= required
        )

    def degraded_methods(self) -> tuple[str, ...]:
        return tuple(item.method_id for item in self.method_boundaries if not item.available)

    def has_single_available_boundary(self) -> bool:
        return len(distinct_method_boundaries(tuple(item for item in self.method_boundaries if item.available))) <= 1

    def to_dict(self) -> dict[str, Any]:
        boundaries = {item.method_id: item for item in self.method_boundaries}
        return _json_value(
            {
                **asdict(self),
                "method_boundaries": [asdict(item) for item in self.method_boundaries],
                "method_selection": [
                    item.selection_record(boundaries, registry_version=self.method_registry_version)
                    for item in self.method_boundaries
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class BatchCoverageAssessment:
    assessment_id: str
    portfolio_id: str
    decision_slot_id: str
    attempt_id: str
    batch_id: str
    coverage: str
    novelty: str
    source_depth: str
    provenance_independence: str
    contradictions: tuple[str, ...]
    implementation_uncertainty: str
    oracle_readiness: str
    unresolved_decision_risk: str
    disposition: str
    causal_refs: tuple[str, ...]
    next_actions: tuple[str, ...]
    capture_refs: tuple[str, ...]
    receipt_refs: tuple[str, ...]
    checkpoint_refs: tuple[str, ...]
    authority_disposition: str = "inside_confirmed_authority"
    superseded_strategy_revision: str | None = None
    successor_strategy_revision: str | None = None
    evidence_disposition: str = "captured"
    alternate_method_available: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.assessment_id, "assessment_id"),
            (self.portfolio_id, "portfolio_id"),
            (self.decision_slot_id, "decision_slot_id"),
            (self.attempt_id, "attempt_id"),
            (self.batch_id, "batch_id"),
            (self.coverage, "coverage"),
            (self.novelty, "novelty"),
            (self.source_depth, "source_depth"),
            (self.provenance_independence, "provenance_independence"),
            (self.implementation_uncertainty, "implementation_uncertainty"),
            (self.oracle_readiness, "oracle_readiness"),
            (self.unresolved_decision_risk, "unresolved_decision_risk"),
        ):
            _text(value, label)
        if self.disposition not in _DISPOSITIONS:
            raise SearchPortfolioError("unsupported disposition")
        if self.authority_disposition not in _AUTHORITY_DISPOSITIONS:
            raise SearchPortfolioError("authority-expanding pivots are not allowed")
        if self.evidence_disposition not in _EVIDENCE_DISPOSITIONS:
            raise SearchPortfolioError("unsupported evidence_disposition")
        if not isinstance(self.alternate_method_available, bool):
            raise SearchPortfolioError("alternate_method_available must be bool")
        for label in (
            "contradictions",
            "causal_refs",
            "next_actions",
            "capture_refs",
            "receipt_refs",
            "checkpoint_refs",
        ):
            object.__setattr__(self, label, _strings(getattr(self, label), label))
        if not self.causal_refs or not self.receipt_refs or not self.checkpoint_refs:
            raise SearchPortfolioError("assessments require receipt, checkpoint, and causal lineage")
        if self.evidence_disposition == "captured" and not self.capture_refs:
            raise SearchPortfolioError("captured assessments require immutable captures")
        if self.evidence_disposition != "captured" and self.capture_refs:
            raise SearchPortfolioError("unavailable assessments must not claim captures")
        if self.disposition == "pivot" and (
            not self.superseded_strategy_revision or not self.successor_strategy_revision
        ):
            raise SearchPortfolioError("pivot requires superseded and successor strategy revisions")
        if self.authority_disposition == "requires_requester_reopen" and self.disposition != "blocked":
            raise SearchPortfolioError("requester-controlled changes require a blocked disposition")

    @property
    def requires_deeper_work(self) -> bool:
        return self.disposition in {"deepen", "broaden", "pivot", "validate"}

    def policy_input(self) -> dict[str, object]:
        """Return a bounded, non-authoritative policy input projection."""
        return {
            "portfolio_id": self.portfolio_id,
            "decision_slot_id": self.decision_slot_id,
            "attempt_id": self.attempt_id,
            "batch_id": self.batch_id,
            "disposition": self.disposition,
            "causal_refs": self.causal_refs,
            "next_actions": self.next_actions,
            "requires_deeper_work": self.requires_deeper_work,
            "evidence_disposition": self.evidence_disposition,
            "alternate_method_available": self.alternate_method_available,
            "unresolved_decision_risk": self.unresolved_decision_risk,
        }

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


def assess_acquisition_batch(
    *,
    assessment_id: str,
    portfolio_id: str,
    decision_slot_id: str,
    attempt_id: str,
    batch_id: str,
    coverage: str,
    novelty: str,
    source_depth: str,
    provenance_independence: str,
    contradictions: Sequence[str],
    implementation_uncertainty: str,
    oracle_readiness: str,
    unresolved_decision_risk: str,
    causal_refs: Sequence[str],
    capture_refs: Sequence[str],
    receipt_refs: Sequence[str],
    checkpoint_refs: Sequence[str],
    superseded_strategy_revision: str | None = None,
    successor_strategy_revision: str | None = None,
    authority_disposition: str = "inside_confirmed_authority",
    evidence_disposition: str = "captured",
    alternate_method_available: bool = False,
) -> BatchCoverageAssessment:
    """Classify a completed batch without granting lifecycle authority."""
    has_contradiction = bool(_strings(contradictions, "contradictions"))
    if authority_disposition == "requires_requester_reopen":
        disposition = "blocked"
        next_actions = ("reopen-human-decision",)
        superseded = successor = None
    elif evidence_disposition != "captured":
        disposition = "broaden" if alternate_method_available else "blocked"
        next_actions = ("switch-to-alternate-method",) if alternate_method_available else ("record-typed-blocker",)
        superseded = successor = None
    elif has_contradiction:
        if not superseded_strategy_revision or not successor_strategy_revision:
            raise SearchPortfolioError("contradiction requires exact superseded and successor strategy revisions")
        disposition = "pivot"
        next_actions = ("create-successor-strategy",)
        superseded = superseded_strategy_revision
        successor = successor_strategy_revision
    elif coverage == "none":
        disposition = "broaden" if alternate_method_available else "blocked"
        next_actions = ("switch-to-alternate-method",) if alternate_method_available else ("record-typed-blocker",)
        superseded = successor = None
    elif source_depth in {"snippet", "summary"} or coverage != "complete":
        disposition = "deepen"
        next_actions = ("open-full-source",)
        superseded = successor = None
    elif oracle_readiness != "ready" or implementation_uncertainty in {"high", "unknown"}:
        disposition = "validate"
        next_actions = ("run-bounded-validation",)
        superseded = successor = None
    else:
        disposition = "sufficient_for_slot"
        next_actions = ("submit-for-closure-assessment",)
        superseded = successor = None
    return BatchCoverageAssessment(
        assessment_id=assessment_id,
        portfolio_id=portfolio_id,
        decision_slot_id=decision_slot_id,
        attempt_id=attempt_id,
        batch_id=batch_id,
        coverage=coverage,
        novelty=novelty,
        source_depth=source_depth,
        provenance_independence=provenance_independence,
        contradictions=tuple(contradictions),
        implementation_uncertainty=implementation_uncertainty,
        oracle_readiness=oracle_readiness,
        unresolved_decision_risk=unresolved_decision_risk,
        disposition=disposition,
        causal_refs=tuple(causal_refs),
        next_actions=next_actions,
        capture_refs=tuple(capture_refs),
        receipt_refs=tuple(receipt_refs),
        checkpoint_refs=tuple(checkpoint_refs),
        authority_disposition=authority_disposition,
        superseded_strategy_revision=superseded,
        successor_strategy_revision=successor,
        evidence_disposition=evidence_disposition,
        alternate_method_available=alternate_method_available,
    )


def derive_search_portfolio(
    *,
    portfolio_id: str,
    intent_revision: str,
    working_brief_revision: str,
    strategy_revision: str,
    decision_slot_id: str,
    slot_question: str,
    evidence_deficit: str,
    authority_envelope: str,
    available_methods: Sequence[MethodBoundary] | MethodRegistry,
    prior_acquisition_refs: Sequence[str] = (),
    prior_outcomes: Sequence[str] = (),
    deficit_dimensions: Sequence[str] = (),
    planning_context: Sequence[str] = (),
) -> SearchPortfolio:
    _text(slot_question, "slot_question")
    normalized_dimensions = _strings(deficit_dimensions, "deficit_dimensions")
    categories = tuple(
        dict.fromkeys(
            (
                "mechanism",
                "implementation",
                *(dimension.replace("_", "-").lower() for dimension in normalized_dimensions if dimension.strip()),
                "validation",
            )
        )
    )
    context = _strings(planning_context, "planning_context")[:8]
    outcomes = _strings(prior_outcomes, "prior_outcomes")[:4]
    context_prefix = " ".join(context)
    outcome_suffix = " ".join(outcomes)
    subquestions = (
        {
            "subquestion_id": f"{portfolio_id}-explicit-slot",
            "category": "slot",
            "question": slot_question,
            "question_origin": "explicit",
            "originating_deficit": evidence_deficit,
            "expected_decision_effect": f"Resolve the requester-stated Slot {decision_slot_id}.",
            "stop_or_replan_trigger": "The Slot closure oracle passes or evidence requires replanning.",
        },
        *(
            {
                "subquestion_id": f"{portfolio_id}-{category}",
                "category": category,
                "question": f"{category.title()} for: {slot_question}",
                "question_origin": "implicit",
                "originating_deficit": evidence_deficit,
                "expected_decision_effect": f"Reduce {category} uncertainty for {decision_slot_id}.",
                "stop_or_replan_trigger": "Primary evidence resolves or contradicts the deficit.",
            }
            for category in categories
        ),
    )
    registry = _method_registry(available_methods)
    methods = registry.boundaries
    usable = tuple(item for item in methods if item.available)
    planned_methods = usable or methods
    queries = tuple(
        {
            "query_id": f"{portfolio_id}-query-{index}",
            "subquestion_id": subquestion["subquestion_id"],
            "originating_slot_id": decision_slot_id,
            "query": " ".join(
                part for part in (context_prefix, slot_question, subquestion["category"], outcome_suffix) if part
            ),
            "method_id": item.method_id,
            "provider_id": item.provider_id,
            "target_evidence_class": item.expected_evidence_class,
            "expected_decision_effect": subquestion["expected_decision_effect"],
            "query_rewrite_reason": (
                "method available for the originating deficit"
                + ("; prior acquisition outcome requires a distinct follow-up" if outcomes else "")
                if item.available
                else f"method unavailable: {item.limitation_code}; retain rejected plan trace"
            ),
        }
        for index, (subquestion, item) in enumerate(
            (pair for subquestion in subquestions for pair in ((subquestion, item) for item in planned_methods)),
            1,
        )
    )
    return SearchPortfolio(
        portfolio_id,
        intent_revision,
        working_brief_revision,
        strategy_revision,
        decision_slot_id,
        evidence_deficit,
        authority_envelope,
        subquestions,
        queries,
        methods,
        tuple(prior_acquisition_refs),
        ("Decision Slot is supported by independent evidence.",),
        ("Contradiction or shallow evidence remains.",),
        registry.version,
        registry.digest,
        registry.registry_id,
    )


def validate_search_portfolio_payload(value: Mapping[str, Any], *, run_id: str | None = None) -> None:
    """Validate the persisted projection consumed by coordinator dispatch."""

    if not isinstance(value, Mapping):
        raise SearchPortfolioError("search portfolio payload must be a mapping")
    required = {
        "schema_version",
        "kind",
        "run_id",
        "portfolio_id",
        "intent_revision",
        "working_brief_revision",
        "strategy_revision",
        "decision_slot_id",
        "evidence_deficit",
        "authority_envelope",
        "subquestions",
        "query_variants",
        "method_boundaries",
        "method_selection",
        "prior_acquisition_refs",
        "stop_criteria",
        "replan_triggers",
        "method_registry_version",
        "method_registry_digest",
        "method_registry_id",
        "lineage",
        "slot_closure_oracle",
        "method_capability",
        "status",
    }
    if set(value) != required:
        raise SearchPortfolioError("search portfolio payload has unexpected fields")
    if value.get("schema_version") != 1 or value.get("kind") != SEARCH_PORTFOLIO_KIND:
        raise SearchPortfolioError("unsupported search portfolio payload")
    try:
        validate_identifier(value.get("run_id"), "run_id")
    except (RuntimeStoreError, TypeError, ValueError) as error:
        raise SearchPortfolioError("search portfolio has invalid run_id") from error
    if run_id is not None and value["run_id"] != run_id:
        raise SearchPortfolioError("search portfolio run_id does not match ledger run")
    if value.get("status") not in {"active", "blocked"}:
        raise SearchPortfolioError("unsupported search portfolio status")
    portfolio = SearchPortfolio(
        portfolio_id=str(value.get("portfolio_id", "")),
        intent_revision=str(value.get("intent_revision", "")),
        working_brief_revision=str(value.get("working_brief_revision", "")),
        strategy_revision=str(value.get("strategy_revision", "")),
        decision_slot_id=str(value.get("decision_slot_id", "")),
        evidence_deficit=str(value.get("evidence_deficit", "")),
        authority_envelope=str(value.get("authority_envelope", "")),
        subquestions=tuple(value.get("subquestions", ())),
        query_variants=tuple(value.get("query_variants", ())),
        method_boundaries=tuple(MethodBoundary(**dict(item)) for item in value.get("method_boundaries", ())),
        prior_acquisition_refs=tuple(value.get("prior_acquisition_refs", ())),
        stop_criteria=tuple(value.get("stop_criteria", ())),
        replan_triggers=tuple(value.get("replan_triggers", ())),
        method_registry_version=str(value.get("method_registry_version", "")),
        method_registry_digest=str(value.get("method_registry_digest", "")),
        method_registry_id=str(value.get("method_registry_id", "")),
    )
    if (
        len(portfolio.method_registry_digest) != 64
        or any(character not in "0123456789abcdef" for character in portfolio.method_registry_digest)
        or not portfolio.method_registry_id
    ):
        raise SearchPortfolioError("search portfolio lacks immutable method registry identity")
    boundaries = {item.method_id: item for item in portfolio.method_boundaries}
    selections = value.get("method_selection")
    if not isinstance(selections, Sequence) or isinstance(selections, (str, bytes)):
        raise SearchPortfolioError("method_selection must be a sequence")
    selection_by_id = {
        item.get("method_id"): item
        for item in selections
        if isinstance(item, Mapping) and isinstance(item.get("method_id"), str)
    }
    if set(selection_by_id) != set(boundaries):
        raise SearchPortfolioError("method selection does not cover registry boundaries")
    for method_id, boundary in boundaries.items():
        expected = boundary.selection_record(boundaries, registry_version=portfolio.method_registry_version)
        if _json_value(selection_by_id[method_id]) != expected:
            raise SearchPortfolioError("method selection does not match registry boundary")
    lineage = value.get("lineage")
    if not isinstance(lineage, Mapping) or set(lineage) != {
        "intent_model_ref",
        "working_brief_ref",
        "strategy_ref",
        "decision_map_ref",
        "method_registry_ref",
        "decision_slot_id",
    }:
        raise SearchPortfolioError("search portfolio lacks exact lineage")
    for name in ("intent_model_ref", "working_brief_ref", "strategy_ref", "decision_map_ref", "method_registry_ref"):
        try:
            ArtifactRef.from_dict(lineage[name])
        except (TypeError, ValueError, RuntimeStoreError) as error:
            raise SearchPortfolioError("search portfolio has invalid lineage") from error
    if lineage["decision_slot_id"] != portfolio.decision_slot_id:
        raise SearchPortfolioError("search portfolio slot lineage does not match payload")
    capability = value.get("method_capability")
    if (
        not isinstance(capability, Mapping)
        or capability.get("method_registry_version") != portfolio.method_registry_version
    ):
        raise SearchPortfolioError("search portfolio lacks method capability projection")
    active = any(item.available for item in boundaries.values())
    if (value["status"] == "active") != active:
        raise SearchPortfolioError("search portfolio status does not match method availability")


class SearchPortfolioService:
    """Persist portfolio and batch-assessment artifacts in the canonical ledger."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise SearchPortfolioError("SearchPortfolioService requires a RunLedger")
        self.ledger = ledger

    def register_methods(
        self,
        *,
        run_id: str,
        registry: MethodRegistry,
        expected_revision: int,
    ) -> ArtifactRevision:
        """Persist immutable method declarations before a portfolio selects them."""

        run_id = validate_identifier(run_id, "run_id")
        if not isinstance(registry, MethodRegistry):
            raise SearchPortfolioError("registry must be a MethodRegistry")
        payload = {
            "schema_version": 1,
            "kind": METHOD_REGISTRY_KIND,
            "run_id": run_id,
            **registry.to_dict(),
        }
        return self._append_once(
            run_id=run_id,
            artifact_id=registry.registry_id,
            kind=METHOD_REGISTRY_KIND,
            payload=payload,
            parent_refs=(),
            expected_revision=expected_revision,
        )

    def plan(
        self,
        *,
        run_id: str,
        portfolio_id: str,
        intent_model: ArtifactRevision,
        working_brief: ArtifactRevision,
        strategy: ArtifactRevision,
        decision_map: ArtifactRevision,
        slot: DecisionSlotDeficit | Mapping[str, Any],
        authority_envelope: str,
        available_methods: Sequence[MethodBoundary] | MethodRegistry,
        method_registry: ArtifactRevision | None = None,
        prior_acquisition_refs: Sequence[ArtifactRevision | ArtifactRef] = (),
        expected_revision: int,
    ) -> ArtifactRevision:
        """Persist one portfolio before acquisition dispatch can consume it."""

        run_id = validate_identifier(run_id, "run_id")
        portfolio_id = validate_identifier(portfolio_id, "portfolio_id")
        intent = self._current_artifact(intent_model, run_id, "intent-model", "intent_model")
        brief = self._current_artifact(working_brief, run_id, "working-brief", "working_brief")
        current_strategy = self._current_artifact(strategy, run_id, "strategy-projection", "strategy")
        target = self._current_artifact(decision_map, run_id, "blueprint-target", "decision_map")
        intent_ref = _artifact_ref(intent)
        brief_ref = _artifact_ref(brief)
        strategy_ref = _artifact_ref(current_strategy)
        target_ref = _artifact_ref(target)
        if intent_ref not in brief.parent_refs:
            raise SearchPortfolioError("working_brief lacks exact intent lineage")
        if target_ref not in current_strategy.parent_refs:
            raise SearchPortfolioError("strategy lacks exact decision map lineage")
        if brief_ref not in target.parent_refs or intent_ref not in target.parent_refs:
            raise SearchPortfolioError("decision_map lacks exact brief and intent lineage")
        slot_deficit = DecisionSlotDeficit.from_value(slot)
        self._validate_slot(target, slot_deficit)
        previous = self._prior_acquisition_artifacts(prior_acquisition_refs, run_id)
        registry = _method_registry(available_methods)
        registry_artifact, plan_revision = self._resolve_registry(
            method_registry,
            registry,
            run_id,
            expected_revision=expected_revision,
        )
        portfolio = derive_search_portfolio(
            portfolio_id=portfolio_id,
            intent_revision=_reference_label(intent_ref),
            working_brief_revision=_reference_label(brief_ref),
            strategy_revision=_reference_label(strategy_ref),
            decision_slot_id=slot_deficit.slot_id,
            slot_question=slot_deficit.question,
            evidence_deficit=self._evidence_deficit(slot_deficit),
            authority_envelope=authority_envelope,
            available_methods=registry,
            prior_acquisition_refs=tuple(_reference_label(_artifact_ref(item)) for item in previous),
            prior_outcomes=self._prior_outcomes(previous),
            deficit_dimensions=slot_deficit.missing_dimensions,
            planning_context=self._planning_context(intent, brief, target, current_strategy, slot_deficit),
        )
        payload = {
            "schema_version": 1,
            "kind": SEARCH_PORTFOLIO_KIND,
            "run_id": run_id,
            **portfolio.to_dict(),
            "lineage": {
                "intent_model_ref": intent_ref.to_dict(),
                "working_brief_ref": brief_ref.to_dict(),
                "strategy_ref": strategy_ref.to_dict(),
                "decision_map_ref": target_ref.to_dict(),
                "method_registry_ref": _artifact_ref(registry_artifact).to_dict(),
                "decision_slot_id": slot_deficit.slot_id,
            },
            "slot_closure_oracle": slot_deficit.closure_oracle,
            "method_capability": self._method_capability(
                portfolio.method_boundaries,
                registry_version=portfolio.method_registry_version,
            ),
            "status": "active" if any(item.available for item in portfolio.method_boundaries) else "blocked",
        }
        parents = (
            intent_ref,
            brief_ref,
            strategy_ref,
            target_ref,
            _artifact_ref(registry_artifact),
            *(_artifact_ref(item) for item in previous),
        )
        validate_search_portfolio_payload(payload, run_id=run_id)
        return self._append_once(
            run_id=run_id,
            artifact_id=portfolio_id,
            kind=SEARCH_PORTFOLIO_KIND,
            payload=payload,
            parent_refs=parents,
            expected_revision=plan_revision,
        )

    def record_assessment(
        self,
        *,
        run_id: str,
        assessment: BatchCoverageAssessment,
        portfolio_ref: ArtifactRef,
        capture_artifacts: Sequence[ArtifactRevision],
        receipt_artifacts: Sequence[ArtifactRevision],
        checkpoint_artifacts: Sequence[ArtifactRevision],
        expected_revision: int,
        successor_strategy: ArtifactRevision | None = None,
    ) -> ArtifactRevision:
        """Persist a batch decision with immutable capture/checkpoint lineage."""

        run_id = validate_identifier(run_id, "run_id")
        if not isinstance(assessment, BatchCoverageAssessment):
            raise SearchPortfolioError("assessment must be a BatchCoverageAssessment")
        portfolio = self._stored_artifact(portfolio_ref, run_id, SEARCH_PORTFOLIO_KIND, "portfolio_ref")
        if not self.ledger.is_latest_artifact(portfolio_ref) or portfolio.payload.get("status") != "active":
            raise SearchPortfolioError("portfolio_ref must identify an active current portfolio")
        validate_search_portfolio_payload(_artifact_payload(portfolio))
        self._validate_portfolio_registry(run_id, portfolio)
        if portfolio.id != assessment.portfolio_id:
            raise SearchPortfolioError("assessment portfolio_id does not match portfolio_ref")
        if portfolio.payload.get("decision_slot_id") != assessment.decision_slot_id:
            raise SearchPortfolioError("assessment decision_slot_id does not match portfolio")
        captures = self._bound_artifacts(
            capture_artifacts,
            run_id,
            "source-capture",
            "capture_artifacts",
            required=assessment.evidence_disposition == "captured",
        )
        receipts = self._bound_artifacts(receipt_artifacts, run_id, "acquisition-receipt", "receipt_artifacts")
        checkpoints = self._bound_artifacts(
            checkpoint_artifacts,
            run_id,
            "analysis-checkpoint",
            "checkpoint_artifacts",
        )
        self._validate_assessment_refs(assessment, captures, receipts, checkpoints)
        if any(self._capture_attempt(item) != assessment.attempt_id for item in captures):
            raise SearchPortfolioError("assessment captures do not match attempt_id")
        if any(self._receipt_attempt(item) != assessment.attempt_id for item in receipts):
            raise SearchPortfolioError("assessment receipts do not match attempt_id")
        if any(self._checkpoint_attempt(item) != assessment.attempt_id for item in checkpoints):
            raise SearchPortfolioError("assessment checkpoints do not match attempt_id")
        self._validate_artifact_lineage(assessment, captures, receipts, checkpoints)
        strategy_parent = self._pivot_strategy_parent(
            run_id,
            portfolio,
            assessment,
            successor_strategy,
        )
        parents = (
            portfolio_ref,
            *(_artifact_ref(item) for item in captures),
            *(_artifact_ref(item) for item in receipts),
            *(_artifact_ref(item) for item in checkpoints),
            *((strategy_parent,) if strategy_parent is not None else ()),
        )
        payload = {
            "schema_version": 1,
            "kind": BATCH_COVERAGE_ASSESSMENT_KIND,
            "run_id": run_id,
            "portfolio_ref": portfolio_ref.to_dict(),
            "assessment": assessment.to_dict(),
            "status": "recorded",
        }
        return self._append_once(
            run_id=run_id,
            artifact_id=validate_identifier(assessment.assessment_id, "assessment_id"),
            kind=BATCH_COVERAGE_ASSESSMENT_KIND,
            payload=payload,
            parent_refs=parents,
            expected_revision=expected_revision,
        )

    def validate_persisted_portfolio(
        self,
        *,
        run_id: str,
        portfolio_ref: ArtifactRef,
    ) -> ArtifactRevision:
        """Validate a portfolio and its immutable method-registry parent."""

        run_id = validate_identifier(run_id, "run_id")
        portfolio = self._stored_artifact(portfolio_ref, run_id, SEARCH_PORTFOLIO_KIND, "portfolio_ref")
        validate_search_portfolio_payload(_artifact_payload(portfolio), run_id=run_id)
        self._validate_portfolio_registry(run_id, portfolio)
        return portfolio

    def validate_recorded_assessment(
        self,
        *,
        run_id: str,
        assessment_ref: ArtifactRef,
        portfolio_ref: ArtifactRef,
        attempt_id: str,
        expected_method_id: str | None = None,
        expected_provider_id: str | None = None,
    ) -> ArtifactRevision:
        """Validate a persisted assessment before a worker completion consumes it."""

        run_id = validate_identifier(run_id, "run_id")
        portfolio = self.validate_persisted_portfolio(run_id=run_id, portfolio_ref=portfolio_ref)
        if not self.ledger.is_latest_artifact(portfolio_ref) or portfolio.payload.get("status") != "active":
            raise SearchPortfolioError("portfolio_ref must identify an active current portfolio")
        artifact = self._stored_artifact(
            assessment_ref,
            run_id,
            BATCH_COVERAGE_ASSESSMENT_KIND,
            "assessment_ref",
        )
        if not self.ledger.is_latest_artifact(assessment_ref):
            raise SearchPortfolioError("assessment_ref must identify a current assessment")
        payload = _artifact_payload(artifact)
        if set(payload) != {"schema_version", "kind", "run_id", "portfolio_ref", "assessment", "status"}:
            raise SearchPortfolioError("assessment payload has unexpected fields")
        if (
            payload.get("schema_version") != 1
            or payload.get("kind") != BATCH_COVERAGE_ASSESSMENT_KIND
            or payload.get("run_id") != run_id
            or payload.get("status") != "recorded"
        ):
            raise SearchPortfolioError("unsupported assessment payload")
        try:
            recorded_portfolio_ref = ArtifactRef.from_dict(payload["portfolio_ref"])
            assessment = BatchCoverageAssessment(**dict(payload["assessment"]))
        except (KeyError, TypeError, ValueError, RuntimeStoreError) as error:
            raise SearchPortfolioError("assessment payload is invalid") from error
        if recorded_portfolio_ref != portfolio_ref or portfolio_ref not in artifact.parent_refs:
            raise SearchPortfolioError("assessment lacks exact portfolio lineage")
        if artifact.id != assessment.assessment_id or assessment.attempt_id != attempt_id:
            raise SearchPortfolioError("assessment does not match worker attempt")
        captures = self._assessment_parent_artifacts(
            artifact,
            assessment.capture_refs,
            run_id,
            "source-capture",
            "capture_refs",
            required=assessment.evidence_disposition == "captured",
        )
        receipts = self._assessment_parent_artifacts(
            artifact,
            assessment.receipt_refs,
            run_id,
            "acquisition-receipt",
            "receipt_refs",
        )
        checkpoints = self._assessment_parent_artifacts(
            artifact,
            assessment.checkpoint_refs,
            run_id,
            "analysis-checkpoint",
            "checkpoint_refs",
        )
        if (
            portfolio.id != assessment.portfolio_id
            or portfolio.payload.get("decision_slot_id") != assessment.decision_slot_id
        ):
            raise SearchPortfolioError("assessment does not match portfolio")
        if any(self._capture_attempt(item) != attempt_id for item in captures):
            raise SearchPortfolioError("assessment captures do not match attempt_id")
        if any(self._receipt_attempt(item) != attempt_id for item in receipts):
            raise SearchPortfolioError("assessment receipts do not match attempt_id")
        if any(self._checkpoint_attempt(item) != attempt_id for item in checkpoints):
            raise SearchPortfolioError("assessment checkpoints do not match attempt_id")
        self._validate_assessment_refs(assessment, captures, receipts, checkpoints)
        self._validate_artifact_lineage(
            assessment,
            captures,
            receipts,
            checkpoints,
            expected_method_id=expected_method_id,
            expected_provider_id=expected_provider_id,
        )
        return artifact

    def _current_artifact(
        self,
        value: ArtifactRevision,
        run_id: str,
        kind: str,
        label: str,
    ) -> ArtifactRevision:
        if not isinstance(value, ArtifactRevision):
            raise SearchPortfolioError(f"{label} must be an ArtifactRevision")
        result = self._stored_artifact(_artifact_ref(value), run_id, kind, label)
        if not self.ledger.is_latest_artifact(_artifact_ref(result)):
            raise SearchPortfolioError(f"{label} is stale")
        return result

    def _resolve_registry(
        self,
        value: ArtifactRevision | None,
        registry: MethodRegistry,
        run_id: str,
        *,
        expected_revision: int,
    ) -> tuple[ArtifactRevision, int]:
        if value is None:
            if self.ledger.get_revision(run_id) != expected_revision:
                raise SearchPortfolioError("stale ledger revision")
            artifact = self.register_methods(
                run_id=run_id,
                registry=registry,
                expected_revision=expected_revision,
            )
            return artifact, self.ledger.get_revision(run_id)
        artifact = self._current_artifact(value, run_id, METHOD_REGISTRY_KIND, "method_registry")
        payload = _artifact_payload(artifact)
        if (
            payload.get("registry_id") != registry.registry_id
            or payload.get("version") != registry.version
            or payload.get("digest") != registry.digest
            or payload.get("boundaries") != [_json_value(asdict(item)) for item in registry.boundaries]
        ):
            raise SearchPortfolioError("method_registry does not match selected registry")
        return artifact, expected_revision

    def _validate_portfolio_registry(self, run_id: str, portfolio: ArtifactRevision) -> None:
        payload = _artifact_payload(portfolio)
        lineage = payload.get("lineage")
        if not isinstance(lineage, Mapping):
            raise SearchPortfolioError("portfolio lacks method registry lineage")
        try:
            registry_ref = ArtifactRef.from_dict(lineage["method_registry_ref"])
            registry_artifact = self._stored_artifact(
                registry_ref,
                run_id,
                METHOD_REGISTRY_KIND,
                "method_registry_ref",
            )
            registry_payload = _artifact_payload(registry_artifact)
            registry = MethodRegistry(
                registry_id=str(registry_payload["registry_id"]),
                version=str(registry_payload["version"]),
                boundaries=tuple(MethodBoundary(**dict(item)) for item in registry_payload["boundaries"]),
            )
        except (KeyError, TypeError, ValueError, RuntimeStoreError) as error:
            raise SearchPortfolioError("portfolio method registry is invalid") from error
        expected_registry_payload = {
            "schema_version": 1,
            "kind": METHOD_REGISTRY_KIND,
            "run_id": run_id,
            **registry.to_dict(),
        }
        if (
            not self.ledger.is_latest_artifact(registry_ref)
            or registry_ref not in portfolio.parent_refs
            or registry_payload != expected_registry_payload
            or payload.get("method_registry_id") != registry.registry_id
            or payload.get("method_registry_version") != registry.version
            or payload.get("method_registry_digest") != registry.digest
            or payload.get("method_boundaries") != expected_registry_payload["boundaries"]
        ):
            raise SearchPortfolioError("portfolio method registry does not match immutable parent")

    def _stored_artifact(self, reference: ArtifactRef, run_id: str, kind: str, label: str) -> ArtifactRevision:
        if not isinstance(reference, ArtifactRef) or reference.round_id != run_id:
            raise SearchPortfolioError(f"{label} must be an exact reference in the run")
        try:
            artifact = self.ledger.get_artifact(reference)
        except (RuntimeStoreError, LedgerIntegrityError) as error:
            raise SearchPortfolioError(f"{label} is unresolved") from error
        if artifact.kind != kind:
            raise SearchPortfolioError(f"{label} must identify {kind}")
        return artifact

    @staticmethod
    def _receipt_attempt(artifact: ArtifactRevision) -> str:
        payload = _artifact_payload(artifact)
        attempt_id = payload.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise SearchPortfolioError("receipt artifact lacks attempt_id")
        return attempt_id

    @staticmethod
    def _checkpoint_attempt(artifact: ArtifactRevision) -> str:
        payload = _artifact_payload(artifact)
        attempt_id = payload.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise SearchPortfolioError("checkpoint artifact lacks attempt_id")
        return attempt_id

    @staticmethod
    def _capture_attempt(artifact: ArtifactRevision) -> str:
        payload = _artifact_payload(artifact)
        attempt_id = payload.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise SearchPortfolioError("capture artifact lacks attempt_id")
        return attempt_id

    def _prior_acquisition_artifacts(
        self,
        values: Sequence[ArtifactRevision | ArtifactRef],
        run_id: str,
    ) -> tuple[ArtifactRevision, ...]:
        allowed = {
            "source-capture",
            "acquisition-receipt",
            "analysis-checkpoint",
            BATCH_COVERAGE_ASSESSMENT_KIND,
        }
        result: list[ArtifactRevision] = []
        for index, value in enumerate(values):
            reference = _artifact_ref(value) if isinstance(value, ArtifactRevision) else value
            if not isinstance(reference, ArtifactRef) or reference.round_id != run_id:
                raise SearchPortfolioError(f"prior_acquisition_refs[{index}] must belong to the run")
            try:
                artifact = self.ledger.get_artifact(reference)
            except (RuntimeStoreError, LedgerIntegrityError) as error:
                raise SearchPortfolioError(f"prior_acquisition_refs[{index}] is unresolved") from error
            if artifact.kind not in allowed:
                raise SearchPortfolioError(f"prior_acquisition_refs[{index}] is not acquisition lineage")
            result.append(artifact)
        refs = tuple(_artifact_ref(item) for item in result)
        if len(set(refs)) != len(refs):
            raise SearchPortfolioError("prior_acquisition_refs must not contain duplicates")
        return tuple(result)

    def _bound_artifacts(
        self,
        values: Sequence[ArtifactRevision],
        run_id: str,
        kind: str,
        label: str,
        *,
        required: bool = True,
    ) -> tuple[ArtifactRevision, ...]:
        result: list[ArtifactRevision] = []
        for index, value in enumerate(values):
            if not isinstance(value, ArtifactRevision):
                raise SearchPortfolioError(f"{label}[{index}] must be an ArtifactRevision")
            result.append(self._stored_artifact(_artifact_ref(value), run_id, kind, f"{label}[{index}]"))
        refs = tuple(_artifact_ref(item) for item in result)
        if (required and not refs) or len(set(refs)) != len(refs):
            raise SearchPortfolioError(f"{label} must contain unique immutable artifacts")
        return tuple(result)

    def _assessment_parent_artifacts(
        self,
        assessment_artifact: ArtifactRevision,
        labels: Sequence[str],
        run_id: str,
        kind: str,
        label: str,
        *,
        required: bool = True,
    ) -> tuple[ArtifactRevision, ...]:
        refs_by_label = {_reference_label(reference): reference for reference in assessment_artifact.parent_refs}
        refs = []
        for item in labels:
            reference = refs_by_label.get(item)
            if reference is None:
                raise SearchPortfolioError(f"assessment {label} lack immutable parent lineage")
            refs.append(reference)
        if (required and not refs) or len(set(refs)) != len(refs):
            raise SearchPortfolioError(f"assessment {label} must contain unique immutable artifacts")
        return tuple(self._stored_artifact(reference, run_id, kind, f"assessment {label}") for reference in refs)

    @staticmethod
    def _prior_outcomes(values: Sequence[ArtifactRevision]) -> tuple[str, ...]:
        result: list[str] = []
        for item in values:
            payload = _artifact_payload(item)
            if item.kind == BATCH_COVERAGE_ASSESSMENT_KIND:
                assessment = payload.get("assessment")
                if isinstance(assessment, Mapping):
                    disposition = assessment.get("disposition")
                    evidence_disposition = assessment.get("evidence_disposition")
                    if isinstance(disposition, str) and disposition.strip():
                        result.append(f"prior disposition {disposition.strip()}")
                    if isinstance(evidence_disposition, str) and evidence_disposition != "captured":
                        result.append(f"prior evidence {evidence_disposition}")
            elif item.kind == "acquisition-receipt":
                status = payload.get("status")
                if isinstance(status, str) and status in {"failed", "blocked", "unknown"}:
                    result.append(f"prior receipt {status}")
        return tuple(dict.fromkeys(result))

    def _pivot_strategy_parent(
        self,
        run_id: str,
        portfolio: ArtifactRevision,
        assessment: BatchCoverageAssessment,
        successor_strategy: ArtifactRevision | None,
    ) -> ArtifactRef | None:
        if assessment.disposition != "pivot":
            if successor_strategy is not None:
                raise SearchPortfolioError("successor_strategy is only valid for pivot assessments")
            return None
        lineage = portfolio.payload.get("lineage")
        if not isinstance(lineage, Mapping):
            raise SearchPortfolioError("portfolio lacks strategy lineage")
        try:
            prior_ref = ArtifactRef.from_dict(lineage["strategy_ref"])
        except (KeyError, TypeError, ValueError) as error:
            raise SearchPortfolioError("portfolio lacks valid strategy lineage") from error
        if prior_ref.round_id != run_id or assessment.superseded_strategy_revision != _reference_label(prior_ref):
            raise SearchPortfolioError("pivot superseded strategy does not match portfolio lineage")
        if not isinstance(successor_strategy, ArtifactRevision):
            raise SearchPortfolioError("pivot requires persisted successor_strategy")
        successor = self._current_artifact(successor_strategy, run_id, "strategy-projection", "successor_strategy")
        successor_ref = _artifact_ref(successor)
        if prior_ref not in successor.parent_refs:
            raise SearchPortfolioError("successor_strategy lacks superseded strategy lineage")
        if assessment.successor_strategy_revision != _reference_label(successor_ref):
            raise SearchPortfolioError("pivot successor strategy does not match persisted successor")
        return successor_ref

    @staticmethod
    def _validate_slot(target: ArtifactRevision, slot: DecisionSlotDeficit) -> None:
        payload = _artifact_payload(target)
        candidates = payload.get("slots", payload.get("decision_slots", ()))
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise SearchPortfolioError("decision_map has invalid slots")
        for candidate in candidates:
            if isinstance(candidate, Mapping) and candidate.get("id", candidate.get("slot_id")) == slot.slot_id:
                question = candidate.get("question")
                if isinstance(question, str) and question.strip() and question.strip() != slot.question:
                    raise SearchPortfolioError("decision slot question does not match decision_map")
                return
        raise SearchPortfolioError("decision_slot_id is absent from decision_map")

    @staticmethod
    def _evidence_deficit(slot: DecisionSlotDeficit) -> str:
        dimensions = ", ".join(slot.missing_dimensions) or "decision evidence"
        return f"Open decision slot requires {dimensions}: {slot.question}"

    @staticmethod
    def _planning_context(
        intent: ArtifactRevision,
        brief: ArtifactRevision,
        target: ArtifactRevision,
        strategy: ArtifactRevision,
        slot: DecisionSlotDeficit,
    ) -> tuple[str, ...]:
        intent_payload = _artifact_payload(intent)
        brief_payload = _artifact_payload(brief)
        target_payload = _artifact_payload(target)
        strategy_payload = _artifact_payload(strategy)
        slot_payload = next(
            (
                candidate
                for candidate in target_payload.get("slots", target_payload.get("decision_slots", ()))
                if isinstance(candidate, Mapping) and candidate.get("id", candidate.get("slot_id")) == slot.slot_id
            ),
            {},
        )
        selected = (
            intent_payload.get("desired_outcomes", ()),
            intent_payload.get("hypotheses", ()),
            brief_payload.get("working_interpretation", ""),
            brief_payload.get("technical_outcome", ""),
            brief_payload.get("retained_hard_constraints", ()),
            strategy_payload.get("current_understanding", ""),
            slot_payload.get("bounded_research_need", "") if isinstance(slot_payload, Mapping) else "",
            slot_payload.get("closure_rule", "") if isinstance(slot_payload, Mapping) else "",
        )
        values = tuple(dict.fromkeys(_planning_text(selected)))
        return values[:8]

    @staticmethod
    def _method_capability(
        boundaries: Sequence[MethodBoundary],
        *,
        registry_version: str,
    ) -> dict[str, Any]:
        unavailable = [item.method_id for item in boundaries if not item.available]
        available_count = len(distinct_method_boundaries([item for item in boundaries if item.available]))
        return {
            "method_registry_version": registry_version,
            "available_boundary_count": available_count,
            "degraded_method_ids": unavailable,
            "degraded": bool(unavailable) or available_count <= 1,
            "blocking_reason": "no_available_method_boundary" if not available_count else None,
        }

    @staticmethod
    def _validate_assessment_refs(
        assessment: BatchCoverageAssessment,
        captures: Sequence[ArtifactRevision],
        receipts: Sequence[ArtifactRevision],
        checkpoints: Sequence[ArtifactRevision],
    ) -> None:
        expected_capture = {_reference_label(_artifact_ref(item)) for item in captures}
        expected_receipt = {_reference_label(_artifact_ref(item)) for item in receipts}
        expected_checkpoint = {_reference_label(_artifact_ref(item)) for item in checkpoints}
        if set(assessment.capture_refs) != expected_capture:
            raise SearchPortfolioError("assessment capture_refs do not match immutable captures")
        if set(assessment.receipt_refs) != expected_receipt:
            raise SearchPortfolioError("assessment receipt_refs do not match immutable receipts")
        if set(assessment.checkpoint_refs) != expected_checkpoint:
            raise SearchPortfolioError("assessment checkpoint_refs do not match immutable checkpoints")
        required = expected_capture | expected_receipt | expected_checkpoint
        if set(assessment.causal_refs) != required:
            raise SearchPortfolioError("assessment causal_refs must exactly match artifact lineage")

    def _validate_artifact_lineage(
        self,
        assessment: BatchCoverageAssessment,
        captures: Sequence[ArtifactRevision],
        receipts: Sequence[ArtifactRevision],
        checkpoints: Sequence[ArtifactRevision],
        *,
        expected_method_id: str | None = None,
        expected_provider_id: str | None = None,
    ) -> None:
        if expected_method_id is not None:
            _text(expected_method_id, "expected_method_id")
        if expected_provider_id is not None:
            _text(expected_provider_id, "expected_provider_id")
        capture_refs = {_artifact_ref(item) for item in captures}
        capture_by_ref: dict[ArtifactRef, SourceCapture] = {}
        for artifact in captures:
            reference = _artifact_ref(artifact)
            try:
                capture = SourceCapture.from_dict(_artifact_payload(artifact))
                content = self.ledger.get_bound_content(reference)
            except (LedgerIntegrityError, TypeError, ValueError) as error:
                raise SearchPortfolioError("assessment capture lacks committed content binding") from error
            if (
                capture.capture_id != artifact.id
                or capture.run_id != artifact.round_id
                or capture.attempt_id != assessment.attempt_id
                or capture.status != "committed"
                or content.digest != capture.content_digest
                or content.media_type != capture.media_type
                or content.byte_size != capture.size_bytes
                or content.availability != "available"
                or expected_method_id is not None
                and capture.method_id != expected_method_id
                or expected_provider_id is not None
                and capture.provider_id != expected_provider_id
            ):
                raise SearchPortfolioError("assessment capture lacks committed content binding")
            capture_by_ref[reference] = capture
        for receipt in receipts:
            try:
                value = AcquisitionReceipt.from_dict(_artifact_payload(receipt))
            except (TypeError, ValueError) as error:
                raise SearchPortfolioError("assessment receipt has invalid acquisition payload") from error
            if (
                value.receipt_id != receipt.id
                or value.attempt_id != assessment.attempt_id
                or expected_method_id is not None
                and value.method_id != expected_method_id
                or expected_provider_id is not None
                and value.provider_id != expected_provider_id
            ):
                raise SearchPortfolioError("assessment receipt does not match attempt_id")
            if assessment.evidence_disposition == "captured":
                matching = [
                    (reference, capture)
                    for reference, capture in capture_by_ref.items()
                    if capture.capture_id == value.capture_id
                ]
                if len(matching) != 1:
                    raise SearchPortfolioError("captured assessment receipt lacks bound source capture")
                capture_ref, capture = matching[0]
                if (
                    value.status != "succeeded"
                    or value.method_id != capture.method_id
                    or value.provider_id != capture.provider_id
                    or receipt.parent_refs != (capture_ref,)
                ):
                    raise SearchPortfolioError("captured assessment receipt lacks capture parent")
            elif (
                value.capture_id is not None
                or value.status not in {"failed", "blocked", "unknown"}
                or not value.failure_history
                or receipt.parent_refs
            ):
                raise SearchPortfolioError("unavailable assessment receipt must not claim capture lineage")
        for checkpoint in checkpoints:
            try:
                value = AnalysisCheckpoint.from_dict(_artifact_payload(checkpoint))
                checkpoint_refs = tuple(
                    ArtifactRef.from_dict(reference) if isinstance(reference, Mapping) else reference
                    for reference in value.source_capture_refs
                )
            except (TypeError, ValueError) as error:
                raise SearchPortfolioError("checkpoint has invalid source capture refs") from error
            if (
                value.checkpoint_id != checkpoint.id
                or value.run_id != checkpoint.round_id
                or value.attempt_id != assessment.attempt_id
            ):
                raise SearchPortfolioError("checkpoint does not match assessment attempt")
            if assessment.evidence_disposition == "captured":
                if (
                    any(not isinstance(reference, ArtifactRef) for reference in checkpoint_refs)
                    or set(checkpoint_refs) != capture_refs
                    or set(checkpoint.parent_refs) != capture_refs
                ):
                    raise SearchPortfolioError("checkpoint lacks exact captured source lineage")
            elif checkpoint_refs or checkpoint.parent_refs:
                raise SearchPortfolioError("unavailable assessment checkpoint must not claim source capture lineage")

    def _append_once(
        self,
        *,
        run_id: str,
        artifact_id: str,
        kind: str,
        payload: Mapping[str, Any],
        parent_refs: Sequence[ArtifactRef],
        expected_revision: int,
    ) -> ArtifactRevision:
        existing = [
            item for item in self.ledger.load_run(run_id).artifacts if item.id == artifact_id and item.kind == kind
        ]
        if existing:
            latest = max(existing, key=lambda item: item.revision)
            if _artifact_payload(latest) != dict(payload) or latest.parent_refs != tuple(parent_refs):
                raise SearchPortfolioError(f"{kind} id conflict")
            return latest
        try:
            return self.ledger.append_artifact(
                run_id,
                artifact_id,
                kind,
                dict(payload),
                parent_refs=tuple(parent_refs),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise SearchPortfolioError("stale ledger revision") from error
