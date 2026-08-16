from __future__ import annotations

import json

import pytest


def _event(number: int):
    from research_tree.interaction_state import InteractionEvent

    return InteractionEvent.user_message(
        event_id=f"turn-{number:02d}",
        text=f"Work item {number}",
        outcome=f"work item {number}",
        consequence="low",
        reversible=True,
        authority=("repository_write",) if number == 1 else (),
    )


def test_fifteen_turn_window_evicts_transients_but_preserves_durable_constraints(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.interaction_state import InteractionEvent

    controller = DurableInteractionController.initialize(tmp_path, project_id="topic", run_id="run", window_size=10)
    revision = 0
    for number in range(1, 16):
        revision = controller.submit(_event(number), expected_revision=revision).revision
    revision = controller.submit(
        InteractionEvent.stance(
            event_id="constraint", proposition_id="no-network", stance="correct", evidence_anchor="user-turn"
        ),
        expected_revision=revision,
    ).revision
    loaded = controller.load()
    assert len(loaded.active_window) == 10
    assert "turn-01" not in loaded.active_window
    assert loaded.durable["authority"] == ["repository_write"]
    assert loaded.durable["corrections"]["no-network"]["value"] == "correct"
    assert len(list(controller.paths.episodes.glob("*.yaml"))) == 16


def test_recall_omits_superseded_and_recovers_old_correction(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.interaction_state import InteractionEvent

    controller = DurableInteractionController.initialize(tmp_path, project_id="topic", run_id="run", window_size=1)
    revision = controller.submit(_event(1), expected_revision=0).revision
    revision = controller.submit(
        InteractionEvent.agent_assumption(
            event_id="old-plan", assumption_id="plan", statement="Use old deployment plan.", pending_actions=("deploy",)
        ),
        expected_revision=revision,
    ).revision
    revision = controller.submit(
        InteractionEvent.correction(event_id="correct-plan", target_id="plan", replacement="Use safe deployment plan."),
        expected_revision=revision,
    ).revision
    controller.submit(_event(2), expected_revision=revision)
    recalled = controller.recall("safe deployment plan", limit=10)
    assert any(item["event_id"] == "correct-plan" for item in recalled)
    assert not any(item["event_id"] == "old-plan" for item in recalled)


def test_stale_write_is_rejected_and_checkpoint_recovery_marks_started_action_unknown(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController, StaleInteractionRevision

    controller = DurableInteractionController.initialize(tmp_path, project_id="topic", run_id="run")
    revision = controller.submit(_event(1), expected_revision=0).revision
    with pytest.raises(StaleInteractionRevision):
        controller.submit(_event(2), expected_revision=0)
    controller.record_action_started("publish", expected_revision=revision)
    checkpoint = controller.checkpoint(expected_revision=revision + 1)
    recovered = controller.recover(checkpoint)
    assert recovered.state.agent.next_move == "repair"
    assert recovered.pending_actions["publish"] == "unknown"


def test_unadmitted_evidence_cannot_change_beliefs_and_contestation_retracts(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController

    controller = DurableInteractionController.initialize(tmp_path, project_id="topic", run_id="run")
    assert (
        controller.propose_evidence("claim-a", "candidate", admitted=False, expected_revision=0).factual_beliefs == {}
    )
    revision = controller.load().revision
    assert controller.propose_evidence(
        "claim-a", "confirmed", admitted=True, expected_revision=revision
    ).factual_beliefs == {"claim-a": "confirmed"}
    revision = controller.load().revision
    assert controller.contest_evidence("claim-a", expected_revision=revision).factual_beliefs == {}


def test_project_hook_event_checkpoints_and_records_degraded_integrity(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController

    controller = DurableInteractionController.initialize(tmp_path, project_id="topic", run_id="run")
    controller.consume_lifecycle_event("PreCompact")
    state = json.loads(controller.paths.state.read_text(encoding="utf-8"))
    assert state["recovery_cursor"] is not None
    assert state["state_integrity"] == "healthy"
    controller.consume_lifecycle_event("unknown-telemetry")
    assert controller.load().state_integrity == "degraded"


def test_contested_evidence_cancels_dependent_pending_effects_atomically(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.interaction_state import InteractionEvent

    controller = DurableInteractionController.initialize(tmp_path, project_id="topic", run_id="run")
    controller.submit(
        InteractionEvent.agent_assumption(
            event_id="assume-claim", assumption_id="claim-a", statement="Use claim A.", pending_actions=("publish",)
        ),
        expected_revision=0,
    )
    controller.record_action_started("publish", expected_revision=1)
    controller.propose_evidence("claim-a", "Claim A is true.", admitted=True, expected_revision=2)

    contested = controller.contest_evidence("claim-a", expected_revision=3)

    assert contested.factual_beliefs == {}
    assert contested.pending_actions == {}
    assert contested.state.agent.pending_actions == ()
    assert contested.state.agent.next_move == "repair"


def test_lifecycle_observation_consumes_project_state_without_blocking_host(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.lifecycle_hook import observe

    controller = DurableInteractionController.initialize(tmp_path, project_id="topic", run_id="run")
    result = observe(
        {"cwd": str(tmp_path), "project_id": "topic", "run_id": "run", "hook_event_name": "PreCompact"},
        host="codex",
        event="PreCompact",
        project_root=tmp_path,
        process_cwd=tmp_path,
    )
    assert result["status"] == "recorded"
    assert controller.load().recovery_cursor is not None


def test_lifecycle_precompact_and_session_start_preserve_host_response(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.lifecycle_hook import host_response, observe

    controller = DurableInteractionController.initialize(tmp_path, project_id="topic", run_id="run")
    for event in ("PreCompact", "SessionStart"):
        assert (
            observe(
                {"cwd": str(tmp_path), "project_id": "topic", "run_id": "run", "hook_event_name": event},
                host="codex",
                event=event,
                project_root=tmp_path,
                process_cwd=tmp_path,
            ).get("status")
            == "recorded"
        )
        assert host_response("codex") == {"continue": True}
    assert controller.load().recovery_cursor is not None


def test_durable_projection_recovers_from_interrupted_double_write(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController

    controller = DurableInteractionController.initialize(tmp_path, project_id="topic", run_id="run")
    controller.submit(_event(1), expected_revision=0)
    controller.paths.durable.write_text('{"interrupted": true}\n', encoding="utf-8")

    loaded = controller.load()
    assert loaded.durable["authority"] == ["repository_write"]
    assert json.loads(controller.paths.durable.read_text(encoding="utf-8"))["authority"] == ["repository_write"]


def test_correction_reconciles_started_and_unrelated_pending_actions(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.interaction_state import InteractionEvent

    controller = DurableInteractionController.initialize(tmp_path, project_id="project-245", run_id="run-245")
    controller.submit(
        InteractionEvent.agent_assumption(
            event_id="assume-weekly",
            assumption_id="assume-weekly",
            statement="Publish every week.",
            pending_actions=("publish-weekly",),
        ),
        expected_revision=0,
    )
    controller.submit(
        InteractionEvent.agent_assumption(
            event_id="assume-notify",
            assumption_id="assume-notify",
            statement="Notify the team after publication.",
            pending_actions=("notify-team",),
        ),
        expected_revision=1,
    )
    controller.record_action_started("publish-weekly", expected_revision=2)
    controller.record_action_started("notify-team", expected_revision=3)

    corrected = controller.submit(
        InteractionEvent.correction(
            event_id="correct-release",
            target_id="assume-weekly",
            replacement="Publish only after verification.",
        ),
        expected_revision=4,
    )

    assert corrected.state.agent.pending_actions == ("notify-team",)
    assert corrected.pending_actions == {"notify-team": "started"}
    assert corrected.state.superseded_ids
    assert corrected.state.agent.next_move == "repair"


def test_checkpoint_recovery_cannot_restore_correction_invalidated_action(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.interaction_state import InteractionEvent

    controller = DurableInteractionController.initialize(tmp_path, project_id="project-245", run_id="run-245-recovery")
    controller.submit(
        InteractionEvent.agent_assumption(
            event_id="assume-weekly",
            assumption_id="assume-weekly",
            statement="Publish every week.",
            pending_actions=("publish-weekly",),
        ),
        expected_revision=0,
    )
    controller.submit(
        InteractionEvent.agent_assumption(
            event_id="assume-notify",
            assumption_id="assume-notify",
            statement="Notify the team after publication.",
            pending_actions=("notify-team",),
        ),
        expected_revision=1,
    )
    controller.record_action_started("publish-weekly", expected_revision=2)
    controller.record_action_started("notify-team", expected_revision=3)
    checkpoint = controller.checkpoint(expected_revision=4)

    controller.submit(
        InteractionEvent.correction(
            event_id="correct-release",
            target_id="assume-weekly",
            replacement="Publish only after verification.",
        ),
        expected_revision=4,
    )
    recovered = controller.recover(checkpoint)

    assert "publish-weekly" not in recovered.state.agent.pending_actions
    assert recovered.state.agent.pending_actions == ("notify-team",)
    assert recovered.pending_actions == {"notify-team": "unknown"}
    assert "assume-weekly" in recovered.state.superseded_ids


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        ("malformed.yaml", {"schema": 1}),
        (
            "00000000000000000003-malformed.yaml",
            {
                "event": {
                    "kind": "correction",
                    "event_id": "malformed",
                    "target_id": "assume-weekly",
                    "replacement": None,
                }
            },
        ),
    ],
)
def test_checkpoint_recovery_fails_closed_on_malformed_correction_evidence(
    tmp_path, filename: str, payload: dict[str, object]
) -> None:
    from research_tree.durable_interaction_state import (
        DurableInteractionController,
        DurableInteractionStateError,
    )
    from research_tree.interaction_state import InteractionEvent

    controller = DurableInteractionController.initialize(tmp_path, project_id="project-245", run_id="run-245-malformed")
    controller.submit(
        InteractionEvent.agent_assumption(
            event_id="assume-weekly",
            assumption_id="assume-weekly",
            statement="Publish every week.",
            pending_actions=("publish-weekly",),
        ),
        expected_revision=0,
    )
    controller.record_action_started("publish-weekly", expected_revision=1)
    checkpoint = controller.checkpoint(expected_revision=2)
    (controller.paths.episodes / filename).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DurableInteractionStateError):
        controller.recover(checkpoint)


def test_duplicate_correction_does_not_restore_invalidated_action(tmp_path) -> None:
    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.interaction_state import InteractionEvent

    controller = DurableInteractionController.initialize(tmp_path, project_id="project-245", run_id="run-245-replay")
    controller.submit(
        InteractionEvent.agent_assumption(
            event_id="assume-release",
            assumption_id="assume-weekly",
            statement="Publish every week.",
            pending_actions=("publish-weekly",),
        ),
        expected_revision=0,
    )
    controller.record_action_started("publish-weekly", expected_revision=1)
    correction = InteractionEvent.correction(
        event_id="correct-release",
        target_id="assume-weekly",
        replacement="Publish only after verification.",
    )
    corrected = controller.submit(correction, expected_revision=2)

    repeated = controller.submit(correction, expected_revision=corrected.revision)

    assert repeated.state.agent.pending_actions == ()
    assert repeated.pending_actions == {}
