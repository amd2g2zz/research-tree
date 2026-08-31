"""Tests for observation origin + HostEvent actor constraints (issue #440, tasks.md 4.1).

Observations entering canonical state must carry a required ``origin`` drawn
from ORIGIN_TYPES; the envelope ``actor`` must be constrained to the same
vocabulary. Both fail closed, naming the field.
"""

from __future__ import annotations

import pytest

from research_tree.host_events import HostEvent, HostEventError
from research_tree.origins import ORIGIN_TYPES


def _base_payload() -> dict[str, object]:
    return {
        "event_id": "evt-1",
        "kind": "observation",
        "run_id": "run-1",
        "round_id": "run-1",
        "attempt_id": "attempt-1",
        "expected_revision": 1,
        "sequence": 1,
        "actor": "agent",
        "created_at": "2026-09-01T00:00:00Z",
        "payload": {"origin": "worker"},
    }


def test_observation_with_valid_origin_accepted() -> None:
    event = HostEvent.from_value(_base_payload())
    assert event.payload["origin"] == "worker"


@pytest.mark.parametrize("origin", sorted(ORIGIN_TYPES))
def test_observation_accepts_every_vocabulary_value(origin: str) -> None:
    payload = _base_payload()
    payload["payload"] = {"origin": origin}
    assert HostEvent.from_value(payload).payload["origin"] == origin


def test_observation_without_origin_rejected() -> None:
    payload = _base_payload()
    payload["payload"] = {}
    with pytest.raises(HostEventError) as excinfo:
        HostEvent.from_value(payload)
    assert "origin" in str(excinfo.value)


def test_observation_with_unknown_origin_rejected() -> None:
    payload = _base_payload()
    payload["payload"] = {"origin": "some-random-string"}
    with pytest.raises(HostEventError) as excinfo:
        HostEvent.from_value(payload)
    assert "origin" in str(excinfo.value)


def test_actor_outside_vocabulary_rejected() -> None:
    payload = _base_payload()
    payload["actor"] = "some-random-string"
    with pytest.raises(HostEventError) as excinfo:
        HostEvent.from_value(payload)
    assert "actor" in str(excinfo.value)


@pytest.mark.parametrize("actor", sorted(ORIGIN_TYPES))
def test_actor_accepts_every_vocabulary_value(actor: str) -> None:
    payload = _base_payload()
    payload["actor"] = actor
    assert HostEvent.from_value(payload).actor == actor
