from __future__ import annotations

from pathlib import Path

import pytest


def correction_context(tmp_path: Path):
    from research_tree import CorrectionBinding, CorrectionEvent, ResearchRunCoordinator, RunLedger
    from research_tree.domain import ArtifactRef

    ledger = RunLedger(tmp_path / "correction-ledger")
    ledger.create_run("run-correction")

    def append(artifact_id, kind, payload, parents=()):
        return ledger.append_artifact(
            "run-correction",
            artifact_id,
            kind,
            payload,
            parent_refs=parents,
            expected_revision=ledger.get_revision("run-correction"),
        )

    intent = append("intent-current", "intent-model", {"task_id": "task-research"})
    brief = append(
        "brief-current",
        "working-brief",
        {"task_id": "task-research", "domain_id": "domain-diagnostic-repository"},
        (ArtifactRef("run-correction", intent.id, intent.revision),),
    )
    strategy = append(
        "strategy-current",
        "research-strategy",
        {"subject": "diagnostic repository"},
        (ArtifactRef("run-correction", brief.id, brief.revision),),
    )
    handoff = append(
        "handoff-current",
        "alignment-handoff",
        {"confirmed": True, "strategy_digest": strategy.content_hash},
        (ArtifactRef("run-correction", strategy.id, strategy.revision),),
    )
    decision_map = append(
        "decision-map-current",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-target", "priority": "P0"}]},
        (ArtifactRef("run-correction", handoff.id, handoff.revision),),
    )
    coordinator = ResearchRunCoordinator(ledger)
    state = coordinator.initialize(
        run_id="run-correction",
        alignment_handoff=handoff,
        blueprint_target=decision_map,
        expected_revision=ledger.get_revision("run-correction"),
        idempotency_key="initialize-correction-run",
    )
    artifacts = {
        "intent_model": intent,
        "working_brief": brief,
        "decision_map": decision_map,
        "strategy": strategy,
        "handoff": handoff,
    }
    affected = {role: CorrectionBinding.from_artifact(role, artifact) for role, artifact in artifacts.items()}
    event = CorrectionEvent.create(
        event_id="correction-wrong-subject",
        run_id="run-correction",
        kind="correction",
        actor="human",
        reason="The repository is diagnostic evidence, not the research target.",
        relation="supersedes",
        task_id="task-research",
        domain_id="domain-diagnostic-repository",
        successor_task_id="task-research",
        successor_domain_id="domain-autonomous-agent",
        affected=affected,
    )
    return ledger, coordinator, state, artifacts, event


def successor_bindings(ledger, event, artifacts, *, parallel=False):
    from research_tree import CorrectionBinding
    from research_tree.domain import ArtifactRef

    fresh = {}
    prior_fresh = None
    for role in ("intent_model", "working_brief", "strategy", "handoff", "decision_map"):
        stale = artifacts[role]
        parents = [ArtifactRef(stale.round_id, stale.id, stale.revision)]
        if prior_fresh is not None:
            parents.append(ArtifactRef(prior_fresh.round_id, prior_fresh.id, prior_fresh.revision))
        payload = {"successor_for": event.event_id, "role": role}
        if role == "intent_model":
            payload["task_id"] = event.successor_task_id
        elif role == "working_brief":
            payload.update(task_id=event.successor_task_id, domain_id=event.successor_domain_id)
        elif role == "handoff":
            payload["confirmed"] = True
        artifact_id = f"parallel-{role.replace('_', '-')}" if parallel else stale.id
        prior_fresh = fresh[role] = ledger.append_artifact(
            event.run_id,
            artifact_id,
            stale.kind,
            payload,
            parent_refs=parents,
            expected_revision=ledger.get_revision(event.run_id),
        )
    affected = {role: CorrectionBinding.from_artifact(role, item) for role, item in fresh.items()}
    authority = {
        "correction_event_id": event.event_id,
        "bindings": {role: affected[role].to_dict() for role in ("decision_map", "strategy", "handoff")},
    }
    return fresh, affected, authority


def test_material_correction_atomically_preserves_and_supersedes_exact_state(tmp_path: Path) -> None:
    from research_tree import CORRECTION_EVENT_KIND, STALE_STATE_QUARANTINE_KIND
    from research_tree.domain import ArtifactRef

    ledger, coordinator, predecessor, artifacts, event = correction_context(tmp_path)
    old_lease = ledger.append_artifact(
        "run-correction",
        "attempt-old-strategy",
        "attempt-lease",
        {"status": "active", "work_item_id": "work-old-strategy"},
        parent_refs=(ArtifactRef(predecessor.round_id, predecessor.id, predecessor.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    unrelated = ledger.append_artifact(
        event.run_id,
        "attempt-unrelated",
        "attempt-lease",
        {"status": "active"},
        expected_revision=ledger.get_revision(event.run_id),
    )

    successor = coordinator.apply_correction(
        event,
        expected_revision=ledger.get_revision("run-correction"),
    )

    assert successor.payload["state"] == "alignment"
    assert successor.payload["task_id"] == "task-research"
    assert successor.payload["domain_id"] == "domain-autonomous-agent"
    assert successor.payload["correction_event_id"] == event.event_id
    assert (
        successor.payload["previous_state_ref"]
        == ArtifactRef(predecessor.round_id, predecessor.id, predecessor.revision).to_dict()
    )
    assert (
        coordinator.ledger.get_artifact(ArtifactRef(predecessor.round_id, predecessor.id, predecessor.revision))
        == predecessor
    )
    snapshot = ledger.load_run("run-correction")
    correction = next(item for item in snapshot.artifacts if item.kind == CORRECTION_EVENT_KIND)
    quarantine = next(item for item in snapshot.artifacts if item.kind == STALE_STATE_QUARANTINE_KIND)
    assert correction.payload["relation"] == "supersedes"
    assert quarantine.payload["correction_event_id"] == event.event_id
    assert set(quarantine.payload["stale_bindings"]) == set(artifacts)
    dependent_refs = quarantine.payload["dependent_refs"]
    assert ArtifactRef(old_lease.round_id, old_lease.id, old_lease.revision).to_dict() in dependent_refs
    assert ArtifactRef(unrelated.round_id, unrelated.id, unrelated.revision).to_dict() not in dependent_refs
    assert {role: binding["digest"] for role, binding in quarantine.payload["stale_bindings"].items()} == {
        role: artifact.content_hash for role, artifact in artifacts.items()
    }

    replay = coordinator.apply_correction(event, expected_revision=0)
    assert replay == successor
    changed = event.to_dict()
    changed["reason"] = "Changed reuse must conflict."
    with pytest.raises(coordinator.event_conflict_error, match="event_id_conflict"):
        coordinator.apply_correction(changed, expected_revision=0)


def test_correction_quarantines_descendant_behind_unknown_intermediate_kind(tmp_path: Path) -> None:
    from research_tree import ResearchRunCoordinator
    from research_tree.domain import ArtifactRef

    ledger, coordinator, predecessor, _, event = correction_context(tmp_path)
    intermediate = ledger.append_artifact(
        event.run_id,
        "unclassified-intermediate",
        "future-canonical-artifact",
        {"status": "current"},
        parent_refs=(ArtifactRef(predecessor.round_id, predecessor.id, predecessor.revision),),
        expected_revision=ledger.get_revision(event.run_id),
    )
    descendant = ledger.append_artifact(
        event.run_id,
        "descendant-behind-unknown",
        "attempt-lease",
        {"attempt_id": "descendant-behind-unknown", "status": "active"},
        parent_refs=(ArtifactRef(intermediate.round_id, intermediate.id, intermediate.revision),),
        expected_revision=ledger.get_revision(event.run_id),
    )
    independent_root = ledger.append_artifact(
        event.run_id,
        "independent-root",
        "future-canonical-artifact",
        {"status": "current"},
        expected_revision=ledger.get_revision(event.run_id),
    )
    independent_descendant = ledger.append_artifact(
        event.run_id,
        "independent-descendant",
        "attempt-lease",
        {"attempt_id": "independent-descendant", "status": "active"},
        parent_refs=(ArtifactRef(independent_root.round_id, independent_root.id, independent_root.revision),),
        expected_revision=ledger.get_revision(event.run_id),
    )

    coordinator.apply_correction(event, expected_revision=ledger.get_revision(event.run_id))

    quarantined = coordinator._quarantined_refs(event.run_id)
    assert ArtifactRef(descendant.round_id, descendant.id, descendant.revision) in quarantined
    assert (
        ArtifactRef(independent_descendant.round_id, independent_descendant.id, independent_descendant.revision)
        not in quarantined
    )
    restarted = ResearchRunCoordinator(ledger)
    paths = restarted.why_not_complete(event.run_id)["quarantined_paths"]
    descendant_path = next(
        item
        for item in paths
        if item["artifact_ref"] == ArtifactRef(descendant.round_id, descendant.id, descendant.revision).to_dict()
    )
    assert descendant_path == {
        "correction_event_id": event.event_id,
        "artifact_ref": ArtifactRef(descendant.round_id, descendant.id, descendant.revision).to_dict(),
        "path": [
            ArtifactRef(predecessor.round_id, predecessor.id, predecessor.revision).to_dict(),
            ArtifactRef(intermediate.round_id, intermediate.id, intermediate.revision).to_dict(),
            ArtifactRef(descendant.round_id, descendant.id, descendant.revision).to_dict(),
        ],
    }
    recovery = restarted.recover(event.run_id)
    assert recovery["reconciled_attempts"] == ["independent-descendant"]
    assert recovery["quarantined_attempts"] == ["descendant-behind-unknown"]


def test_invalid_correction_binding_and_fault_leave_no_partial_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from research_tree import (
        CoordinatorConflictError,
        CorrectionBinding,
        CorrectionEvent,
        InvalidFeedbackError,
        RunLedger,
    )

    ledger, coordinator, predecessor, artifacts, event = correction_context(tmp_path)
    malformed = event.to_dict()
    malformed["affected"]["strategy"]["digest"] = "0" * 64
    before = ledger.load_run("run-correction")
    with pytest.raises(CoordinatorConflictError, match="digest"):
        coordinator.apply_correction(
            CorrectionEvent.from_value(malformed),
            expected_revision=ledger.get_revision("run-correction"),
        )
    assert ledger.load_run("run-correction") == before
    assert coordinator.state("run-correction") == predecessor

    parallel = ledger.append_artifact(
        event.run_id,
        "strategy-parallel",
        artifacts["strategy"].kind,
        {"subject": "parallel but not authoritative"},
        parent_refs=artifacts["strategy"].parent_refs,
        expected_revision=ledger.get_revision(event.run_id),
    )
    for field, value in (
        ("affected", CorrectionBinding.from_artifact("strategy", parallel).to_dict()),
        ("task_id", "task-parallel"),
        ("domain_id", "domain-parallel"),
    ):
        invalid = event.to_dict()
        if field == "affected":
            invalid[field]["strategy"] = value
        else:
            invalid[field] = value
        snapshot = ledger.load_run(event.run_id)
        with pytest.raises(CoordinatorConflictError):
            coordinator.apply_correction(invalid, expected_revision=ledger.get_revision(event.run_id))
        assert ledger.load_run(event.run_id) == snapshot

    missing = event.to_dict()
    missing["affected"].pop("handoff")
    with pytest.raises(InvalidFeedbackError, match="affected roles"):
        CorrectionEvent.from_value(missing)
    before = ledger.load_run(event.run_id)

    def fail_before_commit() -> None:
        raise RuntimeError("injected correction fault")

    monkeypatch.setattr(RunLedger, "_before_commit", staticmethod(fail_before_commit))
    with pytest.raises(RuntimeError, match="injected correction fault"):
        coordinator.apply_correction(
            event,
            expected_revision=ledger.get_revision("run-correction"),
        )
    assert ledger.load_run("run-correction") == before
    assert coordinator.state("run-correction") == predecessor


def test_stale_authority_is_quarantined_and_fresh_successor_can_dispatch(tmp_path: Path) -> None:
    from research_tree import CoordinatorConflictError

    ledger, coordinator, _, artifacts, event = correction_context(tmp_path)
    successor = coordinator.apply_correction(
        event,
        expected_revision=ledger.get_revision("run-correction"),
    )
    stale_authority = event.action_authority()
    before = ledger.load_run("run-correction")
    sensitive = (
        ("alignment_projection_ready", "coordinator"),
        ("handoff_confirmed", "human"),
        ("deliveries_compiled", "coordinator"),
        ("delivery_accepted", "human"),
    )
    with pytest.raises(coordinator.stale_state_error, match="stale_digest") as dispatch_error:
        coordinator.dispatch(
            run_id="run-correction",
            work_item={
                "work_item_id": "work-old",
                "success_oracle": "Produce current evidence.",
                "authority_binding": stale_authority,
            },
            worker_id="worker-1",
            expected_revision=ledger.get_revision("run-correction"),
        )
    assert dispatch_error.value.reason == "stale_digest"
    assert dispatch_error.value.next_action == "reenter_alignment"
    for transition, actor in sensitive:
        with pytest.raises(coordinator.stale_state_error, match="stale_digest"):
            coordinator.transition(
                "run-correction",
                transition,
                actor,
                expected_revision=ledger.get_revision("run-correction"),
                payload={"authority_binding": stale_authority},
            )
    with pytest.raises(coordinator.stale_state_error, match="stale_digest"):
        coordinator.complete(
            "run-correction",
            actor="human",
            expected_revision=ledger.get_revision("run-correction"),
            requirements={"authority_binding": stale_authority},
        )
    assert ledger.load_run("run-correction") == before
    assert coordinator.state("run-correction") == successor

    _, _, parallel_authority = successor_bindings(ledger, event, artifacts, parallel=True)
    before_parallel = ledger.load_run(event.run_id)
    with pytest.raises(coordinator.stale_state_error):
        coordinator.transition(
            event.run_id,
            "alignment_projection_ready",
            "coordinator",
            expected_revision=ledger.get_revision(event.run_id),
            payload={"authority_binding": parallel_authority},
        )
    assert ledger.load_run(event.run_id) == before_parallel
    _, _, fresh_authority = successor_bindings(ledger, event, artifacts)
    with pytest.raises(CoordinatorConflictError, match="strategy_projection"):
        coordinator.dispatch(
            run_id="run-correction",
            work_item={
                "work_item_id": "work-current",
                "success_oracle": "Produce successor-bound evidence.",
                "authority_binding": fresh_authority,
            },
            worker_id="worker-1",
            expected_revision=ledger.get_revision("run-correction"),
        )


def test_reopen_requires_fresh_five_role_successor_bindings(tmp_path: Path) -> None:
    from research_tree import CorrectionEvent
    from research_tree.domain import ArtifactRef

    ledger, coordinator, _, artifacts, event = correction_context(tmp_path)
    first_successor = coordinator.apply_correction(
        event,
        expected_revision=ledger.get_revision(event.run_id),
    )
    stale_reopen = CorrectionEvent.create(
        event_id="reopen-stale-target",
        run_id=event.run_id,
        kind="reopen",
        actor="human",
        reason="Reopen the corrected target.",
        relation="reopens",
        task_id=event.successor_task_id,
        domain_id=event.successor_domain_id,
        successor_task_id=event.successor_task_id,
        successor_domain_id=event.successor_domain_id,
        affected=event.affected,
    )
    with pytest.raises(coordinator.stale_state_error, match="stale_digest"):
        coordinator.apply_correction(
            stale_reopen,
            expected_revision=ledger.get_revision(event.run_id),
        )

    _, fresh_bindings, _ = successor_bindings(ledger, event, artifacts)
    reopen = CorrectionEvent.create(
        event_id="reopen-current-target",
        run_id=event.run_id,
        kind="reopen",
        actor="human",
        reason="Reopen the successor interpretation with explicit current state.",
        relation="reopens",
        task_id=event.successor_task_id,
        domain_id=event.successor_domain_id,
        successor_task_id=event.successor_task_id,
        successor_domain_id="domain-reopened-research",
        affected=fresh_bindings,
    )
    reopened = coordinator.apply_correction(
        reopen,
        expected_revision=ledger.get_revision(event.run_id),
    )
    assert reopened.payload["correction_relation"] == "reopens"
    assert reopened.payload["domain_id"] == "domain-reopened-research"
    assert (
        coordinator.ledger.get_artifact(
            ArtifactRef(first_successor.round_id, first_successor.id, first_successor.revision)
        )
        == first_successor
    )


def test_wrong_subject_regression_fixture_matches_correction_contract(tmp_path: Path) -> None:
    import json

    fixture = json.loads(
        (Path(__file__).parents[1] / "evaluation" / "cases" / "correction-invalidation-v1.json").read_text(
            encoding="utf-8"
        )
    )
    ledger, coordinator, _, _, event = correction_context(tmp_path)
    successor = coordinator.apply_correction(
        event,
        expected_revision=ledger.get_revision("run-correction"),
    )
    with pytest.raises(coordinator.stale_state_error) as stale:
        coordinator.dispatch(
            run_id=event.run_id,
            work_item={
                "work_item_id": "work-stale-regression",
                "success_oracle": "Use the old strategy.",
                "authority_binding": event.action_authority(),
            },
            worker_id="worker-regression",
            expected_revision=ledger.get_revision(event.run_id),
        )
    assert fixture["input"]["correction_event_id"] == event.event_id
    assert fixture["expected"]["old_strategy_executable"] is False
    assert (successor.payload["state"], successor.payload["correction_relation"]) == ("alignment", "supersedes")
    assert (stale.value.reason, stale.value.next_action) == ("stale_digest", "reenter_alignment")
