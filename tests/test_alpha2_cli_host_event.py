from __future__ import annotations

import json
from pathlib import Path

from research_tree.cli import main
from research_tree.contracts import HostEvent
from research_tree.coordinator import ResearchRunCoordinator


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
