from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_tree.coordinator import ResearchRunCoordinator
from research_tree.contracts import HostEvent
from research_tree.leases import AttemptLease
from research_tree.sqlite_ledger import SQLiteRunLedger
from tests.alpha2_runtime_helpers import satisfy_p0_closure


def test_material_feedback_preserves_revision_and_quarantines_dependent_state(
    tmp_path: Path,
) -> None:
    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    strategy_digest = "a" * 64
    state = coordinator.create(
        "run-correction-integration",
        task_identity={"subject": "diagnostic-repository", "domain": "runtime"},
    )
    state = coordinator.transition(
        state["run_id"],
        event="alignment_projection_ready",
        actor="coordinator",
        expected_revision=state["revision"],
        payload={"strategy_digest": strategy_digest},
    )
    state = satisfy_p0_closure(ledger, state, suffix="correction")
    for obligation in ("insight_clear", "readiness", "evaluation"):
        state = coordinator.record_obligation(
            state["run_id"],
            obligation,
            evidence_ref=f"evidence:{obligation}",
            expected_revision=state["revision"],
        )
    state = coordinator.issue_lease(
        AttemptLease.create(
            attempt_id="attempt-old-strategy",
            work_item_id="work-old-strategy",
            run_id=state["run_id"],
            owner="worker",
            status="verified",
            dispatch_digest=strategy_digest,
            started_at="2026-08-05T00:00:00+00:00",
            lease_expires_at="2026-08-05T01:00:00+00:00",
        ),
        expected_revision=state["revision"],
    )
    state = coordinator.transition(
        state["run_id"],
        event="handoff_confirmed",
        actor="human",
        expected_revision=state["revision"],
        payload={"displayed_digest": strategy_digest},
    )
    state = coordinator.transition(
        state["run_id"],
        event="batch_checkpoint",
        actor="coordinator",
        expected_revision=state["revision"],
    )
    state = coordinator.transition(
        state["run_id"],
        event="all_slots_closed",
        actor="coordinator",
        expected_revision=state["revision"],
    )
    state = coordinator.transition(
        state["run_id"],
        event="readiness_passed",
        actor="coordinator",
        expected_revision=state["revision"],
    )
    state = coordinator.deliver(
        state["run_id"],
        expected_revision=state["revision"],
        technical_digest="b" * 64,
        human_digest="c" * 64,
    )
    state = coordinator.accept(
        state["run_id"],
        expected_revision=state["revision"],
        displayed_digest=coordinator.delivery_pair_digest(
            state["run_id"], "b" * 64, "c" * 64
        ),
        technical_revision="b" * 64,
        human_revision="c" * 64,
        feedback="The delivered artifacts answer the confirmed research objective.",
    )
    assert all(item["satisfied"] for item in coordinator.obligations(state["run_id"]).values())
    predecessor = dict(state)

    successor = coordinator.record_feedback(
        {
            "feedback_id": "feedback-correct-target",
            "run_id": state["run_id"],
            "actor": "human",
            "kind": "correction",
            "message": "The repository is diagnostic evidence, not the research target.",
            "target_refs": [f"strategy:{strategy_digest}"],
            "materiality": "material",
            "created_at": "2026-08-05T00:30:00+00:00",
            "affected_fields": ["task_identity.subject", "strategy", "handoff"],
            "invalidated_refs": [f"strategy:{strategy_digest}"],
            "successor_refs": ["task-identity:autonomous-agent"],
            "impact_class": "strategy",
            "task_identity_disposition": "rederived",
            "successor_task_identity": {
                "subject": "autonomous-agent",
                "domain": "research",
            },
        },
        expected_revision=state["revision"],
    )

    revisions = coordinator.revisions(state["run_id"])
    assert sorted(revisions) == list(range(successor["revision"] + 1))
    assert revisions[predecessor["revision"]]["state_digest"] == predecessor["state_digest"]
    assert revisions[predecessor["revision"]]["lifecycle_state"] == "completed"
    assert revisions[successor["revision"]]["task_identity"]["subject"] == "autonomous-agent"
    assert all(not item["satisfied"] for item in coordinator.obligations(state["run_id"]).values())
    quarantine = coordinator.attempt_invalidations(state["run_id"])
    assert quarantine["attempt-old-strategy"]["feedback_id"] == "feedback-correct-target"
    assert quarantine["attempt-old-strategy"]["prior_status"] == "verified"
    feedback_event = coordinator.events(state["run_id"])[-1]
    assert feedback_event["payload"]["predecessor_revision"] == predecessor["revision"]
    assert feedback_event["payload"]["successor_revision"] == successor["revision"]
    assert feedback_event["payload"]["invalidated_attempt_ids"] == ["attempt-old-strategy"]
    stale_result = HostEvent.create(
        event_id="event-stale-attempt-finished",
        event_type="worker_finished",
        run_id=state["run_id"],
        round_id="round-correction",
        host="codex",
        expected_revision=successor["revision"],
        attempt_id="attempt-old-strategy",
        payload={"terminal_status": "completed", "artifact_refs": ["finding:old"]},
    )
    with pytest.raises(coordinator.error_type) as invalid_attempt:
        coordinator.ingest_host_event(stale_result)
    assert invalid_attempt.value.code == "attempt_invalidated"
    assert invalid_attempt.value.next_action == "replan_and_create_new_attempt"
    with pytest.raises(coordinator.error_type) as stale:
        coordinator.assert_current(state["run_id"], strategy_digest, action="dispatch")
    assert stale.value.code == "stale_digest"
    expected = json.loads(
        (
            Path(__file__).parents[1]
            / "evaluation"
            / "harness"
            / "fixtures"
            / "correction_invalidation_trace.json"
        ).read_text(encoding="utf-8")
    )["trace"]
    assert {
        "predecessor_lifecycle_state": revisions[predecessor["revision"]][
            "lifecycle_state"
        ],
        "successor_lifecycle_state": successor["lifecycle_state"],
        "successor_task_subject": successor["task_identity"]["subject"],
        "invalidated_attempt_ids": feedback_event["payload"][
            "invalidated_attempt_ids"
        ],
        "invalidated_obligations": feedback_event["payload"][
            "invalidated_obligations"
        ],
        "rejected_followup_code": invalid_attempt.value.code,
    } == expected


def test_rejected_feedback_does_not_create_a_revision(tmp_path: Path) -> None:
    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-rejected-feedback")
    before = coordinator.revisions(state["run_id"])

    with pytest.raises(ValueError):
        coordinator.record_feedback(
            {
                "feedback_id": "feedback-invalid",
                "run_id": state["run_id"],
                "actor": "human",
                "kind": "correction",
                "message": "Change the target.",
                "target_refs": [],
                "materiality": "material",
                "created_at": "not-a-timestamp",
            },
            expected_revision=state["revision"],
        )

    assert coordinator.revisions(state["run_id"]) == before
    assert coordinator.status(state["run_id"]) == state
