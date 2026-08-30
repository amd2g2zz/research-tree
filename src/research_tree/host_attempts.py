"""Typed normalization of host attempt outcomes (#326).

Process exit codes are not truth: exit 0 with an authentication error, an
exhausted paid quota, or missing mandatory deliverables is a semantic failure,
not a finished worker.  This module is the mandatory normalization boundary
between raw host results and canonical event ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

HOST_ATTEMPT_HOSTS = frozenset({"codex", "claude-code", "hermes"})

# Dispositions are mutually exclusive; classification follows documented
# precedence when several signals co-occur.
ATTEMPT_DISPOSITIONS = frozenset(
    {
        "auth_failure",
        "provider_unavailable",
        "host_incompatible",
        "product_failure",
        "product_quality_failure",
        "unknown_outcome",
        "completed",
    }
)


class HostAttemptError(ValueError):
    """Raised when a host attempt outcome is malformed."""


class AttemptOutcome:
    """Dispositions a normalized attempt can carry (see ATTEMPT_DISPOSITIONS)."""

    AUTH_FAILURE = "auth_failure"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    HOST_INCOMPATIBLE = "host_incompatible"
    PRODUCT_FAILURE = "product_failure"
    PRODUCT_QUALITY_FAILURE = "product_quality_failure"
    UNKNOWN_OUTCOME = "unknown_outcome"
    COMPLETED = "completed"


_PROVIDER_AUTH_FAILURES = frozenset({"authentication_error", "invalid_api_key", "unauthorized", "http_401"})
_PROVIDER_UNAVAILABLE = frozenset(
    {"insufficient_balance", "quota_exhausted", "rate_limited_persistent", "http_429", "provider_down"}
)


@dataclass(frozen=True, slots=True)
class HostAttemptOutcome:
    """One normalized host attempt: every signal the acceptance requires."""

    process_exit: int | None
    timed_out: bool
    provider_disposition: str | None
    usage_disposition: str | None
    expected_deliverables: tuple[str, ...]
    observed_deliverables: tuple[str, ...]
    host_id: str
    session_id: str
    attempt_id: str
    canonical_event_refs: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_exit": self.process_exit,
            "timed_out": self.timed_out,
            "provider_disposition": self.provider_disposition,
            "usage_disposition": self.usage_disposition,
            "expected_deliverables": list(self.expected_deliverables),
            "observed_deliverables": list(self.observed_deliverables),
            "host_id": self.host_id,
            "session_id": self.session_id,
            "attempt_id": self.attempt_id,
            "canonical_event_refs": list(self.canonical_event_refs),
        }


def normalize_attempt(
    *,
    process_exit: int | None,
    timed_out: bool,
    provider_disposition: str | None,
    usage_disposition: str | None,
    expected_deliverables: Sequence[str],
    observed_deliverables: Sequence[str],
    host_id: str,
    session_id: str,
    attempt_id: str,
    canonical_event_refs: Sequence[str] = (),
) -> HostAttemptOutcome:
    """Build one outcome, failing fast on malformed identity."""

    if host_id not in HOST_ATTEMPT_HOSTS:
        raise HostAttemptError(f"host_id must be one of {sorted(HOST_ATTEMPT_HOSTS)}")
    if not isinstance(session_id, str) or not session_id:
        raise HostAttemptError("session_id must be a non-empty string")
    if not isinstance(attempt_id, str) or not attempt_id:
        raise HostAttemptError("attempt_id must be a non-empty string")
    if process_exit is not None and (isinstance(process_exit, bool) or not isinstance(process_exit, int)):
        raise HostAttemptError("process_exit must be an integer or None")
    for label, value in (("provider_disposition", provider_disposition), ("usage_disposition", usage_disposition)):
        if value is not None and (not isinstance(value, str) or not value):
            raise HostAttemptError(f"{label} must be None or a non-empty string")
    return HostAttemptOutcome(
        process_exit=process_exit,
        timed_out=bool(timed_out),
        provider_disposition=provider_disposition,
        usage_disposition=usage_disposition,
        expected_deliverables=tuple(expected_deliverables),
        observed_deliverables=tuple(observed_deliverables),
        host_id=host_id,
        session_id=session_id,
        attempt_id=attempt_id,
        canonical_event_refs=tuple(canonical_event_refs),
    )


def outcome_from_mapping(value: Mapping[str, Any]) -> HostAttemptOutcome:
    """Normalize from a host-event payload mapping (whitelist: extra keys rejected)."""

    required = {
        "process_exit",
        "timed_out",
        "host_id",
        "session_id",
        "attempt_id",
    }
    if not isinstance(value, Mapping):
        raise HostAttemptError("attempt outcome must be a mapping")
    actual = set(value)
    if not required <= actual:
        raise HostAttemptError(f"attempt outcome missing={sorted(required - actual)}")
    return normalize_attempt(
        process_exit=value["process_exit"],
        timed_out=value["timed_out"],
        provider_disposition=value.get("provider_disposition"),
        usage_disposition=value.get("usage_disposition"),
        expected_deliverables=value.get("expected_deliverables", ()),
        observed_deliverables=value.get("observed_deliverables", ()),
        host_id=value["host_id"],
        session_id=value["session_id"],
        attempt_id=value["attempt_id"],
        canonical_event_refs=value.get("canonical_event_refs", ()),
    )


def classify_attempt(outcome: HostAttemptOutcome) -> str:
    """Classify with documented precedence: timeout > auth > unavailable > incompatible > deliverables."""

    if outcome.timed_out or outcome.process_exit is None:
        return AttemptOutcome.UNKNOWN_OUTCOME
    provider = outcome.provider_disposition or ""
    usage = outcome.usage_disposition or ""
    if provider in _PROVIDER_AUTH_FAILURES:
        return AttemptOutcome.AUTH_FAILURE
    if provider in _PROVIDER_UNAVAILABLE or usage in _PROVIDER_UNAVAILABLE:
        return AttemptOutcome.PROVIDER_UNAVAILABLE
    if provider == "host_incompatible":
        return AttemptOutcome.HOST_INCOMPATIBLE
    mandatory_missing = [name for name in outcome.expected_deliverables if name not in outcome.observed_deliverables]
    if outcome.process_exit != 0 or mandatory_missing:
        return AttemptOutcome.PRODUCT_FAILURE
    partial_extra = [name for name in outcome.observed_deliverables if name not in outcome.expected_deliverables]
    if partial_extra or (
        outcome.expected_deliverables
        and len(set(outcome.observed_deliverables)) < len(set(outcome.expected_deliverables))
    ):
        return AttemptOutcome.PRODUCT_QUALITY_FAILURE
    if not outcome.expected_deliverables:
        return AttemptOutcome.PRODUCT_QUALITY_FAILURE
    return AttemptOutcome.COMPLETED


def worker_finished_eligible(outcome: HostAttemptOutcome) -> bool:
    """True only when the attempt may become worker_finished/verified/completed."""

    return classify_attempt(outcome) == AttemptOutcome.COMPLETED
