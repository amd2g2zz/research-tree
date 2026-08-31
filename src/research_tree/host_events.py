"""Typed, digest-bound host event envelopes.

Host adapters use this dependency-free module to translate provider-specific
observations into a common transport shape. The coordinator remains the only
component that can persist lifecycle state.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Mapping

from .domain import canonical_json_bytes, validate_identifier
from .origins import ORIGIN_TYPES

HOST_EVENT_SCHEMA_VERSION = 1
HOST_EVENT_KINDS = frozenset(
    {
        "dispatch",
        "attempt_started",
        "submission",
        "review",
        "provider_failure",
        "unknown_outcome",
        "retry",
        "worker_finished",
        "observation",
        "workflow_started",
        "workflow_resumed",
        "workflow_phase_completed",
        "checkpoint_persisted",
        "reconciliation_detected",
    }
)
_REQUIRED_PAYLOAD_FIELDS = {
    "dispatch": ("objective",),
    "attempt_started": (),
    "submission": ("evidence_refs",),
    "review": ("verdict",),
    "provider_failure": ("category", "provider", "model"),
    "unknown_outcome": ("reason",),
    "retry": ("retry_of",),
    "worker_finished": ("outcome",),
    "observation": (),
    "workflow_started": ("workflow_id", "capability_digest", "strategy_revision", "action_refs", "phase_refs"),
    "workflow_resumed": ("workflow_id", "capability_digest", "strategy_revision", "checkpoint_refs"),
    "workflow_phase_completed": ("workflow_id", "phase_id", "child_attempt_refs", "produced_artifact_refs"),
    "checkpoint_persisted": ("checkpoint_ref", "checkpoint_digest"),
    "reconciliation_detected": ("workflow_id", "classifications", "next_action"),
}


class HostEventError(ValueError):
    """Base error for malformed or unsupported host events."""


class HostEventDigestError(HostEventError):
    """Raised when the declared payload digest does not match the payload."""


class HostEventSequenceError(HostEventError):
    """Raised when an event sequence is stale or has a gap."""


@dataclass(frozen=True, slots=True)
class HostEvent:
    """Immutable host observation envelope."""

    event_id: str
    kind: str
    run_id: str
    round_id: str
    attempt_id: str
    expected_revision: int
    sequence: int
    actor: str
    created_at: str
    payload: Mapping[str, Any]
    payload_digest: str
    decision_slot_id: str | None = None
    action_id: str | None = None
    causation_id: str | None = None
    schema_version: int = HOST_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != HOST_EVENT_SCHEMA_VERSION:
            raise HostEventError("unsupported host-event schema_version")
        for value, label in (
            (self.event_id, "event_id"),
            (self.run_id, "run_id"),
            (self.round_id, "round_id"),
            (self.attempt_id, "attempt_id"),
            (self.actor, "actor"),
        ):
            try:
                validate_identifier(value, label)
            except (TypeError, ValueError) as error:
                raise HostEventError(f"{label} must be a valid identifier") from error
        if self.run_id != self.round_id:
            raise HostEventError("run_id and round_id must match")
        if self.kind not in HOST_EVENT_KINDS:
            raise HostEventError(f"unsupported host-event kind: {self.kind}")
        if isinstance(self.expected_revision, bool) or self.expected_revision < 0:
            raise HostEventError("expected_revision must be a nonnegative integer")
        if isinstance(self.sequence, bool) or self.sequence < 1:
            raise HostEventError("sequence must be a positive integer")
        try:
            datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError) as error:
            raise HostEventError("created_at must be an ISO-8601 timestamp") from error
        if not isinstance(self.payload, Mapping):
            raise HostEventError("payload must be a JSON object")
        normalized = normalize_host_payload(self.payload)
        if dict(normalized) != dict(self.payload):
            raise HostEventError("host-event payload paths must be normalized")
        missing = [field for field in _REQUIRED_PAYLOAD_FIELDS[self.kind] if field not in self.payload]
        if missing:
            raise HostEventError(f"{self.kind} payload missing: {', '.join(missing)}")
        # Issue #440: observations must carry a closed-vocabulary origin so
        # downstream consumers can tell retellings from verified facts.
        if self.kind == "observation":
            origin = self.payload.get("origin")
            if not isinstance(origin, str) or origin not in ORIGIN_TYPES:
                raise HostEventError(
                    f"observation payload origin must be one of {sorted(ORIGIN_TYPES)}; got {origin!r}"
                )
        if self.actor not in ORIGIN_TYPES:
            raise HostEventError(f"actor must be one of {sorted(ORIGIN_TYPES)}; got {self.actor!r}")
        if self.kind == "provider_failure":
            if not ({"opaque_code", "error_code"} & set(self.payload)):
                raise HostEventError("provider_failure payload missing: opaque_code or error_code")
            if not ({"safe_log_ref", "gateway_log_path"} & set(self.payload)):
                raise HostEventError("provider_failure payload missing: safe_log_ref or gateway_log_path")
        if not isinstance(self.payload_digest, str) or len(self.payload_digest) != 64:
            raise HostEventDigestError("payload_digest must be a SHA-256 hex digest")
        try:
            int(self.payload_digest, 16)
        except ValueError as error:
            raise HostEventDigestError("payload_digest must be hexadecimal") from error
        if self.payload_digest != payload_digest(self.payload):
            raise HostEventDigestError("payload_digest does not match payload")
        for value, label in (
            (self.decision_slot_id, "decision_slot_id"),
            (self.action_id, "action_id"),
            (self.causation_id, "causation_id"),
        ):
            if value is not None:
                try:
                    validate_identifier(value, label)
                except (TypeError, ValueError) as error:
                    raise HostEventError(f"{label} must be a valid identifier") from error

    @classmethod
    def from_value(cls, value: "HostEvent | Mapping[str, Any]") -> "HostEvent":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise HostEventError("host event must be a mapping")
        payload = value.get("payload")
        if not isinstance(payload, Mapping):
            raise HostEventError("host event payload must be a mapping")
        normalized = normalize_host_payload(payload)
        declared_digest = value.get("payload_digest", payload_digest(normalized))
        try:
            return cls(
                schema_version=int(value.get("schema_version", HOST_EVENT_SCHEMA_VERSION)),
                event_id=str(value.get("event_id", "")),
                kind=str(value.get("kind", "")),
                run_id=str(value.get("run_id", "")),
                round_id=str(value.get("round_id", value.get("run_id", ""))),
                decision_slot_id=_optional_text(value.get("decision_slot_id")),
                action_id=_optional_text(value.get("action_id")),
                causation_id=_optional_text(value.get("causation_id")),
                attempt_id=str(value.get("attempt_id", "")),
                expected_revision=int(value.get("expected_revision", -1)),
                sequence=int(value.get("sequence", 0)),
                actor=str(value.get("actor", "")),
                created_at=str(value.get("created_at", "")),
                payload=normalized,
                payload_digest=str(declared_digest),
            )
        except HostEventError:
            raise
        except (TypeError, ValueError) as error:
            raise HostEventError("host event envelope contains invalid scalar fields") from error

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "kind": self.kind,
            "run_id": self.run_id,
            "round_id": self.round_id,
            "decision_slot_id": self.decision_slot_id,
            "action_id": self.action_id,
            "causation_id": self.causation_id,
            "attempt_id": self.attempt_id,
            "expected_revision": self.expected_revision,
            "sequence": self.sequence,
            "actor": self.actor,
            "created_at": self.created_at,
            "payload": dict(self.payload),
            "payload_digest": self.payload_digest,
        }
        return {key: value for key, value in result.items() if value is not None}

    @property
    def semantic_digest(self) -> str:
        semantic = self.to_dict()
        semantic.pop("actor", None)
        return hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()


def payload_digest(payload: Mapping[str, Any]) -> str:
    """Compute the canonical payload digest used by every host."""

    return hashlib.sha256(canonical_json_bytes(normalize_host_payload(payload))).hexdigest()


def normalize_host_path(value: str) -> str:
    """Normalize a workspace-relative path and reject traversal."""

    if not isinstance(value, str) or not value.strip():
        raise HostEventError("host path must be a non-empty string")
    text = value.replace("\\", "/")
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise HostEventError("host path must be workspace-relative")
    path = PurePosixPath(text)
    parts: list[str] = []
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise HostEventError("host path cannot escape the workspace")
        parts.append(part)
    if not parts:
        raise HostEventError("host path resolves to the workspace root")
    return "/".join(parts)


def normalize_host_payload(value: Any) -> Any:
    """Canonicalize path-bearing payload fields without changing semantics."""

    if isinstance(value, Mapping):
        return {
            str(key): _normalize_payload_field(str(key), normalize_host_payload(child)) for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [normalize_host_payload(child) for child in value]
    return value


def _normalize_payload_field(key: str, value: Any) -> Any:
    if key.endswith("_path") and isinstance(value, str):
        return normalize_host_path(value)
    if key.endswith("_paths") and isinstance(value, list):
        return [normalize_host_path(item) for item in value]
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "HOST_EVENT_KINDS",
    "HOST_EVENT_SCHEMA_VERSION",
    "HostEvent",
    "HostEventDigestError",
    "HostEventError",
    "HostEventSequenceError",
    "normalize_host_path",
    "normalize_host_payload",
    "payload_digest",
]
