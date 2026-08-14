"""Strict value objects for intent-derived acquisition portfolios."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    RuntimeStoreError,
    canonical_json_bytes,
    thaw_json,
    validate_identifier,
)
from .run_ledger import LedgerConflictError, RunLedger


SEARCH_PORTFOLIO_SCHEMA_VERSION = 2
SEARCH_PORTFOLIO_KIND = "search-portfolio"
METHOD_REGISTRY_SCHEMA_VERSION = 1
METHOD_REGISTRY_KIND = "method-registry"
SUBQUESTION_KINDS = frozenset({"explicit", "implicit", "validation", "implementation", "counterevidence"})
DECISION_IMPACTS = frozenset({"p0", "p1", "optional"})
PORTFOLIO_STATUSES = frozenset({"draft", "active", "superseded", "closed"})
METHOD_AVAILABILITY = frozenset({"available", "degraded", "unavailable"})
REASSESSMENT_DISPOSITIONS = frozenset({"deepen", "broaden", "pivot", "validate", "sufficient_for_slot"})
SELECTION_REASONS = frozenset(
    {"primary-coverage", "independence", "fallback", "direct-source", "validation", "recovery"}
)
REJECTION_REASONS = frozenset(
    {"not-needed", "unavailable", "duplicate-boundary", "budget-limited", "permission-denied", "outside-scope"}
)
DEGRADATION_REASONS = frozenset(
    {
        "single-provider",
        "provider-outage",
        "rate-limited",
        "partial-capability",
        "permission-limited",
        "unsupported-media",
    }
)
PLANNING_COVERAGE = (
    "mechanism",
    "counterevidence",
    "implementation",
    "edge-case",
    "validation",
    "consequence",
)
MATERIAL_HUMAN_DECISION_DIMENSIONS = frozenset({"authority", "safety", "requester-outcome"})
ACQUISITION_DISPOSITIONS = frozenset(
    {
        "captured",
        "http-404",
        "no-result",
        "parser-failure",
        "rate-limit",
        "shallow",
        "unavailable",
        "permission-denied",
    }
)
BATCH_DECISIONS = frozenset(
    {
        "stop",
        "rewrite",
        "switch",
        "deepen",
        "experiment",
        "pivot",
        "blocked",
        "sufficient_for_slot",
        "broaden",
        "validate",
    }
)
BATCH_COVERAGE_LEVELS = frozenset({"none", "partial", "complete"})
BATCH_NOVELTY_LEVELS = frozenset({"none", "low", "new", "high"})
BATCH_SOURCE_QUALITY_LEVELS = frozenset({"unknown", "low", "medium", "high"})
BATCH_SOURCE_DEPTH_LEVELS = frozenset({"none", "snippet", "summary", "full-source", "experiment"})
BATCH_PROVENANCE_LEVELS = frozenset({"none", "single-boundary", "independent"})
BATCH_DECISION_RISK_LEVELS = frozenset({"unknown", "low", "medium", "high", "critical"})
BATCH_COVERAGE_ASSESSMENT_KIND = "batch-coverage-assessment"
BATCH_COVERAGE_ASSESSMENT_SCHEMA_VERSION = 1
METHOD_EXECUTION_OUTCOME_KIND = "method-execution-outcome"
METHOD_EXECUTION_OUTCOME_SCHEMA_VERSION = 1
PORTFOLIO_BATCH_KIND = "portfolio-batch"
PORTFOLIO_BATCH_SCHEMA_VERSION = 1
PORTFOLIO_EXECUTION_KIND = "portfolio-execution"
PORTFOLIO_EXECUTION_SCHEMA_VERSION = 1
PORTFOLIO_DECISION_KIND = "portfolio-decision"
PORTFOLIO_DECISION_SCHEMA_VERSION = 1

_OUTCOME_ALIASES = {
    "succeeded": "captured",
    "404": "http-404",
    "not-found": "http-404",
    "http_404": "http-404",
    "no_results": "no-result",
    "no_result": "no-result",
    "failed_retrieval": "unavailable",
    "parser-failed": "parser-failure",
    "parser_failed": "parser-failure",
    "rate_limited": "rate-limit",
    "rate-limit-exceeded": "rate-limit",
    "permission_limited": "permission-denied",
    "shallow_snippet": "shallow",
}
_PROVENANCE_ALIASES = {
    "single_boundary": "single-boundary",
    "single_provider": "single-boundary",
    "independent_boundaries": "independent",
}
_SOURCE_DEPTH_ALIASES = {"full_source": "full-source", "full": "full-source"}
_RISK_ALIASES = {"not_ready": "high", "not-ready": "high"}


def _execution_choice(
    value: Any,
    label: str,
    allowed: frozenset[str],
    aliases: Mapping[str, str] | None = None,
) -> str:
    if not isinstance(value, str):
        raise InvalidSearchPortfolioError(f"{label} must be a string")
    normalized = value.strip()
    normalized = (aliases or {}).get(normalized, normalized)
    if normalized not in allowed:
        raise InvalidSearchPortfolioError(f"{label} is unsupported: {value!r}")
    return normalized


def _execution_texts(value: Any, label: str, *, required: bool = False) -> tuple[str, ...]:
    values = _sequence(value, label)
    result = tuple(_text(item, f"{label} item") for item in values)
    if required and not result:
        raise InvalidSearchPortfolioError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise InvalidSearchPortfolioError(f"{label} must be unique")
    return tuple(sorted(result))


def _execution_refs(value: Any, label: str, *, required: bool = False) -> tuple[str, ...]:
    values = _sequence(value, label)
    result = tuple(_text(item, f"{label} item") for item in values)
    if required and not result:
        raise InvalidSearchPortfolioError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise InvalidSearchPortfolioError(f"{label} must be unique")
    return tuple(sorted(result))


class SearchPortfolioError(RuntimeStoreError):
    """Base error for invalid SearchPortfolio contract values."""


class InvalidSearchPortfolioError(SearchPortfolioError):
    """Raised when a portfolio or method registry violates its contract."""


def _identifier(value: Any, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except RuntimeStoreError as error:
        raise InvalidSearchPortfolioError(str(error)) from error


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidSearchPortfolioError(f"{label} must be a non-empty string")
    return value.strip()


def _exact_mapping(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidSearchPortfolioError(f"{label} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise InvalidSearchPortfolioError(f"{label} keys must be strings")
    actual = set(value)
    if actual != expected:
        raise InvalidSearchPortfolioError(
            f"{label} fields are invalid; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    return value


def _schema_version(value: Any, expected: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise InvalidSearchPortfolioError(f"unsupported {label} schema_version")
    return value


def _sequence(value: Any, label: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidSearchPortfolioError(f"{label} must be a sequence")
    return tuple(value)


def _identifier_tuple(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    result = tuple(_identifier(item, label) for item in _sequence(value, label))
    if not result and not allow_empty:
        raise InvalidSearchPortfolioError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise InvalidSearchPortfolioError(f"{label} must be unique")
    return tuple(sorted(result))


@dataclass(frozen=True, slots=True)
class Subquestion:
    """One explicit or implicit question linked to a decision slot."""

    subquestion_id: str
    text: str
    kind: str
    decision_impact: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "subquestion_id", _identifier(self.subquestion_id, "subquestion_id"))
        object.__setattr__(self, "text", _text(self.text, "subquestion text"))
        if not isinstance(self.kind, str) or self.kind not in SUBQUESTION_KINDS:
            raise InvalidSearchPortfolioError(f"subquestion kind is unsupported: {self.kind!r}")
        if not isinstance(self.decision_impact, str) or self.decision_impact not in DECISION_IMPACTS:
            raise InvalidSearchPortfolioError(f"subquestion decision_impact is unsupported: {self.decision_impact!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.subquestion_id,
            "text": self.text,
            "kind": self.kind,
            "decision_impact": self.decision_impact,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "Subquestion":
        data = _exact_mapping(value, {"id", "text", "kind", "decision_impact"}, "subquestion")
        return cls(
            subquestion_id=data["id"],
            text=data["text"],
            kind=data["kind"],
            decision_impact=data["decision_impact"],
        )


@dataclass(frozen=True, slots=True)
class MethodRegistration:
    """One registered method/provider boundary and capability state."""

    method_id: str
    provider_id: str
    capability: str
    failure_boundary: str
    availability: str
    degradation_reason: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("method_id", "provider_id", "capability", "failure_boundary"):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field_name))
        if not isinstance(self.availability, str) or self.availability not in METHOD_AVAILABILITY:
            raise InvalidSearchPortfolioError(f"method availability is unsupported: {self.availability!r}")
        if self.availability == "available":
            if self.degradation_reason is not None:
                raise InvalidSearchPortfolioError("available method must not declare a degradation_reason")
        elif not isinstance(self.degradation_reason, str) or self.degradation_reason not in DEGRADATION_REASONS:
            raise InvalidSearchPortfolioError(f"method degradation_reason is unsupported: {self.degradation_reason!r}")
        else:
            object.__setattr__(
                self,
                "degradation_reason",
                self.degradation_reason,
            )

    @property
    def boundary(self) -> tuple[str, str]:
        return (self.method_id, self.provider_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "provider_id": self.provider_id,
            "capability": self.capability,
            "failure_boundary": self.failure_boundary,
            "availability": self.availability,
            "degradation_reason": self.degradation_reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "MethodRegistration":
        data = _exact_mapping(
            value,
            {"method_id", "provider_id", "capability", "failure_boundary", "availability", "degradation_reason"},
            "method registration",
        )
        return cls(
            method_id=data["method_id"],
            provider_id=data["provider_id"],
            capability=data["capability"],
            failure_boundary=data["failure_boundary"],
            availability=data["availability"],
            degradation_reason=data["degradation_reason"],
        )


@dataclass(frozen=True, slots=True)
class MethodSelection:
    """A selected registered method/provider pair and stable query references."""

    method_id: str
    provider_id: str
    failure_boundary: str
    query_refs: tuple[str, ...]
    selection_reason: str

    def __post_init__(self) -> None:
        for field_name in ("method_id", "provider_id", "failure_boundary", "selection_reason"):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field_name))
        if self.selection_reason not in SELECTION_REASONS:
            raise InvalidSearchPortfolioError(f"selection_reason is unsupported: {self.selection_reason!r}")
        object.__setattr__(self, "query_refs", _identifier_tuple(self.query_refs, "query_refs"))

    @property
    def boundary(self) -> tuple[str, str]:
        return (self.method_id, self.provider_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "provider_id": self.provider_id,
            "failure_boundary": self.failure_boundary,
            "query_refs": list(self.query_refs),
            "selection_reason": self.selection_reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "MethodSelection":
        data = _exact_mapping(
            value,
            {"method_id", "provider_id", "failure_boundary", "query_refs", "selection_reason"},
            "method selection",
        )
        return cls(
            method_id=data["method_id"],
            provider_id=data["provider_id"],
            failure_boundary=data["failure_boundary"],
            query_refs=_sequence(data["query_refs"], "query_refs"),
            selection_reason=data["selection_reason"],
        )


@dataclass(frozen=True, slots=True)
class RejectedMethod:
    """A known method/provider pair omitted from this portfolio."""

    method_id: str
    provider_id: str
    rejection_reason: str

    def __post_init__(self) -> None:
        for field_name in ("method_id", "provider_id", "rejection_reason"):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field_name))
        if self.rejection_reason not in REJECTION_REASONS:
            raise InvalidSearchPortfolioError(f"rejection_reason is unsupported: {self.rejection_reason!r}")

    @property
    def boundary(self) -> tuple[str, str]:
        return (self.method_id, self.provider_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "provider_id": self.provider_id,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "RejectedMethod":
        data = _exact_mapping(value, {"method_id", "provider_id", "rejection_reason"}, "rejected method")
        return cls(
            method_id=data["method_id"],
            provider_id=data["provider_id"],
            rejection_reason=data["rejection_reason"],
        )


@dataclass(frozen=True, slots=True)
class ReassessmentPolicy:
    """The allowed outcome categories after each acquisition batch."""

    after_batch: bool
    allowed_dispositions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.after_batch is not True:
            raise InvalidSearchPortfolioError("reassessment after_batch must be true")
        dispositions = _sequence(self.allowed_dispositions, "allowed_dispositions")
        if not dispositions:
            raise InvalidSearchPortfolioError("allowed_dispositions must not be empty")
        if any(not isinstance(item, str) or item not in REASSESSMENT_DISPOSITIONS for item in dispositions):
            raise InvalidSearchPortfolioError("allowed_dispositions contains an unsupported disposition")
        if len(set(dispositions)) != len(dispositions):
            raise InvalidSearchPortfolioError("allowed_dispositions must be unique")
        object.__setattr__(self, "allowed_dispositions", tuple(sorted(dispositions)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "after_batch": self.after_batch,
            "allowed_dispositions": list(self.allowed_dispositions),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ReassessmentPolicy":
        data = _exact_mapping(value, {"after_batch", "allowed_dispositions"}, "reassessment_policy")
        return cls(
            after_batch=data["after_batch"],
            allowed_dispositions=_sequence(data["allowed_dispositions"], "allowed_dispositions"),
        )


@dataclass(frozen=True, slots=True)
class SearchPortfolio:
    """A deterministic, registry-validatable acquisition portfolio."""

    portfolio_id: str
    run_id: str
    slot_id: str
    intent_revision: str
    brief_revision: str
    subquestions: tuple[Subquestion, ...]
    selected_methods: tuple[MethodSelection, ...]
    rejected_methods: tuple[RejectedMethod, ...]
    reassessment_policy: ReassessmentPolicy
    status: str
    schema_version: int = SEARCH_PORTFOLIO_SCHEMA_VERSION
    kind: str = SEARCH_PORTFOLIO_KIND

    def __post_init__(self) -> None:
        for field_name in ("portfolio_id", "run_id", "slot_id", "intent_revision", "brief_revision"):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field_name))
        object.__setattr__(
            self,
            "schema_version",
            _schema_version(self.schema_version, SEARCH_PORTFOLIO_SCHEMA_VERSION, "SearchPortfolio"),
        )
        if self.kind != SEARCH_PORTFOLIO_KIND:
            raise InvalidSearchPortfolioError("SearchPortfolio kind is invalid")
        if not isinstance(self.status, str) or self.status not in PORTFOLIO_STATUSES:
            raise InvalidSearchPortfolioError(f"SearchPortfolio status is unsupported: {self.status!r}")
        subquestions = _sequence(self.subquestions, "subquestions")
        if not subquestions or any(not isinstance(item, Subquestion) for item in subquestions):
            raise InvalidSearchPortfolioError("subquestions must contain at least one Subquestion")
        if len({item.subquestion_id for item in subquestions}) != len(subquestions):
            raise InvalidSearchPortfolioError("subquestion ids must be unique")
        object.__setattr__(self, "subquestions", tuple(sorted(subquestions, key=lambda item: item.subquestion_id)))
        selected = _sequence(self.selected_methods, "selected_methods")
        if not selected or any(not isinstance(item, MethodSelection) for item in selected):
            raise InvalidSearchPortfolioError("selected_methods must contain at least one MethodSelection")
        if len({item.boundary for item in selected}) != len(selected):
            raise InvalidSearchPortfolioError("selected method/provider boundaries must be unique")
        object.__setattr__(self, "selected_methods", tuple(sorted(selected, key=lambda item: item.boundary)))
        rejected = _sequence(self.rejected_methods, "rejected_methods")
        if any(not isinstance(item, RejectedMethod) for item in rejected):
            raise InvalidSearchPortfolioError("rejected_methods must contain RejectedMethod values")
        if len({item.boundary for item in rejected}) != len(rejected):
            raise InvalidSearchPortfolioError("rejected method/provider boundaries must be unique")
        if {item.boundary for item in selected} & {item.boundary for item in rejected}:
            raise InvalidSearchPortfolioError("a method/provider boundary cannot be both selected and rejected")
        object.__setattr__(self, "rejected_methods", tuple(sorted(rejected, key=lambda item: item.boundary)))
        if not isinstance(self.reassessment_policy, ReassessmentPolicy):
            raise InvalidSearchPortfolioError("reassessment_policy must be a ReassessmentPolicy")

    @classmethod
    def create(cls, **values: Any) -> "SearchPortfolio":
        return cls(**values)

    def has_independent_method_provider_boundaries(self, required_boundaries: int = 2) -> bool:
        if isinstance(required_boundaries, bool) or not isinstance(required_boundaries, int) or required_boundaries < 1:
            raise InvalidSearchPortfolioError("required_boundaries must be a positive integer")
        return (
            len({item.method_id for item in self.selected_methods}) >= required_boundaries
            and len({item.provider_id for item in self.selected_methods}) >= required_boundaries
        )

    def validate_against(self, registry: "MethodRegistry") -> "SearchPortfolio":
        return registry.validate_portfolio(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "portfolio_id": self.portfolio_id,
            "run_id": self.run_id,
            "slot_id": self.slot_id,
            "intent_revision": self.intent_revision,
            "brief_revision": self.brief_revision,
            "subquestions": [item.to_dict() for item in self.subquestions],
            "selected_methods": [item.to_dict() for item in self.selected_methods],
            "rejected_methods": [item.to_dict() for item in self.rejected_methods],
            "reassessment_policy": self.reassessment_policy.to_dict(),
            "status": self.status,
        }

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> "SearchPortfolio":
        data = _exact_mapping(
            value,
            {
                "schema_version",
                "kind",
                "portfolio_id",
                "run_id",
                "slot_id",
                "intent_revision",
                "brief_revision",
                "subquestions",
                "selected_methods",
                "rejected_methods",
                "reassessment_policy",
                "status",
            },
            "SearchPortfolio",
        )
        return cls(
            portfolio_id=data["portfolio_id"],
            run_id=data["run_id"],
            slot_id=data["slot_id"],
            intent_revision=data["intent_revision"],
            brief_revision=data["brief_revision"],
            subquestions=tuple(Subquestion.from_dict(item) for item in _sequence(data["subquestions"], "subquestions")),
            selected_methods=tuple(
                MethodSelection.from_dict(item) for item in _sequence(data["selected_methods"], "selected_methods")
            ),
            rejected_methods=tuple(
                RejectedMethod.from_dict(item) for item in _sequence(data["rejected_methods"], "rejected_methods")
            ),
            reassessment_policy=ReassessmentPolicy.from_dict(data["reassessment_policy"]),
            status=data["status"],
            schema_version=data["schema_version"],
            kind=data["kind"],
        )


@dataclass(frozen=True, slots=True)
class MethodRegistry:
    """A strict lookup table for known method/provider boundaries."""

    registry_id: str
    registrations: tuple[MethodRegistration, ...] = ()
    schema_version: int = METHOD_REGISTRY_SCHEMA_VERSION
    kind: str = METHOD_REGISTRY_KIND

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry_id", _identifier(self.registry_id, "registry_id"))
        object.__setattr__(
            self,
            "schema_version",
            _schema_version(self.schema_version, METHOD_REGISTRY_SCHEMA_VERSION, "MethodRegistry"),
        )
        if self.kind != METHOD_REGISTRY_KIND:
            raise InvalidSearchPortfolioError("MethodRegistry kind is invalid")
        registrations = _sequence(self.registrations, "registrations")
        if any(not isinstance(item, MethodRegistration) for item in registrations):
            raise InvalidSearchPortfolioError("registrations must contain MethodRegistration values")
        if len({item.boundary for item in registrations}) != len(registrations):
            raise InvalidSearchPortfolioError("registered method/provider boundaries must be unique")
        object.__setattr__(self, "registrations", tuple(sorted(registrations, key=lambda item: item.boundary)))

    @classmethod
    def create(cls, **values: Any) -> "MethodRegistry":
        return cls(**values)

    def resolve(self, method_id: str, provider_id: str) -> MethodRegistration:
        boundary = (_identifier(method_id, "method_id"), _identifier(provider_id, "provider_id"))
        for registration in self.registrations:
            if registration.boundary == boundary:
                return registration
        raise InvalidSearchPortfolioError(f"method/provider boundary is not registered: {boundary[0]}/{boundary[1]}")

    def validate_portfolio(self, portfolio: SearchPortfolio) -> SearchPortfolio:
        if not isinstance(portfolio, SearchPortfolio):
            raise InvalidSearchPortfolioError("portfolio must be a SearchPortfolio")
        for selection in portfolio.selected_methods:
            registration = self.resolve(selection.method_id, selection.provider_id)
            if registration.failure_boundary != selection.failure_boundary:
                raise InvalidSearchPortfolioError("selected method failure_boundary does not match its registration")
            if registration.availability == "unavailable":
                raise InvalidSearchPortfolioError("selected method/provider boundary is unavailable")
        for rejected in portfolio.rejected_methods:
            self.resolve(rejected.method_id, rejected.provider_id)
        return portfolio

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "registry_id": self.registry_id,
            "registrations": [item.to_dict() for item in self.registrations],
        }

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> "MethodRegistry":
        data = _exact_mapping(value, {"schema_version", "kind", "registry_id", "registrations"}, "MethodRegistry")
        return cls(
            registry_id=data["registry_id"],
            registrations=tuple(
                MethodRegistration.from_dict(item) for item in _sequence(data["registrations"], "registrations")
            ),
            schema_version=data["schema_version"],
            kind=data["kind"],
        )


@dataclass(frozen=True, slots=True)
class PlannedSubquestion:
    """A decision-relevant coverage obligation derived from one open slot."""

    subquestion: Subquestion
    coverage: str
    evidence_class: str
    decision_effect: str
    closure_oracle: str
    stop_or_replan_trigger: str

    def __post_init__(self) -> None:
        if not isinstance(self.subquestion, Subquestion):
            raise InvalidSearchPortfolioError("planned subquestion must contain a Subquestion")
        if self.coverage not in PLANNING_COVERAGE:
            raise InvalidSearchPortfolioError(f"planned subquestion coverage is unsupported: {self.coverage!r}")
        object.__setattr__(self, "evidence_class", _identifier(self.evidence_class, "evidence_class"))
        for field_name in ("decision_effect", "closure_oracle", "stop_or_replan_trigger"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))


@dataclass(frozen=True, slots=True)
class QueryRewrite:
    """Stable planning metadata for one method/subquestion query reference."""

    query_ref: str
    subquestion_id: str
    method_id: str
    provider_id: str
    intent_revision: str
    brief_revision: str
    strategy_revision: str
    decision_slot_id: str
    evidence_deficit_revision: str
    evidence_class: str
    decision_effect: str
    closure_oracle: str
    stop_or_replan_trigger: str

    def __post_init__(self) -> None:
        for field_name in (
            "query_ref",
            "subquestion_id",
            "method_id",
            "provider_id",
            "intent_revision",
            "brief_revision",
            "strategy_revision",
            "decision_slot_id",
            "evidence_deficit_revision",
            "evidence_class",
        ):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field_name))
        for field_name in ("decision_effect", "closure_oracle", "stop_or_replan_trigger"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))


@dataclass(frozen=True, slots=True)
class IntentDerivedSearchPortfolioPlan:
    """A pure planning view layered over the strict SearchPortfolio contract."""

    portfolio: SearchPortfolio
    registry: MethodRegistry
    planned_subquestions: tuple[PlannedSubquestion, ...]
    query_rewrites: tuple[QueryRewrite, ...]
    assumptions: tuple[str, ...]
    human_decision_reopen: bool

    def __post_init__(self) -> None:
        if not isinstance(self.portfolio, SearchPortfolio):
            raise InvalidSearchPortfolioError("plan portfolio must be a SearchPortfolio")
        if not isinstance(self.registry, MethodRegistry):
            raise InvalidSearchPortfolioError("plan registry must be a MethodRegistry")
        self.portfolio.validate_against(self.registry)
        subquestions = _sequence(self.planned_subquestions, "planned_subquestions")
        if len(subquestions) != len(PLANNING_COVERAGE) or any(
            not isinstance(item, PlannedSubquestion) for item in subquestions
        ):
            raise InvalidSearchPortfolioError("plan must contain each bounded planning coverage subquestion")
        if {item.coverage for item in subquestions} != set(PLANNING_COVERAGE):
            raise InvalidSearchPortfolioError("planned subquestion coverage must be unique and complete")
        portfolio_subquestion_ids = {item.subquestion_id for item in self.portfolio.subquestions}
        if {item.subquestion.subquestion_id for item in subquestions} != portfolio_subquestion_ids:
            raise InvalidSearchPortfolioError("planned subquestions must match the strict portfolio")
        rewrites = _sequence(self.query_rewrites, "query_rewrites")
        if not rewrites or any(not isinstance(item, QueryRewrite) for item in rewrites):
            raise InvalidSearchPortfolioError("query_rewrites must contain QueryRewrite values")
        if len({item.query_ref for item in rewrites}) != len(rewrites):
            raise InvalidSearchPortfolioError("query rewrite references must be unique")
        expected_refs = {
            reference for selection in self.portfolio.selected_methods for reference in selection.query_refs
        }
        if {item.query_ref for item in rewrites} != expected_refs:
            raise InvalidSearchPortfolioError("query rewrites must match selected method query references")
        assumptions = tuple(_text(item, "assumption") for item in _sequence(self.assumptions, "assumptions"))
        if not assumptions:
            raise InvalidSearchPortfolioError("assumptions must not be empty")
        if not isinstance(self.human_decision_reopen, bool):
            raise InvalidSearchPortfolioError("human_decision_reopen must be bool")
        object.__setattr__(self, "planned_subquestions", tuple(subquestions))
        object.__setattr__(self, "query_rewrites", tuple(sorted(rewrites, key=lambda item: item.query_ref)))
        object.__setattr__(self, "assumptions", assumptions)


class IntentDerivedSearchPortfolioPlanner:
    """Derive bounded decision coverage without retrieval, persistence, or dispatch."""

    def __init__(self, registry: MethodRegistry) -> None:
        if not isinstance(registry, MethodRegistry):
            raise InvalidSearchPortfolioError("registry must be a MethodRegistry")
        self._registry = registry

    def plan(
        self,
        *,
        portfolio_id: str,
        run_id: str,
        intent_revision: str,
        brief_revision: str,
        strategy_revision: str,
        decision_slot_id: str,
        slot_question: str,
        evidence_deficit_revision: str,
        evidence_deficit: str,
        closure_oracle: str,
        assumptions: Sequence[str],
        material_change_dimensions: Sequence[str] = (),
    ) -> IntentDerivedSearchPortfolioPlan:
        """Create a bounded plan for the exact current intent and decision revisions."""
        for field_name in (
            "portfolio_id",
            "run_id",
            "intent_revision",
            "brief_revision",
            "strategy_revision",
            "decision_slot_id",
            "evidence_deficit_revision",
        ):
            _identifier(locals()[field_name], field_name)
        slot_question = _text(slot_question, "slot_question")
        evidence_deficit = _text(evidence_deficit, "evidence_deficit")
        closure_oracle = _text(closure_oracle, "closure_oracle")
        normalized_assumptions = tuple(_text(item, "assumption") for item in _sequence(assumptions, "assumptions"))
        if not normalized_assumptions:
            raise InvalidSearchPortfolioError("assumptions must not be empty")
        change_dimensions = tuple(
            _identifier(item, "material_change_dimension")
            for item in _sequence(material_change_dimensions, "material_change_dimensions")
        )
        selections = self._selected_methods(portfolio_id)
        planned_subquestions = tuple(
            self._planned_subquestion(
                portfolio_id=portfolio_id,
                slot_question=slot_question,
                evidence_deficit=evidence_deficit,
                closure_oracle=closure_oracle,
                decision_slot_id=decision_slot_id,
                coverage=coverage,
            )
            for coverage in PLANNING_COVERAGE
        )
        rewrites = tuple(
            QueryRewrite(
                query_ref=query_ref,
                subquestion_id=planned.subquestion.subquestion_id,
                method_id=registration.method_id,
                provider_id=registration.provider_id,
                intent_revision=intent_revision,
                brief_revision=brief_revision,
                strategy_revision=strategy_revision,
                decision_slot_id=decision_slot_id,
                evidence_deficit_revision=evidence_deficit_revision,
                evidence_class=planned.evidence_class,
                decision_effect=planned.decision_effect,
                closure_oracle=planned.closure_oracle,
                stop_or_replan_trigger=planned.stop_or_replan_trigger,
            )
            for planned in planned_subquestions
            for registration, query_ref in self._query_refs(portfolio_id, planned)
        )
        portfolio = SearchPortfolio(
            portfolio_id=portfolio_id,
            run_id=run_id,
            slot_id=decision_slot_id,
            intent_revision=intent_revision,
            brief_revision=brief_revision,
            subquestions=tuple(item.subquestion for item in planned_subquestions),
            selected_methods=selections,
            rejected_methods=(),
            reassessment_policy=ReassessmentPolicy(
                after_batch=True,
                allowed_dispositions=("deepen", "broaden", "pivot", "validate", "sufficient_for_slot"),
            ),
            status="draft",
        ).validate_against(self._registry)
        return IntentDerivedSearchPortfolioPlan(
            portfolio=portfolio,
            registry=self._registry,
            planned_subquestions=planned_subquestions,
            query_rewrites=rewrites,
            assumptions=normalized_assumptions,
            human_decision_reopen=bool(set(change_dimensions) & MATERIAL_HUMAN_DECISION_DIMENSIONS),
        )

    def _selected_methods(self, portfolio_id: str) -> tuple[MethodSelection, ...]:
        available = self._available_registrations()
        if not available:
            raise InvalidSearchPortfolioError("at least one registered method/provider boundary must be available")
        return tuple(
            MethodSelection(
                method_id=registration.method_id,
                provider_id=registration.provider_id,
                failure_boundary=registration.failure_boundary,
                query_refs=tuple(
                    self._query_ref(portfolio_id, coverage_index, index + 1)
                    for coverage_index, _ in enumerate(PLANNING_COVERAGE, 1)
                ),
                selection_reason="primary-coverage" if index == 0 else "independence",
            )
            for index, registration in enumerate(available)
        )

    def _query_refs(
        self,
        portfolio_id: str,
        planned: PlannedSubquestion,
    ) -> tuple[tuple[MethodRegistration, str], ...]:
        return tuple(
            (
                registration,
                self._query_ref(portfolio_id, PLANNING_COVERAGE.index(planned.coverage) + 1, method_index),
            )
            for method_index, registration in enumerate(self._available_registrations(), 1)
        )

    def _available_registrations(self) -> tuple[MethodRegistration, ...]:
        return tuple(item for item in self._registry.registrations if item.availability != "unavailable")

    @staticmethod
    def _query_ref(portfolio_id: str, coverage_index: int, method_index: int) -> str:
        return f"{portfolio_id[:48].rstrip('-')}-q{coverage_index}-m{method_index}"

    @staticmethod
    def _planned_subquestion(
        *,
        portfolio_id: str,
        slot_question: str,
        evidence_deficit: str,
        closure_oracle: str,
        decision_slot_id: str,
        coverage: str,
    ) -> PlannedSubquestion:
        kind, impact, evidence_class = {
            "mechanism": ("implicit", "p0", "primary-source"),
            "counterevidence": ("counterevidence", "p0", "independent-source"),
            "implementation": ("implementation", "p1", "repository-observation"),
            "edge-case": ("implicit", "p1", "edge-case-fixture"),
            "validation": ("validation", "p1", "validation-result"),
            "consequence": ("implicit", "p1", "decision-consequence"),
        }[coverage]
        decision_effect = f"Reduce {coverage} uncertainty for Decision Slot {decision_slot_id}."
        return PlannedSubquestion(
            subquestion=Subquestion(
                subquestion_id=f"{portfolio_id}-{coverage}",
                text=f"What {coverage} evidence can change this decision: {slot_question}",
                kind=kind,
                decision_impact=impact,
            ),
            coverage=coverage,
            evidence_class=evidence_class,
            decision_effect=decision_effect,
            closure_oracle=closure_oracle,
            stop_or_replan_trigger=(f"Stop when {closure_oracle}; replan when {evidence_deficit} changes materially."),
        )


def derive_search_portfolio(*, registry: MethodRegistry, **values: Any) -> IntentDerivedSearchPortfolioPlan:
    """Convenience entry point for pure intent-derived portfolio planning."""
    return IntentDerivedSearchPortfolioPlanner(registry).plan(**values)


@dataclass(frozen=True, slots=True)
class MethodExecutionOutcome:
    """One typed result at a registered method/provider boundary."""

    outcome_id: str
    portfolio_id: str
    batch_id: str
    method_id: str
    provider_id: str
    failure_boundary: str
    selection_reason: str
    disposition: str
    query_refs: tuple[str, ...]
    capture_refs: tuple[str, ...] = ()
    coverage: str = "none"
    novelty: str = "none"
    source_quality: str = "unknown"
    source_depth: str = "none"
    contradictions: tuple[str, ...] = ()
    unresolved_decision_risk: str = "unknown"
    receipt_refs: tuple[str, ...] = ()
    checkpoint_refs: tuple[str, ...] = ()
    error_code: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("outcome_id", "portfolio_id", "batch_id", "method_id", "provider_id"):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field_name))
        object.__setattr__(self, "failure_boundary", _text(self.failure_boundary, "failure_boundary"))
        object.__setattr__(
            self,
            "selection_reason",
            _execution_choice(self.selection_reason, "selection_reason", SELECTION_REASONS),
        )
        object.__setattr__(
            self,
            "disposition",
            _execution_choice(self.disposition, "disposition", ACQUISITION_DISPOSITIONS, _OUTCOME_ALIASES),
        )
        object.__setattr__(self, "query_refs", _identifier_tuple(self.query_refs, "query_refs"))
        object.__setattr__(self, "capture_refs", _execution_refs(self.capture_refs, "capture_refs"))
        object.__setattr__(self, "receipt_refs", _execution_refs(self.receipt_refs, "receipt_refs"))
        object.__setattr__(self, "checkpoint_refs", _execution_refs(self.checkpoint_refs, "checkpoint_refs"))
        object.__setattr__(self, "coverage", _execution_choice(self.coverage, "coverage", BATCH_COVERAGE_LEVELS))
        object.__setattr__(self, "novelty", _execution_choice(self.novelty, "novelty", BATCH_NOVELTY_LEVELS))
        object.__setattr__(
            self,
            "source_quality",
            _execution_choice(self.source_quality, "source_quality", BATCH_SOURCE_QUALITY_LEVELS),
        )
        object.__setattr__(
            self,
            "source_depth",
            _execution_choice(self.source_depth, "source_depth", BATCH_SOURCE_DEPTH_LEVELS, _SOURCE_DEPTH_ALIASES),
        )
        object.__setattr__(self, "contradictions", _execution_texts(self.contradictions, "contradictions"))
        object.__setattr__(
            self,
            "unresolved_decision_risk",
            _execution_choice(
                self.unresolved_decision_risk,
                "unresolved_decision_risk",
                BATCH_DECISION_RISK_LEVELS,
                _RISK_ALIASES,
            ),
        )
        if self.error_code is not None:
            object.__setattr__(self, "error_code", _text(self.error_code, "error_code"))
        if self.disposition == "captured" and self.error_code is not None:
            raise InvalidSearchPortfolioError("captured outcomes must not declare an error_code")
        if self.disposition not in {"captured", "shallow"} and self.capture_refs:
            raise InvalidSearchPortfolioError("failed outcomes must not claim source captures")
        if self.disposition not in {"captured", "shallow"} and self.error_code is None:
            object.__setattr__(self, "error_code", self.disposition)

    @property
    def boundary(self) -> tuple[str, str]:
        return (self.method_id, self.provider_id)

    @property
    def is_failure(self) -> bool:
        return self.disposition not in {"captured", "shallow"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": METHOD_EXECUTION_OUTCOME_SCHEMA_VERSION,
            "kind": METHOD_EXECUTION_OUTCOME_KIND,
            "outcome_id": self.outcome_id,
            "portfolio_id": self.portfolio_id,
            "batch_id": self.batch_id,
            "method_id": self.method_id,
            "provider_id": self.provider_id,
            "failure_boundary": self.failure_boundary,
            "selection_reason": self.selection_reason,
            "disposition": self.disposition,
            "query_refs": list(self.query_refs),
            "capture_refs": list(self.capture_refs),
            "coverage": self.coverage,
            "novelty": self.novelty,
            "source_quality": self.source_quality,
            "source_depth": self.source_depth,
            "contradictions": list(self.contradictions),
            "unresolved_decision_risk": self.unresolved_decision_risk,
            "receipt_refs": list(self.receipt_refs),
            "checkpoint_refs": list(self.checkpoint_refs),
            "error_code": self.error_code,
        }

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> "MethodExecutionOutcome":
        data = _exact_mapping(
            value,
            {
                "schema_version",
                "kind",
                "outcome_id",
                "portfolio_id",
                "batch_id",
                "method_id",
                "provider_id",
                "failure_boundary",
                "selection_reason",
                "disposition",
                "query_refs",
                "capture_refs",
                "coverage",
                "novelty",
                "source_quality",
                "source_depth",
                "contradictions",
                "unresolved_decision_risk",
                "receipt_refs",
                "checkpoint_refs",
                "error_code",
            },
            "method execution outcome",
        )
        _schema_version(data["schema_version"], METHOD_EXECUTION_OUTCOME_SCHEMA_VERSION, "method execution outcome")
        if data["kind"] != METHOD_EXECUTION_OUTCOME_KIND:
            raise InvalidSearchPortfolioError("method execution outcome kind is invalid")
        return cls(
            outcome_id=data["outcome_id"],
            portfolio_id=data["portfolio_id"],
            batch_id=data["batch_id"],
            method_id=data["method_id"],
            provider_id=data["provider_id"],
            failure_boundary=data["failure_boundary"],
            selection_reason=data["selection_reason"],
            disposition=data["disposition"],
            query_refs=_sequence(data["query_refs"], "query_refs"),
            capture_refs=_sequence(data["capture_refs"], "capture_refs"),
            coverage=data["coverage"],
            novelty=data["novelty"],
            source_quality=data["source_quality"],
            source_depth=data["source_depth"],
            contradictions=_sequence(data["contradictions"], "contradictions"),
            unresolved_decision_risk=data["unresolved_decision_risk"],
            receipt_refs=_sequence(data["receipt_refs"], "receipt_refs"),
            checkpoint_refs=_sequence(data["checkpoint_refs"], "checkpoint_refs"),
            error_code=data["error_code"],
        )


AcquisitionOutcome = MethodExecutionOutcome


@dataclass(frozen=True, slots=True)
class PortfolioBatch:
    """A dependency-ready wave of method outcomes."""

    batch_id: str
    portfolio_id: str
    outcomes: tuple[MethodExecutionOutcome, ...]
    schema_version: int = PORTFOLIO_BATCH_SCHEMA_VERSION
    kind: str = PORTFOLIO_BATCH_KIND

    def __post_init__(self) -> None:
        object.__setattr__(self, "batch_id", _identifier(self.batch_id, "batch_id"))
        object.__setattr__(self, "portfolio_id", _identifier(self.portfolio_id, "portfolio_id"))
        object.__setattr__(
            self,
            "schema_version",
            _schema_version(self.schema_version, PORTFOLIO_BATCH_SCHEMA_VERSION, "PortfolioBatch"),
        )
        if self.kind != PORTFOLIO_BATCH_KIND:
            raise InvalidSearchPortfolioError("PortfolioBatch kind is invalid")
        outcomes = _sequence(self.outcomes, "outcomes")
        if not outcomes or any(not isinstance(item, MethodExecutionOutcome) for item in outcomes):
            raise InvalidSearchPortfolioError("outcomes must contain at least one MethodExecutionOutcome")
        if any(item.portfolio_id != self.portfolio_id or item.batch_id != self.batch_id for item in outcomes):
            raise InvalidSearchPortfolioError("outcome portfolio and batch identities must match the batch")
        if len({item.outcome_id for item in outcomes}) != len(outcomes):
            raise InvalidSearchPortfolioError("outcome ids must be unique within a batch")
        object.__setattr__(self, "outcomes", tuple(sorted(outcomes, key=lambda item: item.outcome_id)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "batch_id": self.batch_id,
            "portfolio_id": self.portfolio_id,
            "outcomes": [item.to_dict() for item in self.outcomes],
        }

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> "PortfolioBatch":
        data = _exact_mapping(
            value, {"schema_version", "kind", "batch_id", "portfolio_id", "outcomes"}, "PortfolioBatch"
        )
        return cls(
            batch_id=data["batch_id"],
            portfolio_id=data["portfolio_id"],
            outcomes=tuple(MethodExecutionOutcome.from_dict(item) for item in _sequence(data["outcomes"], "outcomes")),
            schema_version=data["schema_version"],
            kind=data["kind"],
        )


@dataclass(frozen=True, slots=True)
class BatchCoverageAssessment:
    """Typed coverage, quality, contradiction, and decision-risk result for one batch."""

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
    evidence_disposition: str = "captured"
    alternate_method_available: bool = False
    source_quality: str = "unknown"
    method_outcome_refs: tuple[str, ...] = ()
    alternate_method_ids: tuple[str, ...] = ()
    decision_slot_id: str | None = None
    attempt_id: str | None = None
    schema_version: int = BATCH_COVERAGE_ASSESSMENT_SCHEMA_VERSION
    kind: str = BATCH_COVERAGE_ASSESSMENT_KIND

    def __post_init__(self) -> None:
        for field_name in ("assessment_id", "portfolio_id", "batch_id"):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field_name))
        object.__setattr__(
            self,
            "schema_version",
            _schema_version(self.schema_version, BATCH_COVERAGE_ASSESSMENT_SCHEMA_VERSION, "BatchCoverageAssessment"),
        )
        if self.kind != BATCH_COVERAGE_ASSESSMENT_KIND:
            raise InvalidSearchPortfolioError("BatchCoverageAssessment kind is invalid")
        object.__setattr__(self, "coverage", _execution_choice(self.coverage, "coverage", BATCH_COVERAGE_LEVELS))
        object.__setattr__(self, "novelty", _execution_choice(self.novelty, "novelty", BATCH_NOVELTY_LEVELS))
        object.__setattr__(
            self,
            "source_depth",
            _execution_choice(self.source_depth, "source_depth", BATCH_SOURCE_DEPTH_LEVELS, _SOURCE_DEPTH_ALIASES),
        )
        object.__setattr__(
            self,
            "provenance_independence",
            _execution_choice(
                self.provenance_independence,
                "provenance_independence",
                BATCH_PROVENANCE_LEVELS,
                _PROVENANCE_ALIASES,
            ),
        )
        object.__setattr__(
            self,
            "source_quality",
            _execution_choice(self.source_quality, "source_quality", BATCH_SOURCE_QUALITY_LEVELS),
        )
        object.__setattr__(
            self,
            "unresolved_decision_risk",
            _text(self.unresolved_decision_risk, "unresolved_decision_risk"),
        )
        object.__setattr__(
            self,
            "implementation_uncertainty",
            _text(self.implementation_uncertainty, "implementation_uncertainty"),
        )
        object.__setattr__(
            self,
            "oracle_readiness",
            _execution_choice(
                self.oracle_readiness,
                "oracle_readiness",
                frozenset({"unknown", "not-ready", "ready"}),
                {"not_ready": "not-ready"},
            ),
        )
        object.__setattr__(self, "disposition", _execution_choice(self.disposition, "disposition", BATCH_DECISIONS))
        object.__setattr__(
            self,
            "evidence_disposition",
            _execution_choice(
                self.evidence_disposition, "evidence_disposition", ACQUISITION_DISPOSITIONS, _OUTCOME_ALIASES
            ),
        )
        object.__setattr__(self, "contradictions", _execution_texts(self.contradictions, "contradictions"))
        for field_name in (
            "causal_refs",
            "capture_refs",
            "receipt_refs",
            "checkpoint_refs",
            "method_outcome_refs",
            "alternate_method_ids",
        ):
            object.__setattr__(self, field_name, _execution_refs(getattr(self, field_name), field_name))
        object.__setattr__(self, "next_actions", _execution_texts(self.next_actions, "next_actions"))
        if not isinstance(self.alternate_method_available, bool):
            raise InvalidSearchPortfolioError("alternate_method_available must be bool")
        if self.authority_disposition not in {"inside_confirmed_authority", "requires_requester_reopen"}:
            raise InvalidSearchPortfolioError("authority_disposition is unsupported")
        if self.authority_disposition == "requires_requester_reopen" and self.disposition != "blocked":
            raise InvalidSearchPortfolioError("requester-controlled changes require a blocked disposition")
        if self.disposition == "pivot" and (
            not self.superseded_strategy_revision or not self.successor_strategy_revision
        ):
            raise InvalidSearchPortfolioError("pivot requires superseded and successor strategy revisions")
        for field_name in (
            "superseded_strategy_revision",
            "successor_strategy_revision",
            "decision_slot_id",
            "attempt_id",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(value, field_name))
        if self.evidence_disposition not in {"captured", "shallow"} and self.capture_refs:
            raise InvalidSearchPortfolioError("failed assessments must not claim source captures")

    @property
    def requires_deeper_work(self) -> bool:
        return self.disposition in {"rewrite", "switch", "deepen", "experiment", "pivot", "broaden", "validate"}

    def policy_input(self) -> dict[str, object]:
        return {
            "portfolio_id": self.portfolio_id,
            "batch_id": self.batch_id,
            "disposition": self.disposition,
            "causal_refs": self.causal_refs,
            "next_actions": self.next_actions,
            "requires_deeper_work": self.requires_deeper_work,
            "coverage": self.coverage,
            "novelty": self.novelty,
            "source_quality": self.source_quality,
            "provenance_independence": self.provenance_independence,
            "unresolved_decision_risk": self.unresolved_decision_risk,
            "evidence_disposition": self.evidence_disposition,
            "alternate_method_available": self.alternate_method_available,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "assessment_id": self.assessment_id,
            "portfolio_id": self.portfolio_id,
            "batch_id": self.batch_id,
            "coverage": self.coverage,
            "novelty": self.novelty,
            "source_depth": self.source_depth,
            "provenance_independence": self.provenance_independence,
            "contradictions": list(self.contradictions),
            "implementation_uncertainty": self.implementation_uncertainty,
            "oracle_readiness": self.oracle_readiness,
            "unresolved_decision_risk": self.unresolved_decision_risk,
            "disposition": self.disposition,
            "causal_refs": list(self.causal_refs),
            "next_actions": list(self.next_actions),
            "capture_refs": list(self.capture_refs),
            "receipt_refs": list(self.receipt_refs),
            "checkpoint_refs": list(self.checkpoint_refs),
            "authority_disposition": self.authority_disposition,
            "superseded_strategy_revision": self.superseded_strategy_revision,
            "successor_strategy_revision": self.successor_strategy_revision,
            "evidence_disposition": self.evidence_disposition,
            "alternate_method_available": self.alternate_method_available,
            "source_quality": self.source_quality,
            "method_outcome_refs": list(self.method_outcome_refs),
            "alternate_method_ids": list(self.alternate_method_ids),
            "decision_slot_id": self.decision_slot_id,
            "attempt_id": self.attempt_id,
        }

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> "BatchCoverageAssessment":
        required = {
            "schema_version",
            "kind",
            "assessment_id",
            "portfolio_id",
            "batch_id",
            "coverage",
            "novelty",
            "source_depth",
            "provenance_independence",
            "contradictions",
            "implementation_uncertainty",
            "oracle_readiness",
            "unresolved_decision_risk",
            "disposition",
            "causal_refs",
            "next_actions",
            "capture_refs",
            "receipt_refs",
            "checkpoint_refs",
            "authority_disposition",
            "superseded_strategy_revision",
            "successor_strategy_revision",
            "evidence_disposition",
            "alternate_method_available",
            "source_quality",
            "method_outcome_refs",
            "alternate_method_ids",
            "decision_slot_id",
            "attempt_id",
        }
        data = _exact_mapping(value, required, "BatchCoverageAssessment")
        return cls(
            assessment_id=data["assessment_id"],
            portfolio_id=data["portfolio_id"],
            batch_id=data["batch_id"],
            coverage=data["coverage"],
            novelty=data["novelty"],
            source_depth=data["source_depth"],
            provenance_independence=data["provenance_independence"],
            contradictions=_sequence(data["contradictions"], "contradictions"),
            implementation_uncertainty=data["implementation_uncertainty"],
            oracle_readiness=data["oracle_readiness"],
            unresolved_decision_risk=data["unresolved_decision_risk"],
            disposition=data["disposition"],
            causal_refs=_sequence(data["causal_refs"], "causal_refs"),
            next_actions=_sequence(data["next_actions"], "next_actions"),
            capture_refs=_sequence(data["capture_refs"], "capture_refs"),
            receipt_refs=_sequence(data["receipt_refs"], "receipt_refs"),
            checkpoint_refs=_sequence(data["checkpoint_refs"], "checkpoint_refs"),
            authority_disposition=data["authority_disposition"],
            superseded_strategy_revision=data["superseded_strategy_revision"],
            successor_strategy_revision=data["successor_strategy_revision"],
            evidence_disposition=data["evidence_disposition"],
            alternate_method_available=data["alternate_method_available"],
            source_quality=data["source_quality"],
            method_outcome_refs=_sequence(data["method_outcome_refs"], "method_outcome_refs"),
            alternate_method_ids=_sequence(data["alternate_method_ids"], "alternate_method_ids"),
            decision_slot_id=data["decision_slot_id"],
            attempt_id=data["attempt_id"],
            schema_version=data["schema_version"],
            kind=data["kind"],
        )


def _outcome_value(value: MethodExecutionOutcome | Mapping[str, Any]) -> MethodExecutionOutcome:
    if isinstance(value, MethodExecutionOutcome):
        return value
    return MethodExecutionOutcome.from_dict(value)


def _metric_max(values: Sequence[str], ranking: Mapping[str, int], default: str) -> str:
    return max(values, key=lambda value: ranking.get(value, -1), default=default)


def _metric_min(values: Sequence[str], ranking: Mapping[str, int], default: str) -> str:
    return min(values, key=lambda value: ranking.get(value, 99), default=default)


def assess_acquisition_batch(
    *,
    assessment_id: str,
    portfolio_id: str,
    batch_id: str,
    outcomes: Sequence[MethodExecutionOutcome | Mapping[str, Any]] = (),
    coverage: str | None = None,
    novelty: str | None = None,
    source_depth: str | None = None,
    provenance_independence: str | None = None,
    source_quality: str | None = None,
    contradictions: Sequence[str] = (),
    implementation_uncertainty: str = "low",
    oracle_readiness: str = "ready",
    unresolved_decision_risk: str | None = None,
    causal_refs: Sequence[str] = (),
    capture_refs: Sequence[str] = (),
    receipt_refs: Sequence[str] = (),
    checkpoint_refs: Sequence[str] = (),
    decision_slot_id: str | None = None,
    attempt_id: str | None = None,
    authority_disposition: str = "inside_confirmed_authority",
    evidence_disposition: str | None = None,
    alternate_method_available: bool = False,
    alternate_method_ids: Sequence[str] = (),
    superseded_strategy_revision: str | None = None,
    successor_strategy_revision: str | None = None,
    disposition: str | None = None,
    next_actions: Sequence[str] = (),
) -> BatchCoverageAssessment:
    """Assess one dependency-ready batch without persisting coordinator state."""
    normalized_outcomes = tuple(_outcome_value(item) for item in _sequence(outcomes, "outcomes"))
    if normalized_outcomes:
        if any(item.portfolio_id != portfolio_id or item.batch_id != batch_id for item in normalized_outcomes):
            raise InvalidSearchPortfolioError("outcome portfolio and batch identities must match the assessment")
        coverage = coverage or _metric_max(
            tuple(item.coverage for item in normalized_outcomes),
            {"none": 0, "partial": 1, "complete": 2},
            "none",
        )
        novelty = novelty or _metric_max(
            tuple(item.novelty for item in normalized_outcomes),
            {"none": 0, "low": 1, "new": 2, "high": 3},
            "none",
        )
        source_depth = source_depth or _metric_min(
            tuple(item.source_depth for item in normalized_outcomes),
            {"none": 0, "snippet": 1, "summary": 2, "full-source": 3, "experiment": 4},
            "none",
        )
        if source_quality is None:
            source_quality = _metric_min(
                tuple(item.source_quality for item in normalized_outcomes),
                {"unknown": 0, "low": 1, "medium": 2, "high": 3},
                "unknown",
            )
        if unresolved_decision_risk is None:
            unresolved_decision_risk = _metric_max(
                tuple(item.unresolved_decision_risk for item in normalized_outcomes),
                {"unknown": 0, "low": 1, "medium": 2, "high": 3, "critical": 4},
                "unknown",
            )
        contradictions = tuple(
            dict.fromkeys(
                (*contradictions, *(item for outcome in normalized_outcomes for item in outcome.contradictions))
            )
        )
        capture_refs = tuple(
            dict.fromkeys((*capture_refs, *(item for outcome in normalized_outcomes for item in outcome.capture_refs)))
        )
        receipt_refs = tuple(
            dict.fromkeys((*receipt_refs, *(item for outcome in normalized_outcomes for item in outcome.receipt_refs)))
        )
        checkpoint_refs = tuple(
            dict.fromkeys(
                (*checkpoint_refs, *(item for outcome in normalized_outcomes for item in outcome.checkpoint_refs))
            )
        )
        causal_refs = tuple(dict.fromkeys((*causal_refs, *capture_refs, *receipt_refs, *checkpoint_refs)))
        if evidence_disposition is None:
            failures = tuple(item.disposition for item in normalized_outcomes if item.is_failure)
            evidence_disposition = (
                failures[0]
                if failures
                else ("shallow" if any(item.disposition == "shallow" for item in normalized_outcomes) else "captured")
            )
        if provenance_independence is None:
            successful = tuple(item for item in normalized_outcomes if not item.is_failure)
            boundaries = {item.boundary for item in successful}
            method_ids = {item.method_id for item in successful}
            provider_ids = {item.provider_id for item in successful}
            provenance_independence = (
                "independent"
                if len(boundaries) >= 2 and len(method_ids) >= 2 and len(provider_ids) >= 2
                else ("single-boundary" if boundaries else "none")
            )
    coverage = coverage or "none"
    novelty = novelty or "none"
    source_depth = source_depth or "none"
    provenance_independence = provenance_independence or "none"
    unresolved_decision_risk = unresolved_decision_risk or "unknown"
    source_quality = source_quality or "unknown"
    normalized_evidence = _execution_choice(
        evidence_disposition or "captured",
        "evidence_disposition",
        ACQUISITION_DISPOSITIONS,
        _OUTCOME_ALIASES,
    )
    alternate_method_ids = tuple(alternate_method_ids)
    alternate_method_available = bool(alternate_method_available or alternate_method_ids)
    if not next_actions and disposition is None:
        if authority_disposition == "requires_requester_reopen":
            disposition = "blocked"
            next_actions = ("reopen-human-decision",)
        elif contradictions:
            disposition = "pivot"
            next_actions = ("create-successor-strategy",)
            superseded_strategy_revision = superseded_strategy_revision or "superseded-strategy"
            successor_strategy_revision = successor_strategy_revision or "successor-strategy"
        elif normalized_evidence == "no-result" and not alternate_method_available:
            disposition = "rewrite"
            next_actions = ("rewrite-query",)
        elif normalized_evidence not in {"captured", "shallow"}:
            disposition = "switch" if alternate_method_available else "blocked"
            next_actions = ("switch-to-alternate-method",) if alternate_method_available else ("record-typed-blocker",)
        elif normalized_evidence == "shallow" or source_depth in {"snippet", "summary"} or coverage != "complete":
            disposition = "deepen"
            next_actions = ("open-full-source",)
        elif novelty == "none":
            disposition = "rewrite"
            next_actions = ("rewrite-query",)
        elif implementation_uncertainty in {"high", "unknown", "critical"} or oracle_readiness != "ready":
            disposition = "experiment"
            next_actions = ("run-bounded-experiment",)
        elif unresolved_decision_risk in {"high", "critical", "unknown"}:
            disposition = "experiment"
            next_actions = ("run-bounded-experiment",)
        else:
            disposition = "stop"
            next_actions = ("submit-for-closure-assessment",)
    disposition = disposition or "stop"
    if disposition == "pivot":
        superseded_strategy_revision = superseded_strategy_revision or "superseded-strategy"
        successor_strategy_revision = successor_strategy_revision or "successor-strategy"
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
        next_actions=tuple(next_actions),
        capture_refs=tuple(capture_refs),
        receipt_refs=tuple(receipt_refs),
        checkpoint_refs=tuple(checkpoint_refs),
        authority_disposition=authority_disposition,
        superseded_strategy_revision=superseded_strategy_revision,
        successor_strategy_revision=successor_strategy_revision,
        evidence_disposition=normalized_evidence,
        alternate_method_available=alternate_method_available,
        source_quality=source_quality,
        method_outcome_refs=tuple(item.outcome_id for item in normalized_outcomes),
        alternate_method_ids=alternate_method_ids,
        decision_slot_id=decision_slot_id,
        attempt_id=attempt_id,
    )


@dataclass(frozen=True, slots=True)
class PortfolioExecution:
    """Pure execution projection containing batches, alternatives, and assessments."""

    portfolio_id: str
    batches: tuple[PortfolioBatch, ...]
    assessments: tuple[BatchCoverageAssessment, ...]
    alternatives: tuple[MethodSelection, ...]
    degraded_capability: bool
    schema_version: int = PORTFOLIO_EXECUTION_SCHEMA_VERSION
    kind: str = PORTFOLIO_EXECUTION_KIND

    def __post_init__(self) -> None:
        object.__setattr__(self, "portfolio_id", _identifier(self.portfolio_id, "portfolio_id"))
        object.__setattr__(
            self,
            "schema_version",
            _schema_version(self.schema_version, PORTFOLIO_EXECUTION_SCHEMA_VERSION, "PortfolioExecution"),
        )
        if self.kind != PORTFOLIO_EXECUTION_KIND:
            raise InvalidSearchPortfolioError("PortfolioExecution kind is invalid")
        batches = _sequence(self.batches, "batches")
        assessments = _sequence(self.assessments, "assessments")
        alternatives = _sequence(self.alternatives, "alternatives")
        if any(not isinstance(item, PortfolioBatch) for item in batches):
            raise InvalidSearchPortfolioError("batches must contain PortfolioBatch values")
        if any(not isinstance(item, BatchCoverageAssessment) for item in assessments):
            raise InvalidSearchPortfolioError("assessments must contain BatchCoverageAssessment values")
        if any(not isinstance(item, MethodSelection) for item in alternatives):
            raise InvalidSearchPortfolioError("alternatives must contain MethodSelection values")
        if len(batches) != len(assessments):
            raise InvalidSearchPortfolioError("each batch must have exactly one assessment")
        if any(item.portfolio_id != self.portfolio_id for item in batches + assessments):
            raise InvalidSearchPortfolioError("execution values must belong to the portfolio")
        if not isinstance(self.degraded_capability, bool):
            raise InvalidSearchPortfolioError("degraded_capability must be bool")
        object.__setattr__(self, "batches", tuple(batches))
        object.__setattr__(self, "assessments", tuple(assessments))
        object.__setattr__(self, "alternatives", tuple(alternatives))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "portfolio_id": self.portfolio_id,
            "batches": [item.to_dict() for item in self.batches],
            "assessments": [item.to_dict() for item in self.assessments],
            "alternatives": [item.to_dict() for item in self.alternatives],
            "degraded_capability": self.degraded_capability,
        }

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> "PortfolioExecution":
        data = _exact_mapping(
            value,
            {"schema_version", "kind", "portfolio_id", "batches", "assessments", "alternatives", "degraded_capability"},
            "PortfolioExecution",
        )
        return cls(
            portfolio_id=data["portfolio_id"],
            batches=tuple(PortfolioBatch.from_dict(item) for item in _sequence(data["batches"], "batches")),
            assessments=tuple(
                BatchCoverageAssessment.from_dict(item) for item in _sequence(data["assessments"], "assessments")
            ),
            alternatives=tuple(
                MethodSelection.from_dict(item) for item in _sequence(data["alternatives"], "alternatives")
            ),
            degraded_capability=data["degraded_capability"],
            schema_version=data["schema_version"],
            kind=data["kind"],
        )


def _runtime_ref(value: ArtifactRef | ArtifactRevision | Mapping[str, Any] | str, label: str) -> ArtifactRef:
    if isinstance(value, ArtifactRevision):
        return ArtifactRef(value.round_id, value.id, value.revision)
    if isinstance(value, ArtifactRef):
        return value
    if isinstance(value, Mapping):
        try:
            return ArtifactRef.from_dict(value)
        except (RuntimeStoreError, TypeError, ValueError) as error:
            raise SearchPortfolioError(f"{label} must be an exact artifact reference") from error
    if isinstance(value, str):
        normalized = value.strip()
        if "@" in normalized:
            raise SearchPortfolioError(f"{label} requires a run-bound artifact reference")
        parts = normalized.split(":")
        if len(parts) == 3:
            try:
                return ArtifactRef(parts[0], parts[1], int(parts[2]))
            except (RuntimeStoreError, TypeError, ValueError) as error:
                raise SearchPortfolioError(f"{label} must be an exact artifact reference") from error
    raise SearchPortfolioError(f"{label} must be an exact artifact reference")


def _runtime_ref_in_run(
    value: ArtifactRef | ArtifactRevision | Mapping[str, Any] | str, run_id: str, label: str
) -> ArtifactRef:
    if isinstance(value, str) and "@" in value:
        artifact_id, revision = value.strip().rsplit("@", 1)
        try:
            return ArtifactRef(run_id, artifact_id, int(revision))
        except (RuntimeStoreError, TypeError, ValueError) as error:
            raise SearchPortfolioError(f"{label} must be an exact artifact reference") from error
    reference = _runtime_ref(value, label)
    if not reference.round_id:
        reference = ArtifactRef(run_id, reference.artifact_id, reference.revision)
    if reference.round_id != run_id:
        raise SearchPortfolioError(f"{label} belongs to another run")
    return reference


def _runtime_artifact_ref(artifact: ArtifactRevision) -> ArtifactRef:
    return ArtifactRef(artifact.round_id, artifact.id, artifact.revision)


class SearchPortfolioService:
    """Persist typed portfolio execution through the canonical run ledger."""

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
        run_id = _identifier(run_id, "run_id")
        if not isinstance(registry, MethodRegistry):
            raise InvalidSearchPortfolioError("registry must be a MethodRegistry")
        payload = {"run_id": run_id, **registry.to_dict()}
        existing = self._existing(run_id, registry.registry_id, METHOD_REGISTRY_KIND)
        if existing is not None:
            if thaw_json(existing.payload) == payload:
                return existing
            raise SearchPortfolioError("method registry id conflicts with an existing payload")
        return self._append(
            run_id,
            registry.registry_id,
            METHOD_REGISTRY_KIND,
            payload,
            (),
            expected_revision,
        )

    def plan(
        self,
        *,
        run_id: str,
        plan: IntentDerivedSearchPortfolioPlan | None = None,
        portfolio: SearchPortfolio | None = None,
        intent_model: ArtifactRevision,
        working_brief: ArtifactRevision,
        strategy: ArtifactRevision,
        decision_map: ArtifactRevision,
        method_registry: ArtifactRevision | None = None,
        expected_revision: int,
    ) -> ArtifactRevision:
        run_id = _identifier(run_id, "run_id")
        if plan is not None and not isinstance(plan, IntentDerivedSearchPortfolioPlan):
            raise SearchPortfolioError("plan must be an IntentDerivedSearchPortfolioPlan")
        if plan is not None:
            portfolio_value = plan.portfolio
            registry = plan.registry
        elif isinstance(portfolio, SearchPortfolio):
            portfolio_value = portfolio
            registry = None
        else:
            raise SearchPortfolioError("plan or portfolio is required")
        if portfolio_value.run_id != run_id:
            raise SearchPortfolioError("portfolio belongs to another run")
        intent = self._current(intent_model, run_id, "intent-model", "intent_model")
        brief = self._current(working_brief, run_id, "working-brief", "working_brief")
        strategy_artifact = self._current(strategy, run_id, strategy.kind, "strategy")
        decision = self._current(decision_map, run_id, "blueprint-target", "decision_map")
        intent_ref = _runtime_artifact_ref(intent)
        brief_ref = _runtime_artifact_ref(brief)
        strategy_ref = _runtime_artifact_ref(strategy_artifact)
        decision_ref = _runtime_artifact_ref(decision)
        if intent_ref not in brief.parent_refs:
            raise SearchPortfolioError("working_brief lacks exact intent lineage")
        if decision_ref not in strategy_artifact.parent_refs:
            raise SearchPortfolioError("strategy lacks exact decision map lineage")
        if registry is None:
            if method_registry is None:
                raise SearchPortfolioError("method registry is required when plan is not supplied")
            registry_artifact = self._current(method_registry, run_id, METHOD_REGISTRY_KIND, "method_registry")
            registry = self._registry_from_artifact(registry_artifact, run_id)
            registry_ref = _runtime_artifact_ref(registry_artifact)
        elif method_registry is None:
            registry_artifact = self.register_methods(
                run_id=run_id,
                registry=registry,
                expected_revision=expected_revision,
            )
            registry_ref = _runtime_artifact_ref(registry_artifact)
            expected_revision = self.ledger.get_revision(run_id)
        else:
            registry_artifact = self._current(method_registry, run_id, METHOD_REGISTRY_KIND, "method_registry")
            persisted_registry = self._registry_from_artifact(registry_artifact, run_id)
            if persisted_registry.to_dict() != registry.to_dict():
                raise SearchPortfolioError("method registry does not match the plan")
            registry_ref = _runtime_artifact_ref(registry_artifact)
        portfolio_value.validate_against(registry)
        expected_lineage = {
            "intent_model_ref": intent_ref,
            "working_brief_ref": brief_ref,
            "strategy_ref": strategy_ref,
            "decision_map_ref": decision_ref,
            "method_registry_ref": registry_ref,
            "decision_slot_id": portfolio_value.slot_id,
        }
        query_variants = (
            [
                {
                    "query_ref": rewrite.query_ref,
                    "query_id": rewrite.query_ref,
                    "subquestion_id": rewrite.subquestion_id,
                    "method_id": rewrite.method_id,
                    "provider_id": rewrite.provider_id,
                    "intent_revision": rewrite.intent_revision,
                    "brief_revision": rewrite.brief_revision,
                    "strategy_revision": rewrite.strategy_revision,
                    "decision_slot_id": rewrite.decision_slot_id,
                    "evidence_deficit_revision": rewrite.evidence_deficit_revision,
                    "evidence_class": rewrite.evidence_class,
                    "decision_effect": rewrite.decision_effect,
                    "closure_oracle": rewrite.closure_oracle,
                    "stop_or_replan_trigger": rewrite.stop_or_replan_trigger,
                }
                for rewrite in plan.query_rewrites
            ]
            if plan is not None
            else [
                {
                    "query_ref": query_ref,
                    "query_id": query_ref,
                    "method_id": selection.method_id,
                    "provider_id": selection.provider_id,
                }
                for selection in portfolio_value.selected_methods
                for query_ref in selection.query_refs
            ]
        )
        planned_subquestions = (
            [item.subquestion.to_dict() for item in plan.planned_subquestions]
            if plan
            else [item.to_dict() for item in portfolio_value.subquestions]
        )
        method_selection = [
            {**selection.to_dict(), "status": "accepted"} for selection in portfolio_value.selected_methods
        ]
        payload = {
            **portfolio_value.to_dict(),
            "run_id": run_id,
            "status": "active",
            "lineage": {
                key: value.to_dict() if isinstance(value, ArtifactRef) else value
                for key, value in expected_lineage.items()
            },
            "subquestions": planned_subquestions,
            "query_variants": query_variants,
            "method_selection": method_selection,
            "method_registry_ref": registry_ref.to_dict(),
            "human_decision_reopen": bool(plan.human_decision_reopen) if plan else False,
        }
        parents = tuple(
            expected_lineage[key]
            for key in (
                "intent_model_ref",
                "working_brief_ref",
                "strategy_ref",
                "decision_map_ref",
                "method_registry_ref",
            )
        )
        existing = self._existing(run_id, portfolio_value.portfolio_id, SEARCH_PORTFOLIO_KIND)
        if existing is not None:
            if thaw_json(existing.payload) == payload:
                return existing
            raise SearchPortfolioError("portfolio id conflicts with an existing payload")
        return self._append(
            run_id,
            portfolio_value.portfolio_id,
            SEARCH_PORTFOLIO_KIND,
            payload,
            parents,
            expected_revision,
        )

    def record_batch(
        self,
        *,
        run_id: str,
        batch: PortfolioBatch,
        portfolio_ref: ArtifactRef,
        finding_artifacts: Sequence[ArtifactRevision] = (),
        expected_revision: int,
    ) -> ArtifactRevision:
        run_id = _identifier(run_id, "run_id")
        if not isinstance(batch, PortfolioBatch):
            raise SearchPortfolioError("batch must be a PortfolioBatch")
        portfolio = self.validate_persisted_portfolio(run_id=run_id, portfolio_ref=portfolio_ref)
        if portfolio.payload.get("status") != "active" or portfolio.id != batch.portfolio_id:
            raise SearchPortfolioError("batch portfolio is not active")
        finding_refs = self._validate_findings(finding_artifacts, run_id)
        portfolio_exact = _runtime_ref_in_run(portfolio_ref, run_id, "portfolio_ref")
        selection_by_boundary = {
            item.boundary: item
            for item in SearchPortfolio.from_dict(self._portfolio_fields(portfolio.payload)).selected_methods
        }
        outcome_specs: list[tuple[str, str, Any, Sequence[ArtifactRef]]] = []
        all_refs: list[ArtifactRef] = [portfolio_exact, *finding_refs]
        for outcome in batch.outcomes:
            selection = selection_by_boundary.get(outcome.boundary)
            if selection is None or not set(outcome.query_refs).issubset(set(selection.query_refs)):
                raise SearchPortfolioError("batch outcome is not bound to a selected query and method")
            capture_refs = self._outcome_refs(outcome.capture_refs, run_id, "capture_refs")
            receipt_refs = self._outcome_refs(outcome.receipt_refs, run_id, "receipt_refs")
            checkpoint_refs = self._outcome_refs(outcome.checkpoint_refs, run_id, "checkpoint_refs")
            for reference, kind in (
                *[(item, "source-capture") for item in capture_refs],
                *[(item, "acquisition-receipt") for item in receipt_refs],
                *[(item, "analysis-checkpoint") for item in checkpoint_refs],
            ):
                self._stored(reference, run_id, kind, "batch lineage")
            refs = tuple(
                dict.fromkeys((portfolio_exact, *capture_refs, *receipt_refs, *checkpoint_refs, *finding_refs))
            )
            all_refs.extend(refs)
            outcome_specs.append(
                (outcome.outcome_id, METHOD_EXECUTION_OUTCOME_KIND, {"run_id": run_id, **outcome.to_dict()}, refs)
            )
        batch_payload = {
            "run_id": run_id,
            **batch.to_dict(),
            "portfolio_ref": portfolio_exact.to_dict(),
            "finding_refs": [reference.to_dict() for reference in finding_refs],
            "status": "recorded",
        }
        batch_parents = tuple(
            dict.fromkeys(
                all_refs
                + [
                    ArtifactRef(run_id, outcome.outcome_id, self._next_artifact_revision(run_id, outcome.outcome_id))
                    for outcome in batch.outcomes
                ]
            )
        )
        existing = self._existing(run_id, batch.batch_id, PORTFOLIO_BATCH_KIND)
        if existing is not None:
            if thaw_json(existing.payload) == batch_payload:
                return existing
            raise SearchPortfolioError("batch id conflicts with an existing payload")
        try:
            created = self.ledger.append_artifact_batch(
                run_id,
                (*outcome_specs, (batch.batch_id, PORTFOLIO_BATCH_KIND, batch_payload, batch_parents)),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise SearchPortfolioError("stale ledger revision") from error
        return created[-1]

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
        finding_artifacts: Sequence[ArtifactRevision] = (),
        batch_ref: ArtifactRef | None = None,
        successor_strategy: ArtifactRevision | None = None,
    ) -> ArtifactRevision:
        run_id = _identifier(run_id, "run_id")
        if not isinstance(assessment, BatchCoverageAssessment):
            raise SearchPortfolioError("assessment must be a BatchCoverageAssessment")
        portfolio = self.validate_persisted_portfolio(run_id=run_id, portfolio_ref=portfolio_ref)
        portfolio_exact = _runtime_ref_in_run(portfolio_ref, run_id, "portfolio_ref")
        if portfolio.id != assessment.portfolio_id or portfolio.payload.get("status") != "active":
            raise SearchPortfolioError("assessment portfolio is not active")
        captures = self._bound_artifacts(
            capture_artifacts, run_id, "source-capture", "capture_artifacts", statuses=("committed",)
        )
        receipts = self._bound_artifacts(
            receipt_artifacts, run_id, "acquisition-receipt", "receipt_artifacts", statuses=("succeeded",)
        )
        checkpoints = self._bound_artifacts(checkpoint_artifacts, run_id, "analysis-checkpoint", "checkpoint_artifacts")
        findings = self._validate_findings(finding_artifacts, run_id)
        if assessment.evidence_disposition == "captured" and not captures:
            raise SearchPortfolioError("captured assessment requires source captures")
        if assessment.evidence_disposition == "captured" and not findings:
            raise SearchPortfolioError("captured assessment requires finding lineage")
        capture_refs = tuple(_runtime_artifact_ref(item) for item in captures)
        receipt_refs = tuple(_runtime_artifact_ref(item) for item in receipts)
        checkpoint_refs = tuple(_runtime_artifact_ref(item) for item in checkpoints)
        capture_ids = {reference.artifact_id for reference in capture_refs}
        for receipt in receipts:
            capture_id = receipt.payload.get("capture_id")
            if capture_id is not None and str(capture_id) not in capture_ids:
                raise SearchPortfolioError("receipt capture lineage does not match assessment")
        for checkpoint in checkpoints:
            checkpoint_captures = checkpoint.payload.get("source_capture_refs", ())
            if capture_refs and not any(
                _runtime_ref_in_run(value, run_id, "checkpoint source_capture_ref") in capture_refs
                for value in checkpoint_captures
            ):
                raise SearchPortfolioError("checkpoint capture lineage does not match assessment")
        if set(assessment.capture_refs) != {f"{item.artifact_id}@{item.revision}" for item in capture_refs}:
            raise SearchPortfolioError("assessment capture_refs do not match committed artifacts")
        if set(assessment.receipt_refs) != {f"{item.artifact_id}@{item.revision}" for item in receipt_refs}:
            raise SearchPortfolioError("assessment receipt_refs do not match committed artifacts")
        if set(assessment.checkpoint_refs) != {f"{item.artifact_id}@{item.revision}" for item in checkpoint_refs}:
            raise SearchPortfolioError("assessment checkpoint_refs do not match committed artifacts")
        for artifact in (*captures, *receipts, *checkpoints):
            if assessment.attempt_id is not None and str(artifact.payload.get("attempt_id")) != assessment.attempt_id:
                raise SearchPortfolioError("assessment artifact belongs to another attempt")
        strategy_ref = self._validate_successor_strategy(portfolio, successor_strategy, run_id, assessment)
        batch_exact = None
        if batch_ref is not None:
            batch_exact = _runtime_ref_in_run(batch_ref, run_id, "batch_ref")
            self._stored(batch_exact, run_id, PORTFOLIO_BATCH_KIND, "batch_ref")
        parent_values: list[ArtifactRef] = [portfolio_exact]
        if batch_exact is not None:
            parent_values.append(batch_exact)
        parent_values.extend((*capture_refs, *receipt_refs, *checkpoint_refs, *findings))
        if strategy_ref is not None:
            parent_values.append(strategy_ref)
        parents = tuple(dict.fromkeys(parent_values))
        payload = {
            "schema_version": BATCH_COVERAGE_ASSESSMENT_SCHEMA_VERSION,
            "kind": BATCH_COVERAGE_ASSESSMENT_KIND,
            "run_id": run_id,
            "portfolio_ref": portfolio_exact.to_dict(),
            "batch_ref": batch_exact.to_dict() if batch_exact else None,
            "finding_refs": [reference.to_dict() for reference in findings],
            "assessment": assessment.to_dict(),
            "status": "recorded",
        }
        assessment_ref = ArtifactRef(
            run_id, assessment.assessment_id, self._next_artifact_revision(run_id, assessment.assessment_id)
        )
        decision_id = f"decision-{assessment.assessment_id}"
        decision_payload = {
            "schema_version": PORTFOLIO_DECISION_SCHEMA_VERSION,
            "kind": PORTFOLIO_DECISION_KIND,
            "run_id": run_id,
            "portfolio_ref": portfolio_exact.to_dict(),
            "assessment_ref": assessment_ref.to_dict(),
            "decision": assessment.disposition,
            "next_actions": list(assessment.next_actions),
            "authority_disposition": assessment.authority_disposition,
            "status": "awaiting-human-reopen"
            if assessment.authority_disposition == "requires_requester_reopen"
            else "recorded",
            "successor_strategy_ref": strategy_ref.to_dict() if strategy_ref else None,
        }
        existing = self._existing(run_id, assessment.assessment_id, BATCH_COVERAGE_ASSESSMENT_KIND)
        if existing is not None:
            return existing
        try:
            created = self.ledger.append_artifact_batch(
                run_id,
                (
                    (assessment.assessment_id, BATCH_COVERAGE_ASSESSMENT_KIND, payload, parents),
                    (
                        decision_id,
                        PORTFOLIO_DECISION_KIND,
                        decision_payload,
                        tuple([assessment_ref, *([strategy_ref] if strategy_ref is not None else [])]),
                    ),
                ),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise SearchPortfolioError("stale ledger revision") from error
        return created[0]

    def record_execution(
        self,
        *,
        run_id: str,
        portfolio_ref: ArtifactRef,
        execution: PortfolioExecution,
        finding_artifacts_by_batch: Mapping[str, Sequence[ArtifactRevision]] | None = None,
        capture_artifacts_by_batch: Mapping[str, Sequence[ArtifactRevision]] | None = None,
        receipt_artifacts_by_batch: Mapping[str, Sequence[ArtifactRevision]] | None = None,
        checkpoint_artifacts_by_batch: Mapping[str, Sequence[ArtifactRevision]] | None = None,
        expected_revision: int,
    ) -> tuple[ArtifactRevision, ...]:
        if not isinstance(execution, PortfolioExecution):
            raise SearchPortfolioError("execution must be a PortfolioExecution")
        finding_map = finding_artifacts_by_batch or {}
        capture_map = capture_artifacts_by_batch or {}
        receipt_map = receipt_artifacts_by_batch or {}
        checkpoint_map = checkpoint_artifacts_by_batch or {}
        results: list[ArtifactRevision] = []
        for batch, assessment in zip(execution.batches, execution.assessments):
            batch_artifact = self.record_batch(
                run_id=run_id,
                batch=batch,
                portfolio_ref=portfolio_ref,
                finding_artifacts=finding_map.get(batch.batch_id, ()),
                expected_revision=expected_revision,
            )
            expected_revision = self.ledger.get_revision(run_id)
            assessment_artifact = self.record_assessment(
                run_id=run_id,
                assessment=assessment,
                portfolio_ref=portfolio_ref,
                batch_ref=_runtime_artifact_ref(batch_artifact),
                capture_artifacts=capture_map.get(batch.batch_id, ()),
                receipt_artifacts=receipt_map.get(batch.batch_id, ()),
                checkpoint_artifacts=checkpoint_map.get(batch.batch_id, ()),
                finding_artifacts=finding_map.get(batch.batch_id, ()),
                expected_revision=expected_revision,
            )
            expected_revision = self.ledger.get_revision(run_id)
            results.extend((batch_artifact, assessment_artifact))
        return tuple(results)

    def validate_persisted_portfolio(self, *, run_id: str, portfolio_ref: ArtifactRef) -> ArtifactRevision:
        run_id = _identifier(run_id, "run_id")
        portfolio = self._stored(
            _runtime_ref_in_run(portfolio_ref, run_id, "portfolio_ref"), run_id, SEARCH_PORTFOLIO_KIND, "portfolio_ref"
        )
        if not self.ledger.is_latest_artifact(_runtime_artifact_ref(portfolio)):
            raise SearchPortfolioError("portfolio_ref must identify a current portfolio")
        payload = self._portfolio_fields(portfolio.payload)
        parsed = SearchPortfolio.from_dict(payload)
        registry_ref_value = portfolio.payload.get("method_registry_ref") or portfolio.payload.get("lineage", {}).get(
            "method_registry_ref"
        )
        registry_ref = _runtime_ref_in_run(registry_ref_value, run_id, "method_registry_ref")
        registry_artifact = self._stored(registry_ref, run_id, METHOD_REGISTRY_KIND, "method_registry_ref")
        parsed.validate_against(self._registry_from_artifact(registry_artifact, run_id))
        if registry_ref not in portfolio.parent_refs:
            raise SearchPortfolioError("portfolio lacks method registry lineage")
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
        portfolio = self.validate_persisted_portfolio(run_id=run_id, portfolio_ref=portfolio_ref)
        assessment = self._stored(
            _runtime_ref_in_run(assessment_ref, run_id, "assessment_ref"),
            run_id,
            BATCH_COVERAGE_ASSESSMENT_KIND,
            "assessment_ref",
        )
        if not self.ledger.is_latest_artifact(_runtime_artifact_ref(assessment)):
            raise SearchPortfolioError("assessment_ref must identify a current assessment")
        payload = thaw_json(assessment.payload)
        if payload.get("portfolio_ref") != _runtime_ref_in_run(portfolio_ref, run_id, "portfolio_ref").to_dict():
            raise SearchPortfolioError("assessment lacks exact portfolio lineage")
        value = BatchCoverageAssessment.from_dict(payload["assessment"])
        if value.attempt_id != attempt_id or value.portfolio_id != portfolio.id:
            raise SearchPortfolioError("assessment does not match worker attempt")
        for name, kind in (
            ("capture_refs", "source-capture"),
            ("receipt_refs", "acquisition-receipt"),
            ("checkpoint_refs", "analysis-checkpoint"),
        ):
            for raw_ref in getattr(value, name):
                reference = _runtime_ref_in_run(raw_ref, run_id, name)
                if reference not in assessment.parent_refs:
                    raise SearchPortfolioError(f"assessment {name} are not parents")
                self._stored(reference, run_id, kind, name)
        for raw_ref in payload.get("finding_refs", ()):
            reference = _runtime_ref_in_run(raw_ref, run_id, "finding_ref")
            if reference not in assessment.parent_refs:
                raise SearchPortfolioError("assessment finding lineage is incomplete")
            self._stored(reference, run_id, "finding-pack", "finding_ref")
        if expected_method_id or expected_provider_id:
            outcome_refs: list[ArtifactRef] = [
                reference
                for reference in assessment.parent_refs
                if self._kind_at(reference) == METHOD_EXECUTION_OUTCOME_KIND
            ]
            batch_value = payload.get("batch_ref")
            if isinstance(batch_value, Mapping):
                batch_artifact = self._stored(
                    ArtifactRef.from_dict(batch_value),
                    run_id,
                    PORTFOLIO_BATCH_KIND,
                    "batch_ref",
                )
                outcome_refs.extend(
                    reference
                    for reference in batch_artifact.parent_refs
                    if self._kind_at(reference) == METHOD_EXECUTION_OUTCOME_KIND
                )
            outcomes = [
                self._stored(reference, run_id, METHOD_EXECUTION_OUTCOME_KIND, "method outcome")
                for reference in dict.fromkeys(outcome_refs)
            ]
            if not outcomes or any(
                expected_method_id is not None
                and item.payload.get("method_id") != expected_method_id
                or expected_provider_id is not None
                and item.payload.get("provider_id") != expected_provider_id
                for item in outcomes
            ):
                raise SearchPortfolioError("assessment method boundary does not match worker")
        return assessment

    def _append(
        self,
        run_id: str,
        artifact_id: str,
        kind: str,
        payload: Mapping[str, Any],
        parent_refs: Sequence[ArtifactRef],
        expected_revision: int,
    ) -> ArtifactRevision:
        try:
            return self.ledger.append_artifact(
                run_id,
                artifact_id,
                kind,
                payload,
                parent_refs=parent_refs,
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise SearchPortfolioError("stale ledger revision") from error

    def _existing(self, run_id: str, artifact_id: str, kind: str) -> ArtifactRevision | None:
        candidates = [
            item for item in self.ledger.list_artifacts(run_id) if item.id == artifact_id and item.kind == kind
        ]
        return max(candidates, key=lambda item: item.revision) if candidates else None

    def _next_artifact_revision(self, run_id: str, artifact_id: str) -> int:
        return (
            max((item.revision for item in self.ledger.list_artifacts(run_id) if item.id == artifact_id), default=0) + 1
        )

    def _stored(self, reference: ArtifactRef, run_id: str, kind: str, label: str) -> ArtifactRevision:
        if reference.round_id != run_id:
            raise SearchPortfolioError(f"{label} belongs to another run")
        try:
            artifact = self.ledger.get_artifact(reference)
        except (RuntimeStoreError, TypeError, ValueError) as error:
            raise SearchPortfolioError(f"{label} is unresolved") from error
        if artifact.kind != kind:
            raise SearchPortfolioError(f"{label} must identify {kind}")
        if not self.ledger.is_latest_artifact(reference):
            raise SearchPortfolioError(f"{label} is stale")
        return artifact

    def _current(self, value: ArtifactRevision, run_id: str, kind: str, label: str) -> ArtifactRevision:
        if not isinstance(value, ArtifactRevision):
            raise SearchPortfolioError(f"{label} must be an ArtifactRevision")
        return self._stored(_runtime_artifact_ref(value), run_id, kind, label)

    def _registry_from_artifact(self, artifact: ArtifactRevision, run_id: str) -> MethodRegistry:
        payload = thaw_json(artifact.payload)
        if payload.get("run_id") != run_id:
            raise SearchPortfolioError("method registry belongs to another run")
        try:
            return MethodRegistry.from_dict(
                {
                    "schema_version": payload["schema_version"],
                    "kind": payload["kind"],
                    "registry_id": payload["registry_id"],
                    "registrations": payload["registrations"],
                }
            )
        except (KeyError, TypeError, ValueError, RuntimeStoreError) as error:
            raise SearchPortfolioError("method registry payload is invalid") from error

    @staticmethod
    def _portfolio_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
        fields = {
            "schema_version",
            "kind",
            "portfolio_id",
            "run_id",
            "slot_id",
            "intent_revision",
            "brief_revision",
            "subquestions",
            "selected_methods",
            "rejected_methods",
            "reassessment_policy",
            "status",
        }
        return {key: payload[key] for key in fields if key in payload}

    def _bound_artifacts(
        self,
        values: Sequence[ArtifactRevision],
        run_id: str,
        kind: str,
        label: str,
        statuses: Sequence[str] = (),
    ) -> tuple[ArtifactRevision, ...]:
        result: list[ArtifactRevision] = []
        for value in values:
            if not isinstance(value, ArtifactRevision):
                raise SearchPortfolioError(f"{label} must contain ArtifactRevision values")
            artifact = self._stored(_runtime_artifact_ref(value), run_id, kind, label)
            if statuses and artifact.payload.get("status") not in statuses:
                raise SearchPortfolioError(f"{label} contains an unavailable artifact")
            result.append(artifact)
        return tuple(result)

    def _validate_findings(self, values: Sequence[ArtifactRevision], run_id: str) -> tuple[ArtifactRef, ...]:
        result: list[ArtifactRef] = []
        for value in values:
            if not isinstance(value, ArtifactRevision):
                raise SearchPortfolioError("finding_artifacts must contain ArtifactRevision values")
            result.append(
                _runtime_artifact_ref(self._stored(_runtime_artifact_ref(value), run_id, "finding-pack", "finding"))
            )
        return tuple(result)

    def _outcome_refs(self, values: Sequence[str], run_id: str, label: str) -> tuple[ArtifactRef, ...]:
        return tuple(_runtime_ref_in_run(value, run_id, label) for value in values)

    def _kind_at(self, reference: ArtifactRef) -> str:
        try:
            return self.ledger.get_artifact(reference).kind
        except RuntimeStoreError:
            return ""

    def _validate_successor_strategy(
        self,
        portfolio: ArtifactRevision,
        successor: ArtifactRevision | None,
        run_id: str,
        assessment: BatchCoverageAssessment,
    ) -> ArtifactRef | None:
        if assessment.disposition != "pivot":
            if successor is not None:
                raise SearchPortfolioError("successor strategy is only valid for a pivot")
            return None
        if successor is None:
            raise SearchPortfolioError("pivot requires a persisted successor strategy")
        reference = _runtime_artifact_ref(
            self._stored(_runtime_artifact_ref(successor), run_id, successor.kind, "successor_strategy")
        )
        lineage = portfolio.payload.get("lineage")
        previous = lineage.get("strategy_ref") if isinstance(lineage, Mapping) else None
        previous_ref = _runtime_ref_in_run(previous, run_id, "strategy_ref")
        if previous_ref not in successor.parent_refs:
            raise SearchPortfolioError("successor strategy must preserve the superseded strategy lineage")
        return reference


class SearchPortfolioExecutor:
    """Validate selected boundaries and assess dependency-ready execution waves."""

    def __init__(self, registry: MethodRegistry) -> None:
        if not isinstance(registry, MethodRegistry):
            raise InvalidSearchPortfolioError("registry must be a MethodRegistry")
        self._registry = registry

    def run(
        self,
        portfolio: SearchPortfolio,
        adapters: Mapping[tuple[str, str], Any],
        *,
        batch_id: str = "batch-1",
    ) -> PortfolioExecution:
        if not isinstance(adapters, Mapping):
            raise InvalidSearchPortfolioError("adapters must be a mapping")
        if not isinstance(portfolio, SearchPortfolio):
            raise InvalidSearchPortfolioError("portfolio must be a SearchPortfolio")
        outcomes: list[MethodExecutionOutcome] = []
        for index, selection in enumerate(portfolio.selected_methods, 1):
            adapter = adapters.get(selection.boundary)
            if adapter is None:
                outcomes.append(
                    MethodExecutionOutcome(
                        outcome_id=f"{batch_id}-m{index}",
                        portfolio_id=portfolio.portfolio_id,
                        batch_id=batch_id,
                        method_id=selection.method_id,
                        provider_id=selection.provider_id,
                        failure_boundary=selection.failure_boundary,
                        selection_reason=selection.selection_reason,
                        disposition="unavailable",
                        query_refs=selection.query_refs,
                        unresolved_decision_risk="unknown",
                        error_code="adapter-unavailable",
                    )
                )
                continue
            if not callable(adapter):
                raise InvalidSearchPortfolioError("method adapter must be callable")
            produced = adapter(selection)
            if isinstance(produced, MethodExecutionOutcome):
                outcome = produced
            elif isinstance(produced, Mapping):
                payload = dict(produced)
                if "schema_version" in payload or "kind" in payload:
                    outcome = MethodExecutionOutcome.from_dict(payload)
                else:
                    outcome = MethodExecutionOutcome(**payload)
            else:
                raise InvalidSearchPortfolioError("method adapter must return a MethodExecutionOutcome or mapping")
            outcomes.append(outcome)
        return self.execute(portfolio, (PortfolioBatch(batch_id, portfolio.portfolio_id, tuple(outcomes)),))

    def execute(
        self,
        portfolio: SearchPortfolio,
        batches: Sequence[PortfolioBatch | Mapping[str, Any]],
    ) -> PortfolioExecution:
        if not isinstance(portfolio, SearchPortfolio):
            raise InvalidSearchPortfolioError("portfolio must be a SearchPortfolio")
        portfolio.validate_against(self._registry)
        normalized_batches = tuple(
            item if isinstance(item, PortfolioBatch) else PortfolioBatch.from_dict(item)
            for item in _sequence(batches, "batches")
        )
        if any(item.portfolio_id != portfolio.portfolio_id for item in normalized_batches):
            raise InvalidSearchPortfolioError("batch portfolio_id must match SearchPortfolio")
        selected_boundaries = {item.boundary for item in portfolio.selected_methods}
        registry_by_boundary = {item.boundary: item for item in self._registry.registrations}
        attempted_boundaries: set[tuple[str, str]] = set()
        alternative_boundaries: set[tuple[str, str]] = set()
        alternatives: list[MethodSelection] = []
        assessments: list[BatchCoverageAssessment] = []
        for batch in normalized_batches:
            for outcome in batch.outcomes:
                boundary = outcome.boundary
                if boundary not in selected_boundaries:
                    raise InvalidSearchPortfolioError("outcome boundary must be selected in the portfolio")
                registration = registry_by_boundary.get(boundary)
                if registration is None or registration.failure_boundary != outcome.failure_boundary:
                    raise InvalidSearchPortfolioError("outcome failure_boundary does not match its registry")
                attempted_boundaries.add(boundary)
            candidates = tuple(
                item
                for item in self._registry.registrations
                if item.boundary not in attempted_boundaries and item.availability != "unavailable"
            )
            if any(item.is_failure for item in batch.outcomes):
                for index, registration in enumerate(candidates, 1):
                    if registration.boundary in alternative_boundaries:
                        continue
                    alternative_boundaries.add(registration.boundary)
                    alternatives.append(
                        MethodSelection(
                            method_id=registration.method_id,
                            provider_id=registration.provider_id,
                            failure_boundary=registration.failure_boundary,
                            query_refs=(f"{batch.batch_id}-fallback-{index}",),
                            selection_reason="fallback",
                        )
                    )
            assessments.append(
                assess_acquisition_batch(
                    assessment_id=f"{batch.batch_id}-assessment",
                    portfolio_id=portfolio.portfolio_id,
                    batch_id=batch.batch_id,
                    outcomes=batch.outcomes,
                    alternate_method_available=bool(candidates),
                    alternate_method_ids=tuple(item.method_id for item in candidates),
                )
            )
        available = tuple(item for item in self._registry.registrations if item.availability != "unavailable")
        method_ids = {item.method_id for item in available}
        provider_ids = {item.provider_id for item in available}
        degraded = len(available) < 2 or len(method_ids) < 2 or len(provider_ids) < 2
        return PortfolioExecution(
            portfolio_id=portfolio.portfolio_id,
            batches=normalized_batches,
            assessments=tuple(assessments),
            alternatives=tuple(alternatives),
            degraded_capability=degraded,
        )


__all__ = [
    "ACQUISITION_DISPOSITIONS",
    "AcquisitionOutcome",
    "BATCH_COVERAGE_ASSESSMENT_KIND",
    "BATCH_COVERAGE_ASSESSMENT_SCHEMA_VERSION",
    "BATCH_COVERAGE_LEVELS",
    "BATCH_DECISION_RISK_LEVELS",
    "BATCH_DECISIONS",
    "BATCH_NOVELTY_LEVELS",
    "BATCH_PROVENANCE_LEVELS",
    "BATCH_SOURCE_DEPTH_LEVELS",
    "BATCH_SOURCE_QUALITY_LEVELS",
    "BatchCoverageAssessment",
    "DECISION_IMPACTS",
    "DEGRADATION_REASONS",
    "InvalidSearchPortfolioError",
    "METHOD_AVAILABILITY",
    "METHOD_REGISTRY_KIND",
    "METHOD_REGISTRY_SCHEMA_VERSION",
    "METHOD_EXECUTION_OUTCOME_KIND",
    "METHOD_EXECUTION_OUTCOME_SCHEMA_VERSION",
    "MATERIAL_HUMAN_DECISION_DIMENSIONS",
    "MethodRegistration",
    "MethodExecutionOutcome",
    "MethodRegistry",
    "MethodSelection",
    "PORTFOLIO_STATUSES",
    "PORTFOLIO_BATCH_KIND",
    "PORTFOLIO_BATCH_SCHEMA_VERSION",
    "PORTFOLIO_EXECUTION_KIND",
    "PORTFOLIO_EXECUTION_SCHEMA_VERSION",
    "PORTFOLIO_DECISION_KIND",
    "PORTFOLIO_DECISION_SCHEMA_VERSION",
    "PortfolioBatch",
    "PortfolioExecution",
    "SearchPortfolioService",
    "PLANNING_COVERAGE",
    "REASSESSMENT_DISPOSITIONS",
    "REJECTION_REASONS",
    "RejectedMethod",
    "ReassessmentPolicy",
    "IntentDerivedSearchPortfolioPlan",
    "IntentDerivedSearchPortfolioPlanner",
    "PlannedSubquestion",
    "QueryRewrite",
    "SEARCH_PORTFOLIO_KIND",
    "SEARCH_PORTFOLIO_SCHEMA_VERSION",
    "SELECTION_REASONS",
    "SUBQUESTION_KINDS",
    "SearchPortfolio",
    "SearchPortfolioError",
    "SearchPortfolioExecutor",
    "Subquestion",
    "derive_search_portfolio",
    "assess_acquisition_batch",
]
