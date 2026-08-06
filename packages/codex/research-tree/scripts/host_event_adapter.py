#!/usr/bin/env python3
"""Translate one native host observation into a canonical HostEvent wire object.

This adapter is deliberately stateless. It neither creates a run nor tracks tasks,
evidence, readiness, delivery, or completion. The canonical coordinator validates
and ingests the emitted event.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence
import unicodedata


PROTOCOL_VERSION = 1
HOSTS = ("codex", "claude-code", "hermes")
EVENT_TYPES = frozenset(
    {
        "dispatch_requested",
        "attempt_started",
        "finding_submitted",
        "review_completed",
        "provider_failed",
        "attempt_unknown",
        "retry_requested",
        "worker_finished",
        "completion_claimed",
        "acceptance_recorded",
        "reconciliation_detected",
    }
)
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
INPUT_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "run_id",
        "round_id",
        "slot_id",
        "action_id",
        "attempt_id",
        "causation_id",
        "correlation_id",
        "sequence",
        "expected_revision",
        "emitted_at",
        "payload",
    }
)
EVENT_PAYLOAD_FIELDS: dict[str, frozenset[str]] = {
    "dispatch_requested": frozenset(
        {"work_item_id", "permission_profile", "dispatch_digest", "lease_policy"}
    ),
    "attempt_started": frozenset(
        {"worker_id", "lease_expires_at", "tool_capability_digest", "started_at"}
    ),
    "finding_submitted": frozenset(
        {"finding_pack_digest", "evidence_refs", "submission_status", "output_digest"}
    ),
    "review_completed": frozenset(
        {"reviewer_id", "accepted_refs", "field_diagnostics", "review_digest"}
    ),
    "provider_failed": frozenset(
        {"provider", "model", "retry_category", "opaque_code", "gateway_log_ref"}
    ),
    "attempt_unknown": frozenset(
        {"reconciliation_reason", "last_heartbeat", "observed_host_state"}
    ),
    "retry_requested": frozenset(
        {"predecessor_attempt", "method_provider_change", "retry_policy"}
    ),
    "worker_finished": frozenset({"terminal_status", "artifact_refs"}),
    "completion_claimed": frozenset(
        {"claim_kind", "claimed_state", "source_ref", "local_status"}
    ),
    "acceptance_recorded": frozenset(
        {"delivery_acceptance_ref", "displayed_digest"}
    ),
    "reconciliation_detected": frozenset(
        {"host_observation", "canonical_observation", "conflict_class", "next_action"}
    ),
}
PROVIDER_RAW_FIELDS = frozenset(
    {
        "raw_error",
        "raw_details",
        "traceback",
        "stack_trace",
        "response_body",
        "provider_message",
        "exception",
        "secret",
        "token",
    }
)
OPAQUE_CODE_RE = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
SAFE_LOG_REF_RE = re.compile(
    r"^(?:log:[A-Za-z0-9._:-]{1,192}|sha256:[0-9a-f]{64})$"
)


class AdapterError(ValueError):
    """A bounded native-to-wire translation error."""


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(child) for key, child in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise AdapterError("JSON numbers must be finite")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            _normalize(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AdapterError("event input is not canonical JSON") from exc


def _identifier(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise AdapterError(f"{label} is invalid")
    return value


def _utc_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise AdapterError("emitted_at must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdapterError("emitted_at must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise AdapterError("emitted_at must be UTC")
    return value


def _validate_payload(event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize(payload)
    missing = EVENT_PAYLOAD_FIELDS[event_type] - set(normalized)
    if missing:
        raise AdapterError(
            f"{event_type} payload is incomplete; missing={sorted(missing)}"
        )
    if event_type == "provider_failed":
        if PROVIDER_RAW_FIELDS & set(normalized):
            raise AdapterError("provider_failed payload contains raw diagnostics")
        if set(normalized) != EVENT_PAYLOAD_FIELDS[event_type]:
            raise AdapterError("provider_failed payload fields mismatch")
        for field in ("provider", "model", "retry_category"):
            if not isinstance(normalized[field], str) or not normalized[field].strip():
                raise AdapterError(f"provider_failed {field} must be nonempty")
        if not isinstance(normalized["opaque_code"], str) or not OPAQUE_CODE_RE.fullmatch(
            normalized["opaque_code"]
        ):
            raise AdapterError("provider_failed opaque_code is invalid")
        log_ref = normalized["gateway_log_ref"]
        if log_ref is not None and (
            not isinstance(log_ref, str) or not SAFE_LOG_REF_RE.fullmatch(log_ref)
        ):
            raise AdapterError("provider_failed gateway_log_ref is not a safe reference")
    return normalized


def translate(host: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Create a host-bound wire event without persisting business state."""

    if host not in HOSTS:
        raise AdapterError(f"unsupported host: {host}")
    data = dict(value)
    missing = INPUT_FIELDS - set(data)
    extra = set(data) - INPUT_FIELDS
    if missing or extra:
        raise AdapterError(
            f"event input fields mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    event_type = data["event_type"]
    if event_type not in EVENT_TYPES:
        raise AdapterError(f"unsupported event_type: {event_type!r}")
    sequence = data["sequence"]
    expected_revision = data["expected_revision"]
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise AdapterError("sequence must be a positive integer")
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 0
    ):
        raise AdapterError("expected_revision must be a nonnegative integer")
    payload = data["payload"]
    if not isinstance(payload, Mapping):
        raise AdapterError("payload must be an object")
    normalized_payload = _validate_payload(event_type, payload)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "event_id": _identifier(data["event_id"], "event_id"),
        "event_type": event_type,
        "run_id": _identifier(data["run_id"], "run_id"),
        "round_id": _identifier(data["round_id"], "round_id"),
        "slot_id": _identifier(data["slot_id"], "slot_id", optional=True),
        "action_id": _identifier(data["action_id"], "action_id", optional=True),
        "attempt_id": _identifier(data["attempt_id"], "attempt_id", optional=True),
        "host": host,
        "causation_id": _identifier(
            data["causation_id"], "causation_id", optional=True
        ),
        "correlation_id": _identifier(
            data["correlation_id"], "correlation_id", optional=True
        ),
        "sequence": sequence,
        "expected_revision": expected_revision,
        "payload_digest": hashlib.sha256(
            _canonical_json_bytes(normalized_payload)
        ).hexdigest(),
        "emitted_at": _utc_timestamp(data["emitted_at"]),
        "payload": normalized_payload,
    }


def _read_input(path: str) -> dict[str, Any]:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdapterError(f"cannot read event input: {exc}") from exc
    if not isinstance(value, dict):
        raise AdapterError("event input must be a JSON object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=HOSTS, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    emit = commands.add_parser("emit")
    emit.add_argument("--input", required=True, help="JSON path, or - for stdin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        event = translate(arguments.host, _read_input(arguments.input))
    except AdapterError as exc:
        print(
            json.dumps(
                {"code": "invalid_host_event_input", "safe_message": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    sys.stdout.buffer.write(_canonical_json_bytes(event) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
