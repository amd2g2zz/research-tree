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
HOSTS = ("codex", "claude-code")
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
    normalized_payload = _normalize(payload)
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
