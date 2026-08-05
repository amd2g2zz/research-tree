"""Deterministic projections and causal explanations over immutable events."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Iterable, Mapping

from .contracts import canonical_json_bytes


class ReplayError(ValueError):
    pass


def ordered_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = [dict(event) for event in events]
    seen: set[tuple[str, int]] = set()
    for event in result:
        event_id = str(event.get("event_id", ""))
        sequence = event.get("sequence")
        if not event_id or not isinstance(sequence, int) or sequence < 1:
            raise ReplayError("events require event_id and positive sequence")
        key = (event_id, sequence)
        if key in seen:
            raise ReplayError(f"duplicate event: {event_id}/{sequence}")
        seen.add(key)
    result.sort(key=lambda event: (int(event["sequence"]), str(event.get("causation_id") or ""), str(event["event_id"])))
    sequences = [int(event["sequence"]) for event in result]
    if sequences != list(range(1, len(sequences) + 1)):
        raise ReplayError("event sequence has a gap or does not start at one")
    return result


def replay_events(initial_state: Mapping[str, Any], events: Iterable[Mapping[str, Any]], reducer: Callable[[dict[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None) -> dict[str, Any]:
    state = dict(initial_state)
    for event in ordered_events(events):
        if reducer is not None:
            state = dict(reducer(state, event))
            continue
        payload = event.get("payload", {})
        if isinstance(payload, Mapping):
            state.update({"last_event_id": event["event_id"], "last_event_type": event.get("event_type"), **dict(payload)})
        else:
            state.update({"last_event_id": event["event_id"], "last_event_type": event.get("event_type")})
    return state


def semantic_state_digest(state: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(state)).hexdigest()


def explain_run(state: Mapping[str, Any], events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = ordered_events(events)
    return {"schema_version": 1, "run_id": state.get("run_id"), "state": dict(state), "event_count": len(ordered), "events": ordered, "state_digest": semantic_state_digest(state)}


def why_not_complete(state: Mapping[str, Any], obligations: Iterable[str] = ()) -> dict[str, Any]:
    unmet = [str(item) for item in obligations if str(item)]
    lifecycle = str(state.get("lifecycle_state", "unknown"))
    if lifecycle != "completed" and not unmet:
        unmet.append(f"lifecycle_state={lifecycle}")
    return {"run_id": state.get("run_id"), "complete": lifecycle == "completed" and not unmet, "lifecycle_state": lifecycle, "unmet_obligations": unmet, "next_action": "accept" if lifecycle == "awaiting_acceptance" else ("continue_research" if lifecycle not in {"completed", "superseded", "failed", "authority_blocked"} else "export_audit")}
