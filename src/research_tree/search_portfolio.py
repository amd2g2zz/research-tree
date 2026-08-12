"""Intent-derived, host-neutral acquisition portfolio contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


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


class SearchPortfolioError(ValueError):
    """A portfolio violates its lineage or authority boundary."""


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


def distinct_method_boundaries(boundaries: Sequence[MethodBoundary]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {f"{item.boundary_kind}:{item.provider_id}:{item.corpus_id}:{item.provenance_group}" for item in boundaries}
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

    def __post_init__(self) -> None:
        for value, label in (
            (self.portfolio_id, "portfolio_id"),
            (self.intent_revision, "intent_revision"),
            (self.working_brief_revision, "working_brief_revision"),
            (self.strategy_revision, "strategy_revision"),
            (self.decision_slot_id, "decision_slot_id"),
            (self.evidence_deficit, "evidence_deficit"),
            (self.authority_envelope, "authority_envelope"),
        ):
            _text(value, label)
        subquestions = _records(
            self.subquestions,
            "subquestions",
            {
                "subquestion_id",
                "category",
                "question",
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
                "query",
                "method_id",
                "provider_id",
                "target_evidence_class",
                "expected_decision_effect",
            },
        )
        if not isinstance(self.method_boundaries, tuple) or not self.method_boundaries:
            raise SearchPortfolioError("method_boundaries must not be empty")
        if any(not isinstance(item, MethodBoundary) for item in self.method_boundaries):
            raise SearchPortfolioError("method_boundaries must contain MethodBoundary values")
        method_ids = {item.method_id for item in self.method_boundaries}
        if any(query["method_id"] not in method_ids for query in queries):
            raise SearchPortfolioError("query method_id must exist in method_boundaries")
        object.__setattr__(self, "subquestions", subquestions)
        object.__setattr__(self, "query_variants", queries)
        object.__setattr__(
            self, "prior_acquisition_refs", _strings(self.prior_acquisition_refs, "prior_acquisition_refs")
        )
        object.__setattr__(self, "stop_criteria", _strings(self.stop_criteria, "stop_criteria", required=True))
        object.__setattr__(self, "replan_triggers", _strings(self.replan_triggers, "replan_triggers", required=True))

    def satisfies_independent_methods(self, *, required: int) -> bool:
        return len(distinct_method_boundaries(self.method_boundaries)) >= required

    def degraded_methods(self) -> tuple[str, ...]:
        return tuple(item.method_id for item in self.method_boundaries if not item.available)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "method_boundaries": [asdict(item) for item in self.method_boundaries]}


@dataclass(frozen=True, slots=True)
class BatchCoverageAssessment:
    assessment_id: str
    portfolio_id: str
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

    def __post_init__(self) -> None:
        for value, label in (
            (self.assessment_id, "assessment_id"),
            (self.portfolio_id, "portfolio_id"),
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
        if self.authority_disposition != "inside_confirmed_authority":
            raise SearchPortfolioError("authority-expanding pivots are not allowed")
        for label in (
            "contradictions",
            "causal_refs",
            "next_actions",
            "capture_refs",
            "receipt_refs",
            "checkpoint_refs",
        ):
            object.__setattr__(self, label, _strings(getattr(self, label), label))
        if not self.causal_refs or not self.capture_refs or not self.receipt_refs or not self.checkpoint_refs:
            raise SearchPortfolioError("assessments require capture, receipt, checkpoint, and causal lineage")
        if self.disposition == "pivot" and (
            not self.superseded_strategy_revision or not self.successor_strategy_revision
        ):
            raise SearchPortfolioError("pivot requires superseded and successor strategy revisions")

    @property
    def requires_deeper_work(self) -> bool:
        return self.disposition in {"deepen", "broaden", "pivot", "validate"}

    def policy_input(self) -> dict[str, object]:
        """Return a bounded, non-authoritative policy input projection."""
        return {
            "portfolio_id": self.portfolio_id,
            "batch_id": self.batch_id,
            "disposition": self.disposition,
            "causal_refs": self.causal_refs,
            "next_actions": self.next_actions,
            "requires_deeper_work": self.requires_deeper_work,
        }


def assess_acquisition_batch(
    *,
    assessment_id: str,
    portfolio_id: str,
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
    authority_disposition: str = "inside_confirmed_authority",
) -> BatchCoverageAssessment:
    """Classify a completed batch without granting lifecycle authority."""
    has_contradiction = bool(_strings(contradictions, "contradictions"))
    if has_contradiction:
        disposition = "pivot"
        next_actions = ("create-successor-strategy",)
        superseded = "active-strategy"
        successor = "successor-strategy"
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
    available_methods: Sequence[MethodBoundary],
    prior_acquisition_refs: Sequence[str] = (),
) -> SearchPortfolio:
    _text(slot_question, "slot_question")
    categories = ("mechanism", "validation")
    subquestions = tuple(
        {
            "subquestion_id": f"{portfolio_id}-{category}",
            "category": category,
            "question": f"{category.title()} for: {slot_question}",
            "originating_deficit": evidence_deficit,
            "expected_decision_effect": f"Reduce {category} uncertainty for {decision_slot_id}.",
            "stop_or_replan_trigger": "Primary evidence resolves or contradicts the deficit.",
        }
        for category in categories
    )
    usable = tuple(item for item in available_methods if item.available) or tuple(available_methods)
    if not usable:
        raise SearchPortfolioError("available_methods must not be empty")
    queries = tuple(
        {
            "query_id": f"{portfolio_id}-query-{index}",
            "subquestion_id": subquestions[index % len(subquestions)]["subquestion_id"],
            "query": f"{slot_question} {subquestions[index % len(subquestions)]['category']}",
            "method_id": item.method_id,
            "provider_id": item.provider_id,
            "target_evidence_class": item.expected_evidence_class,
            "expected_decision_effect": subquestions[index % len(subquestions)]["expected_decision_effect"],
        }
        for index, item in enumerate(usable, 1)
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
        tuple(available_methods),
        tuple(prior_acquisition_refs),
        ("Decision Slot is supported by independent evidence.",),
        ("Contradiction or shallow evidence remains.",),
    )
