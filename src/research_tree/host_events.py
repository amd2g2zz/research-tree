"""Host-specific payload translation into the common HostEvent protocol."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import HostEvent


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
        host_statuses = {str(event.get("payload", {}).get("status")) for event in events if isinstance(event.get("payload"), Mapping)}
        if host_statuses and canonical_status not in host_statuses:
            discrepancies.append({"kind": "divergent_outcome", "attempt_id": attempt_id, "canonical_status": canonical_status, "host_statuses": sorted(host_statuses), "disposition": "canonical_remains_authoritative"})
    for attempt_id in sorted(set(canonical_attempts) - set(by_attempt)):
        if str(canonical_attempts[attempt_id].get("status", "")) in {"leased", "running", "unknown"}:
            discrepancies.append({"kind": "missing_host_event", "attempt_id": attempt_id, "disposition": "recover"})
    return {"schema_version": 1, "discrepancies": discrepancies, "status": "reconcile_required" if discrepancies else "no_divergence_detected"}


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
