"""Host-specific payload translation into the common HostEvent protocol."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import HostEvent


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
