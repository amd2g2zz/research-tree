"""Hermes-specific translation into the shared HostEvent envelope."""

from __future__ import annotations

import re
from typing import Any, Mapping

from host_event_protocol import build_host_event, normalize_path

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MODEL_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_FAILURE_FIELDS = frozenset({"provider", "model", "retry_category", "error_code", "attempt", "gateway_log_path"})
_RETRY_CATEGORIES = frozenset({"transient", "rate_limited", "provider_unavailable", "unknown"})


class HermesEventError(ValueError):
    """Raised when Hermes observations cannot be safely translated."""


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise HermesEventError(f"{label} must be a bounded identifier")
    return value


def _model_identifier(value: Any) -> str:
    if not isinstance(value, str) or not _MODEL_IDENTIFIER.fullmatch(value):
        raise HermesEventError("model must be a bounded identifier")
    return value


def sanitize_provider_failure(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return only bounded provider metadata safe for canonical observation."""

    if not isinstance(payload, Mapping):
        raise HermesEventError("provider failure must be an object")
    unsupported = sorted(set(payload) - _FAILURE_FIELDS)
    if unsupported:
        raise HermesEventError(f"unsupported provider field: {unsupported[0]}")
    category = payload.get("retry_category")
    if category not in _RETRY_CATEGORIES:
        raise HermesEventError("unsupported retry category")
    attempt = payload.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise HermesEventError("attempt must be a positive integer")
    try:
        gateway_log_path = normalize_path(payload.get("gateway_log_path"))
    except (TypeError, ValueError) as error:
        raise HermesEventError(str(error)) from error
    return {
        "provider": _identifier(payload.get("provider"), "provider"),
        "model": _model_identifier(payload.get("model")),
        "category": category,
        "error_code": _identifier(payload.get("error_code"), "error code"),
        "attempt": attempt,
        "gateway_log_path": gateway_log_path,
    }


def build_hermes_event(*, kind: str, payload: Mapping[str, Any], **envelope: Any) -> dict[str, Any]:
    """Build one validated Hermes observation without persisting local state."""

    for field, label in (("event_id", "event id"), ("run_id", "run id"), ("attempt_id", "attempt id")):
        _identifier(envelope.get(field), label)
    for field, label in (("action_id", "action id"), ("decision_slot_id", "decision slot id")):
        if envelope.get(field) is not None:
            _identifier(envelope[field], label)
    if envelope.get("causation_id") is not None:
        _identifier(envelope["causation_id"], "causation id")
    revision = envelope.get("expected_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise HermesEventError("expected revision must be a nonnegative integer")
    sequence = envelope.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise HermesEventError("sequence must be a positive integer")
    normalized = sanitize_provider_failure(payload) if kind == "provider_failure" else dict(payload)
    # Issue #440: observations must carry a closed-vocabulary origin; Hermes
    # is a worker host, so its events use the vocabulary value "worker".
    if kind == "observation" and "origin" not in normalized:
        normalized["origin"] = "worker"
    try:
        return build_host_event(kind=kind, actor="worker", payload=normalized, **envelope)
    except (TypeError, ValueError) as error:
        raise HermesEventError(str(error)) from error


def project_hermes_action(action: Mapping[str, Any]) -> dict[str, Any]:
    """Project a coordinator-issued action into replaceable Hermes UI records."""

    action_id = _identifier(action.get("action_id"), "action id")
    attempt_id = _identifier(action.get("attempt_id"), "attempt id")
    objective = action.get("objective")
    criteria = action.get("acceptance_criteria")
    if not isinstance(objective, str) or not objective.strip():
        raise HermesEventError("objective must be non-empty")
    if not isinstance(criteria, list) or not criteria or not all(isinstance(item, str) and item for item in criteria):
        raise HermesEventError("acceptance criteria must be non-empty strings")
    return {
        "goal": {"id": action_id, "objective": objective, "acceptance_criteria": list(criteria)},
        "kanban": {
            "id": attempt_id,
            "action_id": action_id,
            "method": _identifier(action.get("method"), "method"),
            "status": "projected",
        },
        "authoritative": False,
    }


def recovery_events(
    *,
    run_id: str,
    action_id: str,
    attempt_id: str,
    expected_revision: int,
    next_sequence: int,
    unknown_event_id: str,
    retry_event_id: str,
    retry_category: str,
    method: str,
    authorized_methods: set[str] | frozenset[str],
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the ordered unknown/retry observations for one interrupted attempt."""

    if retry_category not in _RETRY_CATEGORIES:
        raise HermesEventError("unsupported retry category")
    if method not in authorized_methods:
        raise HermesEventError("method is not authorized for this action")
    common = {
        "run_id": run_id,
        "attempt_id": attempt_id,
        "expected_revision": expected_revision,
        "action_id": action_id,
        "created_at": created_at,
    }
    unknown = build_hermes_event(
        event_id=unknown_event_id,
        kind="unknown_outcome",
        sequence=next_sequence,
        payload={"reason": "interrupted_child"},
        **common,
    )
    retry = build_hermes_event(
        event_id=retry_event_id,
        kind="retry",
        sequence=next_sequence + 1,
        causation_id=unknown_event_id,
        payload={
            "retry_of": attempt_id,
            "category": retry_category,
            "method": method,
            "action_id": action_id,
        },
        **common,
    )
    return unknown, retry


__all__ = [
    "HermesEventError",
    "build_hermes_event",
    "project_hermes_action",
    "recovery_events",
    "sanitize_provider_failure",
]
