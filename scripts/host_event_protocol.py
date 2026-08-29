"""Dependency-free HostEvent envelope builder shared by native packages."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Mapping

SCHEMA_VERSION = 1
EVENT_KINDS = frozenset(
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
REQUIRED_PAYLOAD_FIELDS = {
    "provider_failure": ("category", "provider", "model"),
    "workflow_started": ("workflow_id", "capability_digest", "strategy_revision", "action_refs", "phase_refs"),
    "workflow_resumed": ("workflow_id", "capability_digest", "strategy_revision", "checkpoint_refs"),
    "workflow_phase_completed": ("workflow_id", "phase_id", "child_attempt_refs", "produced_artifact_refs"),
    "checkpoint_persisted": ("checkpoint_ref", "checkpoint_digest"),
    "reconciliation_detected": ("workflow_id", "classifications", "next_action"),
}


def normalize_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("host path must be non-empty")
    text = value.replace("\\", "/")
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise ValueError("host path must be workspace-relative")
    parts: list[str] = []
    for part in PurePosixPath(text).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("host path cannot escape workspace")
        parts.append(part)
    if not parts:
        raise ValueError("host path resolves to workspace root")
    return "/".join(parts)


def normalize_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_field(str(key), normalize_payload(child)) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_payload(child) for child in value]
    return value


def _normalize_field(key: str, value: Any) -> Any:
    if key.endswith("_path") and isinstance(value, str):
        return normalize_path(value)
    if key.endswith("_paths") and isinstance(value, list):
        return [normalize_path(item) for item in value]
    return value


def payload_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(normalize_payload(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_host_event(
    *,
    event_id: str,
    kind: str,
    run_id: str,
    attempt_id: str,
    expected_revision: int,
    sequence: int,
    actor: str,
    payload: Mapping[str, Any],
    decision_slot_id: str | None = None,
    action_id: str | None = None,
    causation_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if kind not in EVENT_KINDS:
        raise ValueError(f"unsupported host event kind: {kind}")
    normalized = normalize_payload(payload)
    missing = [field for field in REQUIRED_PAYLOAD_FIELDS.get(kind, ()) if field not in normalized]
    if missing:
        raise ValueError(f"{kind} payload missing: {', '.join(missing)}")
    if kind == "provider_failure":
        if not ({"opaque_code", "error_code"} & set(normalized)):
            raise ValueError("provider_failure payload missing: opaque_code or error_code")
        if not ({"safe_log_ref", "gateway_log_path"} & set(normalized)):
            raise ValueError("provider_failure payload missing: safe_log_ref or gateway_log_path")
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "kind": kind,
        "run_id": run_id,
        "round_id": run_id,
        "attempt_id": attempt_id,
        "expected_revision": expected_revision,
        "sequence": sequence,
        "actor": actor,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "payload": normalized,
        "payload_digest": payload_digest(normalized),
    }
    if decision_slot_id is not None:
        envelope["decision_slot_id"] = decision_slot_id
    if action_id is not None:
        envelope["action_id"] = action_id
    if causation_id is not None:
        envelope["causation_id"] = causation_id
    return envelope


__all__ = [
    "EVENT_KINDS",
    "SCHEMA_VERSION",
    "build_host_event",
    "normalize_path",
    "normalize_payload",
    "payload_digest",
]
