from __future__ import annotations

import json
from pathlib import Path

from research_tree.cli import main
from research_tree.contracts import HostEvent
from research_tree.coordinator import ResearchRunCoordinator
from research_tree.leases import AttemptLease


def test_run_ingest_routes_host_event_to_canonical_coordinator(
    tmp_path: Path, capsys
) -> None:
    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-cli-event")
    event_path = tmp_path / "host-event.json"
    event_path.write_text(
        json.dumps(
            HostEvent.create(
                event_id="event-cli-1",
                event_type="reconciliation_detected",
                run_id="run-cli-event",
                round_id="round-cli",
                host="claude-code",
                expected_revision=state["revision"],
                payload={
                    "host_observation": {"status": "observed"},
                    "canonical_observation": {"status": "pending"},
                    "conflict_class": "status_divergence",
                    "next_action": "reconcile",
                },
            ).to_dict()
        ),
        encoding="utf-8",
    )

    assert main(
        [
            "run",
            "ingest",
            "--workspace",
            str(tmp_path),
            "--event",
            str(event_path),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["event_id"] == "event-cli-1"
    assert coordinator.status("run-cli-event")["revision"] == 1


def test_run_retry_routes_to_coordinator_and_creates_new_attempt(
    tmp_path: Path, capsys
) -> None:
    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-cli-retry")
    coordinator.issue_lease(
        AttemptLease.create(
            attempt_id="attempt-cli-retry",
            work_item_id="work-cli-retry",
            run_id="run-cli-retry",
            owner="hermes-worker",
            status="retryable",
            dispatch_digest="a" * 64,
            started_at="2026-08-05T00:00:00+00:00",
            lease_expires_at="2026-08-05T01:00:00+00:00",
        ),
        expected_revision=state["revision"],
    )
    state = coordinator.status("run-cli-retry")

    assert main(
        [
            "run",
            "retry",
            "--workspace",
            str(tmp_path),
            "--run-id",
            "run-cli-retry",
            "--attempt-id",
            "attempt-cli-retry",
            "--dispatch-digest",
            "b" * 64,
            "--expected-revision",
            str(state["revision"]),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["retry"]["attempt_id"] == "work-cli-retry-retry-1"
