"""Strict value objects for intent-derived acquisition portfolios."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .domain import RuntimeStoreError, canonical_json_bytes, validate_identifier


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


__all__ = [
    "DECISION_IMPACTS",
    "DEGRADATION_REASONS",
    "InvalidSearchPortfolioError",
    "METHOD_AVAILABILITY",
    "METHOD_REGISTRY_KIND",
    "METHOD_REGISTRY_SCHEMA_VERSION",
    "MethodRegistration",
    "MethodRegistry",
    "MethodSelection",
    "PORTFOLIO_STATUSES",
    "REASSESSMENT_DISPOSITIONS",
    "REJECTION_REASONS",
    "RejectedMethod",
    "ReassessmentPolicy",
    "SEARCH_PORTFOLIO_KIND",
    "SEARCH_PORTFOLIO_SCHEMA_VERSION",
    "SELECTION_REASONS",
    "SUBQUESTION_KINDS",
    "SearchPortfolio",
    "SearchPortfolioError",
    "Subquestion",
]
