from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pytest

from research_tree.coordinator import (
    HOST_EVENT_KIND,
    HOST_EVENT_PROJECTION_KIND,
    CoordinatorConflictError,
    CoordinatorEventConflictError,
    ResearchRunCoordinator,
)
from research_tree.host_events import (
    HostEvent,
    HostEventDigestError,
    HostEventError,
    HostEventSequenceError,
    payload_digest,
)
from research_tree.run_ledger import RunLedger
from research_tree.domain import ArtifactRef
from strategy_support import confirm_strategy

ROOT = Path(__file__).resolve().parents[1]


def _coordinator(tmp_path):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-host")
    handoff = ledger.append_artifact(
        "run-host",
        "handoff-1",
        "alignment-handoff",
        {"confirmed": True},
        expected_revision=ledger.get_revision("run-host"),
    )
    target = ledger.append_artifact(
        "run-host",
        "target-1",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1", "priority": "P0"}]},
        parent_refs=(ArtifactRef("run-host", handoff.id, handoff.revision),),
        expected_revision=ledger.get_revision("run-host"),
    )
    coordinator = ResearchRunCoordinator(ledger)
    coordinator.initialize(
        run_id="run-host",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-host"),
    )
    confirm_strategy(ledger, coordinator, "run-host")
    lease = coordinator.dispatch(
        run_id="run-host",
        work_item={"objective": "observe", "success_oracle": "coordinator verifies"},
        worker_id="host-worker",
        expected_revision=ledger.get_revision("run-host"),
        attempt_id="attempt-host",
    )
    return ledger, coordinator, lease


def _event(ledger: RunLedger, *, event_id: str = "event-host", sequence: int = 1, expected_revision: int | None = None):
    payload = {"evidence_refs": ["capture-1"], "observation_path": "reports\\capture.json"}
    return HostEvent.from_value(
        {
            "event_id": event_id,
            "kind": "submission",
            "run_id": "run-host",
            "attempt_id": "attempt-host",
            "expected_revision": ledger.get_revision("run-host") if expected_revision is None else expected_revision,
            "sequence": sequence,
            "actor": "codex",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
    )


def test_envelope_digest_version_and_path_normalization() -> None:
    event = HostEvent.from_value(
        {
            "event_id": "event-one",
            "kind": "observation",
            "run_id": "run-one",
            "attempt_id": "attempt-one",
            "expected_revision": 0,
            "sequence": 1,
            "actor": "claude",
            "created_at": "2026-08-11T00:00:00+00:00",
            "payload": {"artifact_path": r"reports\result.json"},
        }
    )
    assert event.payload["artifact_path"] == "reports/result.json"
    assert event.semantic_digest

    with pytest.raises(HostEventDigestError, match="does not match"):
        HostEvent.from_value({**event.to_dict(), "payload_digest": "0" * 64})
    with pytest.raises(HostEventError, match="schema_version"):
        HostEvent.from_value({**event.to_dict(), "schema_version": 2})


def test_native_authoring_helper_matches_runtime_envelope() -> None:
    spec = importlib.util.spec_from_file_location(
        "host_event_protocol_authoring", ROOT / "scripts" / "host_event_protocol.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    payload = {"evidence_refs": ["capture-1"], "artifact_path": r"reports\capture.json"}
    emitted = module.build_host_event(
        event_id="event-parity",
        kind="submission",
        run_id="run-parity",
        attempt_id="attempt-parity",
        expected_revision=3,
        sequence=1,
        actor="codex",
        payload=payload,
        created_at="2026-08-11T00:00:00+00:00",
    )
    parsed = HostEvent.from_value(emitted)
    assert parsed.to_dict() == emitted
    assert parsed.payload["artifact_path"] == "reports/capture.json"


def test_ingestion_is_atomic_replayable_and_non_authoritative(tmp_path) -> None:
    ledger, coordinator, _ = _coordinator(tmp_path)
    event = _event(ledger)
    accepted = coordinator.ingest_host_event(event)
    replay = coordinator.ingest_host_event({**event.to_dict(), "expected_revision": 0})

    assert accepted == replay
    artifacts = ledger.load_run("run-host").artifacts
    assert sum(item.kind == HOST_EVENT_KIND for item in artifacts) == 1
    assert sum(item.kind == HOST_EVENT_PROJECTION_KIND for item in artifacts) == 1
    assert coordinator.state("run-host").payload["state"] == "autonomous_research"
    assert all(item.payload.get("authoritative") is False for item in artifacts if item.kind == HOST_EVENT_KIND)

    with pytest.raises(CoordinatorEventConflictError, match="event_id_conflict"):
        coordinator.ingest_host_event(
            HostEvent.from_value(
                {
                    **event.to_dict(),
                    "payload": {"evidence_refs": ["capture-other"]},
                    "payload_digest": payload_digest({"evidence_refs": ["capture-other"]}),
                }
            )
        )
    with pytest.raises(CoordinatorEventConflictError, match="event_id_conflict"):
        coordinator.ingest_host_event(
            HostEvent.from_value({**event.to_dict(), "actor": "hermes", "expected_revision": 0})
        )


def test_sequence_gap_stale_revision_and_unknown_attempt_do_not_mutate(tmp_path) -> None:
    ledger, coordinator, _ = _coordinator(tmp_path)
    with pytest.raises(HostEventSequenceError, match="sequence"):
        coordinator.ingest_host_event(_event(ledger, sequence=2))
    assert not any(item.kind == HOST_EVENT_KIND for item in ledger.load_run("run-host").artifacts)

    stale = _event(ledger, event_id="event-stale", expected_revision=0)
    with pytest.raises(CoordinatorConflictError, match="stale_revision"):
        coordinator.ingest_host_event(stale)

    orphan = HostEvent.from_value(
        {**_event(ledger, event_id="event-orphan").to_dict(), "attempt_id": "attempt-missing"}
    )
    with pytest.raises(CoordinatorConflictError, match="unknown_attempt"):
        coordinator.ingest_host_event(orphan)


def test_recovery_event_pair_is_atomic_and_replayable(tmp_path, monkeypatch) -> None:
    ledger, coordinator, _ = _coordinator(tmp_path)
    revision = ledger.get_revision("run-host")

    def event(event_id: str, kind: str, sequence: int, payload: dict) -> HostEvent:
        return HostEvent.from_value(
            {
                "event_id": event_id,
                "kind": kind,
                "run_id": "run-host",
                "attempt_id": "attempt-host",
                "expected_revision": revision,
                "sequence": sequence,
                "actor": "hermes",
                "created_at": "2026-08-11T00:00:00+00:00",
                "payload": payload,
            }
        )

    events = (
        event("unknown-1", "unknown_outcome", 1, {"reason": "interrupted_child"}),
        event("retry-1", "retry", 2, {"retry_of": "attempt-host", "category": "transient"}),
    )
    accepted = coordinator.ingest_host_events(events)
    replay = coordinator.ingest_host_events(tuple({**item.to_dict(), "expected_revision": 0} for item in events))
    assert accepted == replay
    artifacts = ledger.load_run("run-host").artifacts
    assert sum(item.kind == HOST_EVENT_KIND for item in artifacts) == 2
    assert sum(item.kind == HOST_EVENT_PROJECTION_KIND for item in artifacts) == 2

    crash_ledger, crash_coordinator, _ = _coordinator(tmp_path / "crash")
    crash_revision = crash_ledger.get_revision("run-host")
    crash_events = tuple(
        HostEvent.from_value(
            {**item.to_dict(), "event_id": f"crash-{item.event_id}", "expected_revision": crash_revision}
        )
        for item in events
    )

    def fail_before_commit() -> None:
        raise RuntimeError("injected Hermes recovery crash")

    monkeypatch.setattr(RunLedger, "_before_commit", staticmethod(fail_before_commit))
    with pytest.raises(RuntimeError, match="injected Hermes recovery crash"):
        crash_coordinator.ingest_host_events(crash_events)
    assert not any(item.kind == HOST_EVENT_KIND for item in crash_ledger.load_run("run-host").artifacts)
