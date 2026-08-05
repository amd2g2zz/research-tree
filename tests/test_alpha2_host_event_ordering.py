from __future__ import annotations

from copy import deepcopy

import pytest


def test_unsupported_protocol_is_quarantined_without_run_mutation(tmp_path) -> None:
    from research_tree.contracts import HostEvent
    from research_tree.coordinator import ResearchRunCoordinator

    coordinator = ResearchRunCoordinator(tmp_path)
    before = coordinator.create("run-protocol-quarantine")
    raw = HostEvent.create(
        event_id="event-protocol-v2",
        event_type="reconciliation_detected",
        run_id="run-protocol-quarantine",
        round_id="round-protocol",
        host="codex",
        expected_revision=before["revision"],
        payload={
            "host_observation": {"state": "seen"},
            "canonical_observation": {"state": "pending"},
            "conflict_class": "version",
            "next_action": "quarantine",
        },
    ).to_dict()
    raw["protocol_version"] = 2

    with pytest.raises(coordinator.error_type) as error:
        coordinator.ingest_host_event(raw)

    assert error.value.code == "unsupported_protocol_version"
    assert coordinator.status("run-protocol-quarantine") == before
    quarantined = coordinator.quarantined_host_events("run-protocol-quarantine")
    assert quarantined[0]["event_id"] == "event-protocol-v2"
    assert quarantined[0]["reason_code"] == "unsupported_protocol_version"
    assert "payload" not in quarantined[0]["safe_event"]


def test_out_of_order_host_sequence_is_quarantined(tmp_path) -> None:
    from research_tree.contracts import HostEvent
    from research_tree.coordinator import ResearchRunCoordinator

    coordinator = ResearchRunCoordinator(tmp_path)
    before = coordinator.create("run-sequence")
    first = HostEvent.create(
        event_id="event-sequence-2",
        event_type="reconciliation_detected",
        run_id="run-sequence",
        round_id="round-sequence",
        host="claude-code",
        sequence=2,
        expected_revision=before["revision"],
        payload={
            "host_observation": {"state": "seen"},
            "canonical_observation": {"state": "pending"},
            "conflict_class": "status",
            "next_action": "reconcile",
        },
    )
    coordinator.ingest_host_event(first)
    accepted = coordinator.status("run-sequence")
    stale = HostEvent.create(
        event_id="event-sequence-1",
        event_type="reconciliation_detected",
        run_id="run-sequence",
        round_id="round-sequence",
        host="claude-code",
        sequence=1,
        expected_revision=accepted["revision"],
        payload={
            "host_observation": {"state": "old"},
            "canonical_observation": {"state": "pending"},
            "conflict_class": "status",
            "next_action": "reconcile",
        },
    )

    with pytest.raises(coordinator.error_type) as error:
        coordinator.ingest_host_event(stale)
    assert error.value.code == "out_of_order_event"
    assert coordinator.status("run-sequence") == accepted
    assert coordinator.quarantined_host_events("run-sequence")[0]["event_id"] == "event-sequence-1"


def test_host_event_rejects_invalid_ordering_and_optional_ids() -> None:
    from research_tree.contracts import ContractError, HostEvent

    base = {
        "event_id": "event-invalid-order",
        "event_type": "reconciliation_detected",
        "run_id": "run-invalid-order",
        "round_id": "round-invalid-order",
        "host": "hermes",
        "expected_revision": 0,
        "payload": {
            "host_observation": {},
            "canonical_observation": {},
            "conflict_class": "status",
            "next_action": "reconcile",
        },
    }
    with pytest.raises(ContractError):
        HostEvent.create(**base, sequence=0)
    invalid = deepcopy(base)
    invalid["attempt_id"] = "Not Valid"
    with pytest.raises(ContractError):
        HostEvent.create(**invalid)


def test_unknown_attempt_is_retained_as_bounded_orphan_evidence(tmp_path) -> None:
    from research_tree.contracts import HostEvent
    from research_tree.coordinator import ResearchRunCoordinator

    coordinator = ResearchRunCoordinator(tmp_path)
    before = coordinator.create("run-orphan")
    event = HostEvent.create(
        event_id="event-orphan",
        event_type="worker_finished",
        run_id="run-orphan",
        round_id="round-orphan",
        host="hermes",
        attempt_id="attempt-missing",
        expected_revision=before["revision"],
        payload={"terminal_status": "completed", "artifact_refs": ["finding-missing"]},
    )
    with pytest.raises(coordinator.error_type) as error:
        coordinator.ingest_host_event(event)
    assert error.value.code == "attempt_not_found"
    assert coordinator.status("run-orphan") == before
    assert coordinator.quarantined_host_events("run-orphan")[0]["reason_code"] == "attempt_not_found"
