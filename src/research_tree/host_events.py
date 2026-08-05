"""Host-specific payload translation into the common HostEvent protocol."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import HostEvent
from .contracts import canonical_json_bytes
import hashlib
import re


def reconcile_host_events(*, canonical_attempts: Mapping[str, Mapping[str, Any]], host_events: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare host-visible outcomes with canonical attempts without trusting host completion."""
    by_attempt: dict[str, list[Mapping[str, Any]]] = {}
    for event in host_events:
        attempt_id = event.get("attempt_id")
        if attempt_id:
            by_attempt.setdefault(str(attempt_id), []).append(event)
    discrepancies: list[dict[str, Any]] = []
    for attempt_id, events in sorted(by_attempt.items()):
        if attempt_id not in canonical_attempts:
            discrepancies.append({"kind": "missing_canonical_attempt", "attempt_id": attempt_id, "disposition": "unknown"})
            continue
        if len(events) > 1 and len({str(event.get("event_id")) for event in events}) != len(events):
            discrepancies.append({"kind": "duplicate_host_event", "attempt_id": attempt_id, "disposition": "reconcile"})
        canonical_status = str(canonical_attempts[attempt_id].get("status", "unknown"))
        host_statuses: set[str] = set()
        for event in events:
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                continue
            status = payload.get("status")
            if status is None:
                status = payload.get("submission_status")
            if status is None:
                terminal = payload.get("terminal_status")
                if terminal is not None:
                    status = "submitted" if str(terminal).casefold() in {"completed", "verified", "success", "submitted"} else "rejected"
            if status is not None:
                host_statuses.add(str(status))
        if host_statuses and canonical_status not in host_statuses:
            discrepancies.append({"kind": "divergent_outcome", "attempt_id": attempt_id, "canonical_status": canonical_status, "host_statuses": sorted(host_statuses), "disposition": "canonical_remains_authoritative"})
    for attempt_id in sorted(set(canonical_attempts) - set(by_attempt)):
        if str(canonical_attempts[attempt_id].get("status", "")) in {"leased", "running", "unknown"}:
            discrepancies.append({"kind": "missing_host_event", "attempt_id": attempt_id, "disposition": "recover"})
    return {"schema_version": 1, "discrepancies": discrepancies, "status": "reconcile_required" if discrepancies else "no_divergence_detected"}


def canonical_event_digest(events: list[Mapping[str, Any]]) -> str:
    """Hash semantic event content while excluding host-specific ids/timestamps."""
    normalized = []
    for raw in events:
        event = raw if isinstance(raw, HostEvent) else HostEvent.from_dict(raw)
        normalized.append({"event_type": event.event_type, "run_id": event.run_id, "round_id": event.round_id, "slot_id": event.slot_id, "action_id": event.action_id, "attempt_id": event.attempt_id, "causation_id": event.causation_id, "correlation_id": event.correlation_id, "sequence": event.sequence, "expected_revision": event.expected_revision, "payload": dict(event.payload)})
    normalized.sort(key=lambda item: (item["sequence"], item["event_type"], item["attempt_id"] or ""))
    return hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()


def sanitize_provider_failure(*, provider: str, model: str, category: str, opaque_code: str, attempt_id: str, gateway_log_ref: str | None = None) -> dict[str, Any]:
    """Persist only bounded provider metadata; raw gateway details never enter the event."""
    fields = (provider, model, category, opaque_code, attempt_id)
    if any(not isinstance(value, str) or not value.strip() for value in fields):
        raise ValueError("provider failure metadata must be nonempty")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,96}", opaque_code):
        raise ValueError("opaque_code must be bounded and diagnostic-free")
    return {"provider": provider, "model": model, "category": category, "opaque_code": opaque_code, "attempt_id": attempt_id, "gateway_log_ref": gateway_log_ref}


def emit_native_event(
    *, host: str, event_id: str, event_type: str, run_id: str, round_id: str,
    expected_revision: int, payload: Mapping[str, Any], attempt_id: str | None = None,
    slot_id: str | None = None, action_id: str | None = None,
) -> dict[str, Any]:
    """Normalize Codex/Claude/Hermes adapter output without owning state."""

    return HostEvent.create(
        event_id=event_id, event_type=event_type, run_id=run_id, round_id=round_id,
        host=host, expected_revision=expected_revision, payload=payload,
        attempt_id=attempt_id, slot_id=slot_id, action_id=action_id,
    ).to_dict()


def event_from_adapter_payload(
    *, host: str, run_id: str, round_id: str, expected_revision: int,
    adapter_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Translate a bounded adapter event; unknown event names are rejected."""

    data = dict(adapter_payload)
    return emit_native_event(
        host=host,
        event_id=str(data.pop("event_id")),
        event_type=str(data.pop("event_type")),
        run_id=run_id,
        round_id=round_id,
        expected_revision=expected_revision,
        payload=data.pop("payload", data),
        attempt_id=data.pop("attempt_id", None),
        slot_id=data.pop("slot_id", None),
        action_id=data.pop("action_id", None),
    )
