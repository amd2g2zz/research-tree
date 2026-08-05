from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def test_entity_envelope_uses_utf8_without_bom_and_verifies_content_hash() -> None:
    from research_tree.contracts import EntityEnvelope, ContractError

    envelope = EntityEnvelope.create(
        kind="research-run",
        entity_id="run-contract",
        run_id="run-contract",
        actor={"kind": "coordinator", "id": "runtime", "host": "source"},
        status="alignment",
        payload={"task": "理解模糊需求"},
    )
    raw = envelope.canonical_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert json.loads(raw.decode("utf-8"))["content_hash"] == envelope.content_hash
    assert EntityEnvelope.from_dict(envelope.to_dict()) == envelope

    tampered = envelope.to_dict()
    tampered["payload"] = {"task": "changed"}
    with pytest.raises(ContractError, match="content_hash"):
        EntityEnvelope.from_dict(tampered)


def test_lifecycle_registry_is_exactly_the_runtime_transition_system() -> None:
    from research_tree.coordinator import LIFECYCLE_STATES, TRANSITIONS

    registry = json.loads(
        (
            Path(__file__).parents[1]
            / "openspec"
            / "changes"
            / "unify-research-runtime-alpha2"
            / "registries"
            / "lifecycle-matrix-v1.json"
        ).read_text(encoding="utf-8")
    )
    vocabulary = registry["state_vocabulary"]
    assert set(vocabulary) == {"active", "resumable", "terminal"}
    assert set().union(*map(set, vocabulary.values())) == set(LIFECYCLE_STATES)

    required = set(registry["transition_contract"]["required_fields"])
    assert required == {
        "from",
        "event",
        "to",
        "actor",
        "host",
        "guard",
        "side_effects",
        "next_actions",
        "failure_code",
    }
    edges = registry["transitions"]
    assert all(set(edge) == required for edge in edges)
    declared = {
        (edge["from"], edge["event"]): (edge["to"], edge["actor"])
        for edge in edges
    }
    assert len(declared) == len(edges)
    assert declared == TRANSITIONS
    assert all(edge["host"] == "canonical-runtime" for edge in edges)


def test_human_or_operator_transition_rejects_other_actors(tmp_path: Path) -> None:
    from research_tree.coordinator import ResearchRunCoordinator

    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-actor-boundary")
    state = coordinator.transition(
        state["run_id"],
        event="alignment_projection_ready",
        actor="coordinator",
        expected_revision=state["revision"],
        payload={"strategy_digest": state["authority_digest"]},
    )
    state = coordinator.transition(
        state["run_id"],
        event="handoff_confirmed",
        actor="human",
        expected_revision=state["revision"],
        payload={"displayed_digest": state["authority_digest"]},
    )

    with pytest.raises(coordinator.error_type) as rejected:
        coordinator.transition(
            state["run_id"],
            event="cancel_requested",
            actor="host",
            expected_revision=state["revision"],
            payload={"termination_reason": "operator-requested cancellation"},
        )

    assert rejected.value.code == "authority_denied"
    assert coordinator.status(state["run_id"]) == state
    assert coordinator.events(state["run_id"])[-1]["error_code"] == "authority_denied"


@pytest.mark.parametrize(
    "boundary",
    [
        "transition_after_run_update",
        "transition_after_side_effects",
        "transition_after_snapshot",
        "transition_after_event",
    ],
)
def test_transition_crash_boundaries_roll_back_and_retry_once(
    tmp_path: Path, boundary: str
) -> None:
    from research_tree.coordinator import ResearchRunCoordinator

    armed = True

    def fail_at(name: str) -> None:
        nonlocal armed
        if armed and name == boundary:
            armed = False
            raise RuntimeError(f"injected crash at {name}")

    coordinator = ResearchRunCoordinator(tmp_path, fault_injector=fail_at)
    before = coordinator.create("run-transition-crash")
    before_events = coordinator.events(before["run_id"])
    before_revisions = coordinator.revisions(before["run_id"])

    with pytest.raises(RuntimeError, match=boundary):
        coordinator.transition(
            before["run_id"],
            event="alignment_projection_ready",
            actor="coordinator",
            expected_revision=before["revision"],
            payload={"strategy_digest": before["authority_digest"]},
        )

    reopened = ResearchRunCoordinator(tmp_path)
    assert reopened.status(before["run_id"]) == before
    assert reopened.events(before["run_id"]) == before_events
    assert reopened.revisions(before["run_id"]) == before_revisions
    first_recovery = reopened.recover(before["run_id"])
    assert reopened.recover(before["run_id"]) == first_recovery

    committed = reopened.transition(
        before["run_id"],
        event="alignment_projection_ready",
        actor="coordinator",
        expected_revision=before["revision"],
        payload={"strategy_digest": before["authority_digest"]},
    )
    assert committed["revision"] == before["revision"] + 1
    assert committed["lifecycle_state"] == "handoff_pending"
    assert [
        event["event_type"]
        for event in reopened.events(before["run_id"])
        if event["event_type"] == "alignment_projection_ready"
    ] == ["alignment_projection_ready"]


def test_coordinator_rejects_illegal_transition_without_mutation(tmp_path: Path) -> None:
    from research_tree.coordinator import ResearchRunCoordinator

    coordinator = ResearchRunCoordinator(tmp_path)
    created = coordinator.create("run-lifecycle")
    with pytest.raises(coordinator.error_type, match="illegal_transition"):
        coordinator.transition(
            "run-lifecycle",
            event="delivery_accepted",
            actor="human",
            expected_revision=created["revision"],
        )
    assert coordinator.status("run-lifecycle")["revision"] == created["revision"]
    assert coordinator.status("run-lifecycle")["lifecycle_state"] == "alignment"
    assert coordinator.status("run-lifecycle")["state_digest"] == created["state_digest"]
    rejected = coordinator.events("run-lifecycle")[-1]
    assert rejected["accepted"] is False
    assert rejected["event_type"] == "transition_rejected"
    assert rejected["error_code"] == "illegal_transition"
    assert rejected["payload"] == {
        "actor": "human",
        "actual_revision": created["revision"],
        "attempted_event": "delivery_accepted",
        "attempted_revision": created["revision"],
        "current_state": "alignment",
        "next_action": "plan_alignment",
        "payload_digest": coordinator._digest({}),
        "reason_code": "illegal_transition",
    }

    # The same rejected request is audit-idempotent and remains outside the
    # canonical run revision stream.
    with pytest.raises(coordinator.error_type, match="illegal_transition"):
        coordinator.transition(
            "run-lifecycle",
            event="delivery_accepted",
            actor="human",
            expected_revision=created["revision"],
        )
    assert len(coordinator.events("run-lifecycle")) == 2
    assert coordinator.status("run-lifecycle") == created


def test_material_correction_invalidates_digest_and_keeps_task_identity(tmp_path: Path) -> None:
    from research_tree.coordinator import ResearchRunCoordinator
    from research_tree.leases import AttemptLease

    coordinator = ResearchRunCoordinator(tmp_path)
    created = coordinator.create(
        "run-correction",
        task_identity={"subject": "research-tree", "domain": "runtime"},
    )
    handoff = coordinator.transition(
        "run-correction",
        event="alignment_projection_ready",
        actor="coordinator",
        expected_revision=created["revision"],
        payload={"strategy_digest": "a" * 64},
    )
    assert handoff["lifecycle_state"] == "handoff_pending"
    result = coordinator.record_feedback(
        {
            "feedback_id": "feedback-subject",
            "run_id": "run-correction",
            "actor": "human",
            "kind": "correction",
            "message": "The diagnostic repository is evidence, not the research target.",
            "target_refs": ["task:subject", "strategy:a" + "a" * 63],
            "materiality": "material",
            "created_at": "2026-08-05T00:00:00+00:00",
            "successor_task_identity": {"subject": "autonomous-agent", "domain": "research"},
        },
        expected_revision=handoff["revision"],
    )
    assert result["lifecycle_state"] == "alignment"
    assert result["invalidated_digests"] == ["a" * 64]
    assert result["task_identity"]["subject"] == "autonomous-agent"
    with pytest.raises(coordinator.error_type, match="stale_digest"):
        coordinator.assert_current("run-correction", "a" * 64, action="dispatch")
    with pytest.raises(coordinator.error_type, match="stale_digest") as stale:
        coordinator.transition(
            "run-correction",
            event="alignment_projection_ready",
            actor="coordinator",
            expected_revision=result["revision"],
            payload={"strategy_digest": "a" * 64},
        )
    assert stale.value.code == "stale_digest"
    assert stale.value.next_action == "return_to_alignment_and_rederive_strategy"
    with pytest.raises(coordinator.error_type, match="stale_digest"):
        coordinator.issue_lease(
            AttemptLease.create(
                attempt_id="attempt-stale-strategy",
                work_item_id="work-stale-strategy",
                run_id="run-correction",
                owner="worker",
                status="leased",
                dispatch_digest="a" * 64,
                started_at="2026-08-05T00:00:00+00:00",
                lease_expires_at="2026-08-05T01:00:00+00:00",
            ),
            expected_revision=result["revision"],
        )
    assert coordinator.attempts("run-correction") == {}


def test_feedback_event_validates_invalidation_lineage_and_terminal_impact() -> None:
    from research_tree.contracts import ContractError, validate_feedback_event

    event = validate_feedback_event(
        {
            "feedback_id": "feedback-terminal",
            "run_id": "run-feedback",
            "actor": "human",
            "kind": "correction",
            "message": "The objective is infeasible under the confirmed authority.",
            "target_refs": ["strategy:" + "a" * 64],
            "materiality": "terminal",
            "created_at": "2026-08-05T00:00:00+00:00",
            "affected_fields": ["authority"],
            "invalidated_refs": ["strategy:" + "a" * 64],
            "successor_refs": ["run:run-successor"],
            "task_identity_disposition": "superseded",
        }
    )
    assert event["impact_class"] == "terminal"
    assert event["contradicted_refs"] == ["strategy:" + "a" * 64]
    with pytest.raises(ContractError, match="successor_task_identity"):
        validate_feedback_event(
            {
                **event,
                "task_identity_disposition": "rederived",
            }
        )


def test_host_event_is_idempotent_but_payload_conflict_is_rejected(tmp_path: Path) -> None:
    from research_tree.contracts import HostEvent
    from research_tree.coordinator import ResearchRunCoordinator
    from research_tree.leases import AttemptLease

    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-events")
    coordinator.issue_lease(
        AttemptLease.create(
            attempt_id="attempt-find-1",
            work_item_id="work-find-1",
            run_id="run-events",
            owner="worker-1",
            dispatch_digest="a" * 64,
            started_at="2026-08-05T00:00:00+00:00",
            lease_expires_at="2026-08-05T01:00:00+00:00",
        ),
        expected_revision=state["revision"],
    )
    state = coordinator.status("run-events")
    event = HostEvent.create(
        event_id="event-find-1",
        event_type="finding_submitted",
        run_id="run-events",
        round_id="round-events",
        host="claude-code",
        expected_revision=state["revision"],
        attempt_id="attempt-find-1",
        payload={
            "finding_pack_digest": "a" * 64,
            "evidence_refs": ["evidence-1"],
            "submission_status": "submitted",
            "output_digest": "b" * 64,
        },
    )
    first = coordinator.ingest_host_event(event)
    second = coordinator.ingest_host_event(event)
    assert first == second
    assert coordinator.reconcile_host("run-events")["status"] == "no_divergence_detected"
    assert coordinator.status("run-events")["lifecycle_state"] == "alignment"
    changed = HostEvent.create(
        event_id=event.event_id,
        event_type=event.event_type,
        run_id=event.run_id,
        round_id=event.round_id,
        host=event.host,
        expected_revision=event.expected_revision,
        attempt_id=event.attempt_id,
        payload={
            "finding_pack_digest": "a" * 64,
            "evidence_refs": ["evidence-2"],
            "submission_status": "submitted",
            "output_digest": "c" * 64,
        },
    )
    with pytest.raises(coordinator.error_type, match="event_id_conflict"):
        coordinator.ingest_host_event(changed)


def test_host_event_rejects_incomplete_event_specific_payload() -> None:
    from research_tree.contracts import ContractError, HostEvent

    with pytest.raises(ContractError, match="payload is incomplete") as error:
        HostEvent.create(
            event_id="event-incomplete",
            event_type="worker_finished",
            run_id="run-incomplete",
            round_id="round-events",
            host="codex",
            expected_revision=0,
            payload={"status": "completed"},
        )
    assert error.value.code == "incomplete_event_payload"


def test_provider_failure_event_rejects_raw_gateway_details() -> None:
    from research_tree.contracts import ContractError, HostEvent

    with pytest.raises(ContractError, match="raw diagnostics") as error:
        HostEvent.create(
            event_id="event-provider-raw",
            event_type="provider_failed",
            run_id="run-provider-raw",
            round_id="round-events",
            host="hermes",
            expected_revision=0,
            attempt_id="attempt-provider-raw",
            payload={
                "provider": "gateway",
                "model": "glm",
                "retry_category": "retryable",
                "opaque_code": "ctx-001",
                "gateway_log_ref": "log:provider-raw",
                "raw_error": "secret provider stack trace",
            },
        )
    assert error.value.code == "raw_provider_details"


def test_safe_provider_failure_moves_attempt_to_retryable_without_completing_run(
    tmp_path: Path,
) -> None:
    from research_tree.contracts import HostEvent
    from research_tree.coordinator import ResearchRunCoordinator
    from research_tree.leases import AttemptLease

    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-provider-failure")
    coordinator.issue_lease(
        AttemptLease.create(
            attempt_id="attempt-provider-failure",
            work_item_id="work-provider-failure",
            run_id="run-provider-failure",
            owner="hermes-worker",
            dispatch_digest="d" * 64,
            started_at="2026-08-05T00:00:00+00:00",
            lease_expires_at="2026-08-05T01:00:00+00:00",
        ),
        expected_revision=state["revision"],
    )
    state = coordinator.status("run-provider-failure")
    event = HostEvent.create(
        event_id="event-provider-failure",
        event_type="provider_failed",
        run_id="run-provider-failure",
        round_id="round-events",
        host="hermes",
        expected_revision=state["revision"],
        attempt_id="attempt-provider-failure",
        payload={
            "provider": "gateway",
            "model": "glm",
            "retry_category": "context_limit",
            "opaque_code": "ctx-001",
            "gateway_log_ref": "log:provider-failure",
        },
    )

    coordinator.ingest_host_event(event)
    assert coordinator.attempts("run-provider-failure")["attempt-provider-failure"]["status"] == "retryable"
    assert coordinator.status("run-provider-failure")["lifecycle_state"] == "alignment"
    state = coordinator.status("run-provider-failure")
    retry = coordinator.retry_attempt(
        "run-provider-failure",
        "attempt-provider-failure",
        dispatch_digest="e" * 64,
        expected_revision=state["revision"],
        lease_seconds=60,
    )
    assert retry["predecessor"]["status"] == "retryable"
    assert retry["retry"]["attempt_id"] == "work-provider-failure-retry-1"
    assert retry["retry"]["status"] == "leased"
    assert coordinator.attempts("run-provider-failure")["attempt-provider-failure"]["status"] == "retryable"


def test_host_event_rejects_unbound_attempt_without_mutating_ledger(tmp_path: Path) -> None:
    from research_tree.contracts import HostEvent
    from research_tree.coordinator import ResearchRunCoordinator

    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-unbound-event")
    event = HostEvent.create(
        event_id="event-unbound-1",
        event_type="worker_finished",
        run_id="run-unbound-event",
        round_id="round-events",
        host="codex",
        expected_revision=state["revision"],
        attempt_id="attempt-does-not-exist",
        payload={"terminal_status": "completed", "artifact_refs": ["finding-1"]},
    )
    with pytest.raises(coordinator.error_type, match="attempt_not_found"):
        coordinator.ingest_host_event(event)
    assert coordinator.status("run-unbound-event")["revision"] == state["revision"]
    events = coordinator.events("run-unbound-event")
    assert len(events) == 1
    assert events[0]["event_type"] == "run_initialized"


def test_attempt_bound_host_event_requires_attempt_id(tmp_path: Path) -> None:
    from research_tree.contracts import HostEvent
    from research_tree.coordinator import ResearchRunCoordinator

    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-missing-attempt")
    event = HostEvent.create(
        event_id="event-missing-attempt",
        event_type="finding_submitted",
        run_id="run-missing-attempt",
        round_id="round-events",
        host="hermes",
        expected_revision=state["revision"],
        payload={
            "finding_pack_digest": "a" * 64,
            "evidence_refs": ["evidence-1"],
            "submission_status": "submitted",
            "output_digest": "b" * 64,
        },
    )
    with pytest.raises(coordinator.error_type, match="attempt_binding_required"):
        coordinator.ingest_host_event(event)
    assert coordinator.status("run-missing-attempt")["revision"] == state["revision"]


def test_expired_attempt_cannot_submit_success_event(tmp_path: Path) -> None:
    from research_tree.contracts import HostEvent
    from research_tree.coordinator import ResearchRunCoordinator
    from research_tree.leases import AttemptLease

    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create("run-expired-event")
    coordinator.issue_lease(
        AttemptLease.create(
            attempt_id="attempt-expired",
            work_item_id="work-expired",
            run_id="run-expired-event",
            owner="worker-1",
            status="unknown",
            dispatch_digest="b" * 64,
            started_at="2026-08-05T00:00:00+00:00",
            lease_expires_at="2026-08-05T00:01:00+00:00",
        ),
        expected_revision=state["revision"],
    )
    state = coordinator.status("run-expired-event")
    event = HostEvent.create(
        event_id="event-expired-success",
        event_type="worker_finished",
        run_id="run-expired-event",
        round_id="round-events",
        host="codex",
        expected_revision=state["revision"],
        attempt_id="attempt-expired",
        payload={"terminal_status": "completed", "artifact_refs": ["finding-1"]},
    )
    with pytest.raises(coordinator.error_type, match="attempt_expired"):
        coordinator.ingest_host_event(event)
    assert coordinator.status("run-expired-event")["revision"] == state["revision"]


def test_single_transcript_is_observation_not_model_attribution() -> None:
    from research_tree.evaluation_fixtures import assess_attribution

    assessment = assess_attribution(
        [{"model": "GLM5.2", "host": "claude-code", "skill_revision": "alpha2", "result": "failed"}]
    )
    assert assessment["classification"] == "observation"
    assert assessment["causal_attribution"] == "unresolved"
    assert assessment["release_eligible"] is False


def test_alignment_correction_quarantines_handoff_and_rejects_wrong_pending_node(tmp_path: Path) -> None:
    import importlib.util

    path = Path(__file__).parents[1] / "scripts" / "alignment_controller.py"
    spec = importlib.util.spec_from_file_location("alignment_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.init(tmp_path, "align-correction")
    update = {
        "nodes": [
            {"id": "outcome", "type": "outcome", "statement": "Build the right agent.", "status": "supported", "impact": 5, "source": "joint"},
            {"id": "use", "type": "intended_use", "statement": "Use it to plan implementation.", "status": "supported", "impact": 4, "source": "joint"},
            {"id": "scope", "type": "scope_boundary", "statement": "Research and design.", "status": "supported", "impact": 4, "source": "joint"},
            {"id": "delivery", "type": "delivery", "statement": "Deliver a deep report.", "status": "supported", "impact": 4, "source": "joint"},
            {"id": "authority", "type": "authority", "statement": "Agent researches after handoff.", "status": "supported", "impact": 5, "source": "joint"},
            {"id": "success", "type": "success_oracle", "statement": "Every P0 closes.", "status": "supported", "impact": 5, "source": "joint"},
            {"id": "feasible", "type": "feasibility", "statement": "Feasible.", "status": "supported", "impact": 3, "source": "joint"},
            {"id": "strategy", "type": "strategy", "statement": "Use evidence and validation.", "status": "supported", "impact": 5, "source": "joint"},
            {"id": "question", "type": "research_question", "statement": "Which plan?", "status": "candidate", "impact": 5, "source": "joint", "oracle": "A plan is validated."},
            {"id": "human-choice", "type": "constraint", "statement": "What risk boundary matters?", "status": "candidate", "impact": 5, "human_only": True, "source": "agent"},
            {"id": "evidence", "type": "evidence", "statement": "A source exists.", "status": "supported", "impact": 2, "source": "reconnaissance", "attributes": {"anchor": {"kind": "source", "ref": "source:1"}}},
        ],
        "edges": [{"id": "support", "source_id": "evidence", "target_id": "question", "relation": "supports"}],
    }
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps(update), encoding="utf-8")
    first = module.plan(tmp_path, "align-correction", graph)
    store = module.AlignmentGraphStore(module.database_path(tmp_path, "align-correction"))
    with pytest.raises(module.ControllerError, match="pending"):
        store.record("question", "answered", "x")
    store.record("human-choice", "answered", "boundary stated")
    decision = module.plan(tmp_path, "align-correction", graph)
    corrected = store.apply_correction(
        {"feedback_id": "feedback-target", "run_id": "align-correction", "actor": "human", "kind": "correction", "message": "The evidence repository is not the target.", "target_refs": ["strategy:" + decision["alignment_digest"]], "materiality": "material", "created_at": "2026-08-05T00:00:00+00:00"},
        expected_revision=store.status()["controller"]["revision"],
    )
    assert corrected["controller"]["status"] == "alignment"
    assert corrected["controller"]["handoff"] is None
    assert decision["alignment_digest"] in corrected["controller"]["invalidated_digests"]


def test_adaptive_policy_uses_decision_deficits_and_never_prunes_p0() -> None:
    from research_tree.policy import AdaptiveResearchPolicy

    policy = AdaptiveResearchPolicy()
    candidates = policy.propose(
        slots={
            "p0": {"priority": "P0", "question": "Validate the critical path", "closure": 0.1},
            "p1": {"priority": "P1", "question": "Explore an optional path", "closure": 0.2},
        },
        findings=[],
    )
    assert candidates[0]["slot_id"] == "p0"
    state = policy.apply(
        {"p0": {"priority": "P0", "question": "Validate the critical path", "closure": 0.1}},
        [{"id": "f1", "decision_slot_id": "p0", "observations": [{"claim": "x", "anchor": {"kind": "source", "ref": "a"}}], "option_effects": [], "remaining_uncertainties": ["oracle"]}],
    )
    assert state["realized_delta"]["baseline_zero"] is False
    assert state["growth"]
    assert state["growth"][0]["trigger"].startswith("finding:f1")
    assert state["growth"][0]["oracle"]
    assert state["growth"][0]["action_id"].startswith("action-p0-")
    pruned = policy.prune(state["actions"], protected_slots={"p0"})
    assert all(item["slot_id"] == "p0" or item["status"] == "pruned" for item in pruned)


def test_adaptive_policy_reuses_persisted_baseline_for_second_round_gain() -> None:
    from research_tree.policy import AdaptiveResearchPolicy

    policy = AdaptiveResearchPolicy()
    slots = {"p0": {"priority": "P0", "question": "Validate", "closure": 0.1}}
    finding = {
        "id": "f-baseline",
        "decision_slot_id": "p0",
        "observations": [{"claim": "x", "anchor": {"kind": "source", "ref": "a"}}],
        "option_effects": [],
        "remaining_uncertainties": [],
    }
    first = policy.apply(slots, [finding], transition_index=1)
    second = policy.apply(
        slots,
        [finding],
        baseline=first["baseline"],
        transition_index=2,
    )
    assert first["realized_delta"]["baseline_zero"] is False
    assert second["transition_index"] == 2
    assert second["realized_delta"]["baseline_zero"] is True
    assert second["realized_delta"]["duplicate_only"] is True


def test_canonical_run_cli_exposes_status_and_replay(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from research_tree.cli import main

    assert main(["run", "init", "--workspace", str(tmp_path), "--run-id", "run-cli"]) == 0
    capsys.readouterr()
    assert main(["run", "status", "--workspace", str(tmp_path), "--run-id", "run-cli"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["lifecycle_state"] == "alignment"
    assert main(["run", "replay", "--workspace", str(tmp_path), "--run-id", "run-cli"]) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["run_id"] == "run-cli"
    assert replay["events"]
