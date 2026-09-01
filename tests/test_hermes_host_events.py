from __future__ import annotations

import sys
from pathlib import Path

import pytest

from research_tree.host_events import HostEvent

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from hermes_event_adapter import (  # noqa: E402
    HermesEventError,
    build_hermes_event,
    project_hermes_action,
    recovery_events,
    sanitize_provider_failure,
)
from host_event_protocol import build_host_event  # noqa: E402

BASE = {
    "event_id": "provider-failure-1",
    "run_id": "run-hermes",
    "attempt_id": "attempt-1",
    "expected_revision": 12,
    "sequence": 3,
    "created_at": "2026-08-11T00:00:00+00:00",
}


def provider_failure(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "provider": "openrouter",
        "model": "glm-5.2",
        "retry_category": "transient",
        "error_code": "gateway_timeout",
        "attempt": 2,
        "gateway_log_path": r"logs\gateway\attempt-2.jsonl",
    }
    payload.update(overrides)
    return payload


def test_provider_failure_is_sanitized_and_event_is_deterministic() -> None:
    sanitized = sanitize_provider_failure(provider_failure())
    assert sanitized == {
        "provider": "openrouter",
        "model": "glm-5.2",
        "category": "transient",
        "error_code": "gateway_timeout",
        "attempt": 2,
        "gateway_log_path": "logs/gateway/attempt-2.jsonl",
    }

    first = build_hermes_event(kind="provider_failure", payload=provider_failure(), **BASE)
    second = build_hermes_event(kind="provider_failure", payload=provider_failure(), **BASE)
    assert first == second
    assert first["actor"] == "worker"
    assert first["payload"] == sanitized
    assert len(first["payload_digest"]) == 64


@pytest.mark.parametrize(
    "payload,match",
    [
        (provider_failure(raw_message="secret prompt"), "unsupported provider field"),
        (provider_failure(gateway_log_path="C:/private/gateway.log"), "workspace-relative"),
        (provider_failure(gateway_log_path="../gateway.log"), "escape"),
        (provider_failure(retry_category="complete"), "retry category"),
        (provider_failure(attempt=0), "attempt"),
    ],
)
def test_provider_failure_rejects_raw_or_unsafe_diagnostics(payload: dict[str, object], match: str) -> None:
    with pytest.raises(HermesEventError, match=match):
        sanitize_provider_failure(payload)


def test_hermes_envelope_rejects_invalid_canonical_lineage() -> None:
    with pytest.raises(HermesEventError, match="event id"):
        build_hermes_event(kind="observation", payload={}, **{**BASE, "event_id": "../event"})
    with pytest.raises(HermesEventError, match="expected revision"):
        build_hermes_event(kind="observation", payload={}, **{**BASE, "expected_revision": -1})
    with pytest.raises(HermesEventError, match="sequence"):
        build_hermes_event(kind="observation", payload={}, **{**BASE, "sequence": 0})


def test_action_projection_is_replaceable_and_non_authoritative() -> None:
    projection = project_hermes_action(
        {
            "action_id": "action-1",
            "attempt_id": "attempt-1",
            "objective": "Validate the selected dependency.",
            "acceptance_criteria": ["Resolve the evidence anchor", "Record limitations"],
            "method": "documentation",
        }
    )
    assert projection == {
        "goal": {
            "id": "action-1",
            "objective": "Validate the selected dependency.",
            "acceptance_criteria": ["Resolve the evidence anchor", "Record limitations"],
        },
        "kanban": {
            "id": "attempt-1",
            "action_id": "action-1",
            "method": "documentation",
            "status": "projected",
        },
        "authoritative": False,
    }


def test_recovery_emits_unknown_before_bounded_retry() -> None:
    events = recovery_events(
        run_id="run-hermes",
        action_id="action-1",
        attempt_id="attempt-1",
        expected_revision=12,
        next_sequence=3,
        retry_event_id="retry-1",
        unknown_event_id="unknown-1",
        retry_category="transient",
        method="documentation",
        authorized_methods={"documentation", "repository"},
        created_at="2026-08-11T00:00:00+00:00",
    )
    assert [event["kind"] for event in events] == ["unknown_outcome", "retry"]
    assert [event["sequence"] for event in events] == [3, 4]
    assert events[0]["payload"]["reason"] == "interrupted_child"
    assert events[1]["payload"]["retry_of"] == "attempt-1"

    with pytest.raises(HermesEventError, match="authorized"):
        recovery_events(
            run_id="run-hermes",
            action_id="action-1",
            attempt_id="attempt-1",
            expected_revision=12,
            next_sequence=3,
            retry_event_id="retry-2",
            unknown_event_id="unknown-2",
            retry_category="transient",
            method="browser",
            authorized_methods={"documentation"},
            created_at="2026-08-11T00:00:00+00:00",
        )


def test_equivalent_native_and_hermes_observations_share_payload_digest() -> None:
    envelope = {
        "event_id": "observation-1",
        "kind": "observation",
        "run_id": "run-hermes",
        "attempt_id": "attempt-1",
        "expected_revision": 12,
        "sequence": 3,
        "causation_id": "attempt-1",
        "created_at": "2026-08-11T00:00:00+00:00",
        "payload": {"result": "accepted", "artifact_path": r"findings\one.json"},
    }
    hermes = build_hermes_event(**envelope)
    # Issue #440: both sides are worker-originated observations, so the
    # native twin carries the same closed-vocabulary origin as the Hermes
    # adapter injects.
    native_envelope = {
        **envelope,
        "payload": {**envelope["payload"], "origin": "worker"},
    }
    native = build_host_event(actor="worker", **native_envelope)
    assert hermes["payload_digest"] == native["payload_digest"]
    assert hermes["payload"] == native["payload"]
    assert HostEvent.from_value(hermes).semantic_digest == HostEvent.from_value(native).semantic_digest
