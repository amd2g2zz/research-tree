from __future__ import annotations

import hashlib
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from strategy_support import confirm_strategy

from research_tree.coordinator import (
    HOST_EVENT_KIND,
    HOST_EVENT_PROJECTION_KIND,
    CoordinatorConflictError,
    CoordinatorEventConflictError,
    ResearchRunCoordinator,
)
from research_tree.domain import ArtifactRef, canonical_json_bytes
from research_tree.host_events import (
    HostEvent,
    HostEventDigestError,
    HostEventError,
    HostEventSequenceError,
    payload_digest,
)
from research_tree.run_ledger import RunLedger

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
                "causation_id": "unknown-1" if sequence > 1 else None,
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
            {
                **item.to_dict(),
                "event_id": f"crash-{item.event_id}",
                "causation_id": (f"crash-{item.causation_id}" if item.causation_id is not None else None),
                "expected_revision": crash_revision,
            }
        )
        for item in events
    )

    def fail_before_commit() -> None:
        raise RuntimeError("injected Hermes recovery crash")

    monkeypatch.setattr(RunLedger, "_before_commit", staticmethod(fail_before_commit))
    with pytest.raises(RuntimeError, match="injected Hermes recovery crash"):
        crash_coordinator.ingest_host_events(crash_events)
    assert not any(item.kind == HOST_EVENT_KIND for item in crash_ledger.load_run("run-host").artifacts)


def _append_attempt_artifact(ledger: RunLedger, artifact_id: str, kind: str, payload: dict, parents=()):
    return ledger.append_artifact(
        "run-host",
        artifact_id,
        kind,
        payload,
        parent_refs=parents,
        expected_revision=ledger.get_revision("run-host"),
    )


def test_generic_ingestion_cannot_append_or_bypass_projection(tmp_path) -> None:
    ledger, coordinator, _ = _coordinator(tmp_path)
    before = (ledger.get_revision("run-host"), len(ledger.load_run("run-host").artifacts))
    with pytest.raises(CoordinatorConflictError, match="host_event_envelope_required"):
        coordinator.ingest_event(
            run_id="run-host",
            event_id="forged-event",
            attempt_id="attempt-host",
            payload={"outcome": "success"},
            expected_revision=before[0],
        )
    assert (ledger.get_revision("run-host"), len(ledger.load_run("run-host").artifacts)) == before


@pytest.mark.parametrize(
    "lease_patch, error",
    [
        ({"status": "expired"}, "lease_inactive"),
        ({"expires_at": "2020-01-01T00:00:00+00:00"}, "lease_expired"),
    ],
)
def test_inactive_or_expired_lease_is_rejected_without_mutation(tmp_path, lease_patch, error) -> None:
    ledger, coordinator, lease = _coordinator(tmp_path)
    payload = {**lease.payload, **lease_patch}
    replacement = ledger.append_artifact(
        "run-host",
        lease.id,
        lease.kind,
        payload,
        parent_refs=(ArtifactRef("run-host", lease.id, lease.revision),),
        expected_revision=ledger.get_revision("run-host"),
    )
    event = _event(ledger, expected_revision=ledger.get_revision("run-host"))
    before = len(ledger.load_run("run-host").artifacts)
    with pytest.raises(CoordinatorConflictError, match=error):
        coordinator.ingest_host_event(event)
    assert len(ledger.load_run("run-host").artifacts) == before
    assert ledger.is_latest_artifact(ArtifactRef("run-host", replacement.id, replacement.revision))


def test_worker_finished_requires_committed_capture_receipt_checkpoint_and_finding(tmp_path) -> None:
    ledger, coordinator, _ = _coordinator(tmp_path)
    incomplete = HostEvent.from_value(
        {
            **_event(ledger).to_dict(),
            "event_id": "worker-incomplete",
            "kind": "worker_finished",
            "payload": {"outcome": "success"},
            "payload_digest": payload_digest({"outcome": "success"}),
        }
    )
    before = ledger.get_revision("run-host")
    with pytest.raises(CoordinatorConflictError, match="capture_incomplete"):
        coordinator.ingest_host_event(incomplete)
    assert ledger.get_revision("run-host") == before

    capture = _append_attempt_artifact(
        ledger,
        "capture-1",
        "source-capture",
        {"attempt_id": "attempt-host", "status": "committed", "content_digest": "a" * 64},
    )
    receipt = _append_attempt_artifact(
        ledger,
        "receipt-1",
        "acquisition-receipt",
        {"attempt_id": "attempt-host", "capture_id": capture.id, "status": "succeeded"},
        (ArtifactRef("run-host", capture.id, capture.revision),),
    )
    checkpoint = _append_attempt_artifact(
        ledger,
        "checkpoint-1",
        "analysis-checkpoint",
        {"attempt_id": "attempt-host", "status": "committed"},
        (ArtifactRef("run-host", capture.id, capture.revision),),
    )
    finding = _append_attempt_artifact(
        ledger,
        "finding-1",
        "finding-pack",
        {"attempt_id": "attempt-host", "status": "committed"},
    )
    produced = _append_attempt_artifact(
        ledger,
        "output-1",
        "analysis-output",
        {"attempt_id": "attempt-host", "status": "committed"},
    )
    payload = {
        "outcome": "success",
        "capture_refs": [ArtifactRef("run-host", capture.id, capture.revision).to_dict()],
        "receipt_refs": [ArtifactRef("run-host", receipt.id, receipt.revision).to_dict()],
        "checkpoint_ref": ArtifactRef("run-host", checkpoint.id, checkpoint.revision).to_dict(),
        "finding_refs": [ArtifactRef("run-host", finding.id, finding.revision).to_dict()],
        "produced_artifact_refs": [ArtifactRef("run-host", produced.id, produced.revision).to_dict()],
    }
    accepted = HostEvent.from_value(
        {
            **_event(ledger).to_dict(),
            "event_id": "worker-finished",
            "kind": "worker_finished",
            "expected_revision": ledger.get_revision("run-host"),
            "payload": payload,
            "payload_digest": payload_digest(payload),
        }
    )
    event = coordinator.ingest_host_event(accepted)
    restarted = ResearchRunCoordinator(RunLedger(tmp_path))
    replay = restarted.ingest_host_event({**accepted.to_dict(), "expected_revision": 0})
    assert replay == event
    assert any(item.id == "checkpoint-1" for item in RunLedger(tmp_path).list_artifacts("run-host"))


def test_checkpoint_persisted_requires_exact_checkpoint_digest(tmp_path) -> None:
    ledger, coordinator, _ = _coordinator(tmp_path)
    checkpoint = _append_attempt_artifact(
        ledger,
        "checkpoint-1",
        "analysis-checkpoint",
        {"attempt_id": "attempt-host", "status": "committed"},
    )
    payload = {
        "checkpoint_ref": ArtifactRef("run-host", checkpoint.id, checkpoint.revision).to_dict(),
        "checkpoint_digest": hashlib.sha256(canonical_json_bytes(dict(checkpoint.payload))).hexdigest(),
    }
    event = HostEvent.from_value(
        {
            **_event(ledger).to_dict(),
            "event_id": "checkpoint-event",
            "kind": "checkpoint_persisted",
            "expected_revision": ledger.get_revision("run-host"),
            "payload": payload,
            "payload_digest": payload_digest(payload),
        }
    )
    assert coordinator.ingest_host_event(event).payload["kind"] == "checkpoint_persisted"
    forged_payload = {**payload, "checkpoint_digest": "0" * 64}
    forged = HostEvent.from_value(
        {
            **event.to_dict(),
            "event_id": "checkpoint-forged",
            "expected_revision": ledger.get_revision("run-host"),
            "sequence": 2,
            "causation_id": event.event_id,
            "payload": forged_payload,
            "payload_digest": payload_digest(forged_payload),
        }
    )
    before = ledger.get_revision("run-host")
    with pytest.raises(CoordinatorConflictError, match="checkpoint_digest_mismatch"):
        coordinator.ingest_host_event(forged)
    assert ledger.get_revision("run-host") == before
