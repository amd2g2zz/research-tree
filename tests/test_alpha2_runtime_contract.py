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


def _confirmed_initialization_fixture(
    tmp_path: Path,
    *,
    include_confirmation: bool = True,
    include_handoff_parent: bool = True,
):
    from research_tree.coordinator import ResearchRunCoordinator
    from research_tree.sqlite_ledger import SQLiteRunLedger

    coordinator = ResearchRunCoordinator(tmp_path)
    state = coordinator.create(
        "run-init-contract",
        task_identity={"subject": "research-runtime"},
        authority={"scope": "confirmed"},
    )
    ledger = SQLiteRunLedger(tmp_path)
    model = ledger.append_artifact(
        run_id=state["run_id"],
        artifact_id="intent-model",
        kind="intent-model",
        payload={"hypotheses": [{"id": "hypothesis-1", "statement": "Build the runtime."}]},
        actor_kind="coordinator",
        actor_id="alignment",
        status="accepted",
        expected_run_revision=state["revision"],
    )
    brief = ledger.append_artifact(
        run_id=state["run_id"],
        artifact_id="working-brief",
        kind="working-brief",
        payload={"objective": "Build the runtime."},
        actor_kind="coordinator",
        actor_id="alignment",
        status="accepted",
        parent_refs=[{"run_id": state["run_id"], "artifact_id": model["id"], "revision": model["revision"]}],
        expected_run_revision=state["revision"] + 1,
    )
    graph = ledger.append_artifact(
        run_id=state["run_id"],
        artifact_id="alignment-graph",
        kind="alignment-graph",
        payload={"nodes": ["objective"], "edges": []},
        actor_kind="coordinator",
        actor_id="alignment",
        status="accepted",
        expected_run_revision=state["revision"] + 2,
    )
    strategy_digest = "a" * 64
    handoff_payload = {
        "run_id": state["run_id"],
        "alignment_revision": 4,
        "alignment_digest": "b" * 64,
        "strategy_digest": strategy_digest,
        "objective": "Build the runtime.",
        "execution_context": {"scope": "confirmed"},
        "alignment_graph_ref": {"run_id": state["run_id"], "artifact_id": graph["id"], "revision": graph["revision"], "content_hash": graph["content_hash"]},
        "working_brief_ref": {"run_id": state["run_id"], "artifact_id": brief["id"], "revision": brief["revision"], "content_hash": brief["content_hash"]},
        "intent_model_ref": {"run_id": state["run_id"], "artifact_id": model["id"], "revision": model["revision"], "content_hash": model["content_hash"]},
    }
    if include_confirmation:
        handoff_payload["confirmation"] = {
            "actor_id": "requester",
            "response_digest": "c" * 64,
            "displayed_strategy_digest": strategy_digest,
            "confirmed_at": "2026-08-05T00:00:00Z",
        }
    handoff = ledger.append_artifact(
        run_id=state["run_id"],
        artifact_id="alignment-handoff",
        kind="alignment-handoff",
        payload=handoff_payload,
        actor_kind="coordinator",
        actor_id="alignment",
        status="confirmed",
        parent_refs=[
            {"run_id": state["run_id"], "artifact_id": graph["id"], "revision": graph["revision"]},
            {"run_id": state["run_id"], "artifact_id": brief["id"], "revision": brief["revision"]},
            {"run_id": state["run_id"], "artifact_id": model["id"], "revision": model["revision"]},
        ],
        expected_run_revision=state["revision"] + 3,
    )
    target_payload = {
        "target_id": "blueprint-target",
        "run_id": state["run_id"],
        "working_brief_ref": handoff_payload["working_brief_ref"],
        "intent_model_ref": handoff_payload["intent_model_ref"],
        "alignment_handoff_ref": {"run_id": state["run_id"], "artifact_id": handoff["id"], "revision": handoff["revision"], "content_hash": handoff["content_hash"]},
        "slots": [{
            "slot_id": "slot-p0",
            "priority": "P0",
            "question": "Which architecture closes the requirement?",
            "decision_consequence": "Select implementation architecture.",
            "options": ["a", "b"],
            "required_evidence_classes": ["repository"],
            "required_oracles": ["oracle-1"],
            "fallback": "Block.",
            "reversal_condition": "Contrary evidence.",
            "status": "open",
            "lineage_refs": ["working-brief"],
        }],
        "change": {"kind": "initial", "reason": "Confirmed handoff.", "predecessor_ref": None},
    }
    target_parents = [
        {"run_id": state["run_id"], "artifact_id": brief["id"], "revision": brief["revision"]},
        {"run_id": state["run_id"], "artifact_id": model["id"], "revision": model["revision"]},
    ]
    if include_handoff_parent:
        target_parents.insert(0, {"run_id": state["run_id"], "artifact_id": handoff["id"], "revision": handoff["revision"]})
    target = ledger.append_artifact(
        run_id=state["run_id"],
        artifact_id="blueprint-target",
        kind="blueprint-target",
        payload=target_payload,
        actor_kind="coordinator",
        actor_id="blueprint",
        status="active",
        parent_refs=target_parents,
        expected_run_revision=state["revision"] + 4,
    )
    return coordinator, state, handoff, target


def test_coordinator_initializes_only_from_confirmed_exact_lineage(tmp_path: Path) -> None:
    coordinator, state, handoff, target = _confirmed_initialization_fixture(tmp_path)

    initialized = coordinator.initialize_from_alignment(
        state["run_id"],
        handoff_ref={"run_id": state["run_id"], "artifact_id": handoff["id"], "revision": handoff["revision"], "content_hash": handoff["content_hash"]},
        blueprint_target_ref={"run_id": state["run_id"], "artifact_id": target["id"], "revision": target["revision"], "content_hash": target["content_hash"]},
        expected_revision=coordinator.status(state["run_id"])["revision"],
    )

    assert initialized["lifecycle_state"] == "autonomous_research"
    assert [event["event_type"] for event in coordinator.events(state["run_id"])] [-2:] == ["handoff_confirmed", "blueprint_target_bound"]
    events_before_retry = coordinator.events(state["run_id"])
    repeated = coordinator.initialize_from_alignment(
        state["run_id"],
        handoff_ref={"run_id": state["run_id"], "artifact_id": handoff["id"], "revision": handoff["revision"], "content_hash": handoff["content_hash"]},
        blueprint_target_ref={"run_id": state["run_id"], "artifact_id": target["id"], "revision": target["revision"], "content_hash": target["content_hash"]},
        expected_revision=initialized["revision"],
    )
    assert repeated == initialized
    assert coordinator.events(state["run_id"]) == events_before_retry


@pytest.mark.parametrize("committed_prefix", ["handoff_pending", "autonomous_research"])
def test_initialization_resumes_committed_prefix_without_duplicate_events(
    tmp_path: Path, committed_prefix: str
) -> None:
    coordinator, state, handoff, target = _confirmed_initialization_fixture(tmp_path)
    run_id = state["run_id"]
    handoff_ref = {
        "run_id": run_id,
        "artifact_id": handoff["id"],
        "revision": handoff["revision"],
        "content_hash": handoff["content_hash"],
    }
    target_ref = {
        "run_id": run_id,
        "artifact_id": target["id"],
        "revision": target["revision"],
        "content_hash": target["content_hash"],
    }
    strategy_digest = "a" * 64

    prefix = coordinator.transition(
        run_id,
        event="alignment_projection_ready",
        actor="coordinator",
        expected_revision=coordinator.status(run_id)["revision"],
        payload={"strategy_digest": strategy_digest, "handoff_ref": handoff_ref},
    )
    if committed_prefix == "autonomous_research":
        prefix = coordinator.transition(
            run_id,
            event="handoff_confirmed",
            actor="human",
            expected_revision=prefix["revision"],
            payload={"displayed_digest": strategy_digest, "handoff_ref": handoff_ref},
        )

    initialized = coordinator.initialize_from_alignment(
        run_id,
        handoff_ref=handoff_ref,
        blueprint_target_ref=target_ref,
        expected_revision=prefix["revision"],
    )

    assert initialized["lifecycle_state"] == "autonomous_research"
    event_types = [event["event_type"] for event in coordinator.events(run_id)]
    assert event_types.count("alignment_projection_ready") == 1
    assert event_types.count("handoff_confirmed") == 1
    assert event_types.count("blueprint_target_bound") == 1


def test_initialization_rejects_missing_confirmation_without_mutation(tmp_path: Path) -> None:
    coordinator, state, handoff, target = _confirmed_initialization_fixture(tmp_path, include_confirmation=False)
    before = coordinator.status(state["run_id"])
    with pytest.raises(coordinator.error_type) as error:
        coordinator.initialize_from_alignment(
            state["run_id"],
            handoff_ref={"run_id": state["run_id"], "artifact_id": handoff["id"], "revision": handoff["revision"], "content_hash": handoff["content_hash"]},
            blueprint_target_ref={"run_id": state["run_id"], "artifact_id": target["id"], "revision": target["revision"], "content_hash": target["content_hash"]},
            expected_revision=before["revision"],
        )
    assert error.value.code == "handoff_confirmation_invalid"
    assert coordinator.status(state["run_id"]) == before


def test_initialization_rejects_blueprint_without_handoff_parent(tmp_path: Path) -> None:
    coordinator, state, handoff, target = _confirmed_initialization_fixture(tmp_path, include_handoff_parent=False)
    before = coordinator.status(state["run_id"])
    with pytest.raises(coordinator.error_type) as error:
        coordinator.initialize_from_alignment(
            state["run_id"],
            handoff_ref={"run_id": state["run_id"], "artifact_id": handoff["id"], "revision": handoff["revision"], "content_hash": handoff["content_hash"]},
            blueprint_target_ref={"run_id": state["run_id"], "artifact_id": target["id"], "revision": target["revision"], "content_hash": target["content_hash"]},
            expected_revision=before["revision"],
        )
    assert error.value.code == "blueprint_lineage_invalid"
    assert coordinator.status(state["run_id"]) == before


def test_run_init_cli_consumes_exact_persisted_refs(tmp_path: Path, capsys) -> None:
    from research_tree.cli import main

    coordinator, state, handoff, target = _confirmed_initialization_fixture(tmp_path)
    handoff_path = tmp_path / "handoff-ref.json"
    target_path = tmp_path / "blueprint-ref.json"
    handoff_path.write_text(
        json.dumps({"run_id": state["run_id"], "artifact_id": handoff["id"], "revision": handoff["revision"], "content_hash": handoff["content_hash"]}),
        encoding="utf-8",
    )
    target_path.write_text(
        json.dumps({"run_id": state["run_id"], "artifact_id": target["id"], "revision": target["revision"], "content_hash": target["content_hash"]}),
        encoding="utf-8",
    )

    assert main([
        "run",
        "init",
        "--workspace",
        str(tmp_path),
        "--run-id",
        state["run_id"],
        "--handoff-ref",
        str(handoff_path),
        "--blueprint-target-ref",
        str(target_path),
        "--expected-revision",
        str(coordinator.status(state["run_id"])["revision"]),
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["lifecycle_state"] == "autonomous_research"


def _dispatchable_work_item(coordinator, state, target):
    from research_tree.sqlite_ledger import SQLiteRunLedger
    from research_tree.worker_contracts import CanonicalWorkItem

    run_id = state["run_id"]
    target_ref = {
        "run_id": run_id,
        "artifact_id": target["id"],
        "revision": target["revision"],
        "content_hash": target["content_hash"],
    }
    work = CanonicalWorkItem.create(
        work_item_id="work-dispatch",
        slot_id="slot-p0",
        action_kind="deep_dive",
        objective="Resolve the architecture decision.",
        inputs=("blueprint-target:blueprint-target@1",),
        method="repository-analysis",
        expected_output="A schema-valid Finding Pack.",
        success_oracle="The Finding Pack has exact evidence and target lineage.",
        permission_profile="research-read-only",
        completion_evidence=("finding-pack",),
    )
    ledger = SQLiteRunLedger(coordinator.database.parents[1])
    artifact = ledger.append_artifact(
        run_id=run_id,
        artifact_id=work.work_item_id,
        kind="work-item",
        payload=work.to_dict(),
        actor_kind="coordinator",
        actor_id="scheduler",
        status="pending",
        parent_refs=[
            {
                "run_id": run_id,
                "artifact_id": target["id"],
                "revision": target["revision"],
            }
        ],
        expected_run_revision=coordinator.status(run_id)["revision"],
    )
    return {
        "run_id": run_id,
        "artifact_id": artifact["id"],
        "revision": artifact["revision"],
        "content_hash": artifact["content_hash"],
    }, target_ref


def test_dispatch_commits_exact_work_lease_revision_and_event_once(tmp_path: Path) -> None:
    coordinator, state, handoff, target = _confirmed_initialization_fixture(tmp_path)
    initialized = coordinator.initialize_from_alignment(
        state["run_id"],
        handoff_ref={"run_id": state["run_id"], "artifact_id": handoff["id"], "revision": handoff["revision"], "content_hash": handoff["content_hash"]},
        blueprint_target_ref={"run_id": state["run_id"], "artifact_id": target["id"], "revision": target["revision"], "content_hash": target["content_hash"]},
        expected_revision=coordinator.status(state["run_id"])["revision"],
    )
    work_ref, target_ref = _dispatchable_work_item(coordinator, initialized, target)
    before = coordinator.status(state["run_id"])

    dispatched = coordinator.dispatch_action(
        state["run_id"],
        stage_id="dispatch-work-dispatch-1",
        work_item_ref=work_ref,
        blueprint_target_ref=target_ref,
        attempt_id="attempt-work-dispatch-1",
        owner="worker-a",
        started_at="2026-08-06T00:00:00Z",
        lease_expires_at="2026-08-06T00:15:00Z",
        expected_revision=before["revision"],
    )

    assert dispatched["run"]["revision"] == before["revision"] + 1
    assert dispatched["attempt"]["work_item_id"] == "work-dispatch"
    assert dispatched["attempt"]["status"] == "leased"
    assert dispatched["work_item_ref"] == work_ref
    assert coordinator.attempts(state["run_id"])["attempt-work-dispatch-1"] == dispatched["attempt"]
    assert coordinator.events(state["run_id"])[-1]["event_type"] == "action_dispatched"

    events = coordinator.events(state["run_id"])
    repeated = coordinator.dispatch_action(
        state["run_id"],
        stage_id="dispatch-work-dispatch-1",
        work_item_ref=work_ref,
        blueprint_target_ref=target_ref,
        attempt_id="attempt-work-dispatch-1",
        owner="worker-a",
        started_at="2026-08-06T00:00:00Z",
        lease_expires_at="2026-08-06T00:15:00Z",
        expected_revision=before["revision"],
    )
    assert repeated == dispatched
    assert coordinator.events(state["run_id"]) == events

    with pytest.raises(coordinator.error_type) as conflict:
        coordinator.dispatch_action(
            state["run_id"],
            stage_id="dispatch-work-dispatch-1",
            work_item_ref=work_ref,
            blueprint_target_ref=target_ref,
            attempt_id="attempt-work-dispatch-2",
            owner="worker-b",
            started_at="2026-08-06T00:00:00Z",
            lease_expires_at="2026-08-06T00:15:00Z",
            expected_revision=before["revision"],
        )
    assert conflict.value.code == "idempotency_conflict"
    assert coordinator.events(state["run_id"]) == events


def test_dispatch_fault_rolls_back_attempt_revision_and_stage_identity(tmp_path: Path) -> None:
    from research_tree.coordinator import ResearchRunCoordinator

    coordinator, state, handoff, target = _confirmed_initialization_fixture(tmp_path)
    initialized = coordinator.initialize_from_alignment(
        state["run_id"],
        handoff_ref={"run_id": state["run_id"], "artifact_id": handoff["id"], "revision": handoff["revision"], "content_hash": handoff["content_hash"]},
        blueprint_target_ref={"run_id": state["run_id"], "artifact_id": target["id"], "revision": target["revision"], "content_hash": target["content_hash"]},
        expected_revision=coordinator.status(state["run_id"])["revision"],
    )
    work_ref, target_ref = _dispatchable_work_item(coordinator, initialized, target)
    before = coordinator.status(state["run_id"])
    before_events = coordinator.events(state["run_id"])

    def fail(boundary: str) -> None:
        if boundary == "dispatch_after_attempt":
            raise RuntimeError(boundary)

    failing = ResearchRunCoordinator(tmp_path, fault_injector=fail)
    with pytest.raises(RuntimeError, match="dispatch_after_attempt"):
        failing.dispatch_action(
            state["run_id"],
            stage_id="dispatch-work-dispatch-fault",
            work_item_ref=work_ref,
            blueprint_target_ref=target_ref,
            attempt_id="attempt-work-dispatch-fault",
            owner="worker-a",
            started_at="2026-08-06T00:00:00Z",
            lease_expires_at="2026-08-06T00:15:00Z",
            expected_revision=before["revision"],
        )

    reopened = ResearchRunCoordinator(tmp_path)
    assert reopened.status(state["run_id"]) == before
    assert reopened.events(state["run_id"]) == before_events
    assert "attempt-work-dispatch-fault" not in reopened.attempts(state["run_id"])
    committed = reopened.dispatch_action(
        state["run_id"],
        stage_id="dispatch-work-dispatch-fault",
        work_item_ref=work_ref,
        blueprint_target_ref=target_ref,
        attempt_id="attempt-work-dispatch-fault",
        owner="worker-a",
        started_at="2026-08-06T00:00:00Z",
        lease_expires_at="2026-08-06T00:15:00Z",
        expected_revision=before["revision"],
    )
    assert committed["run"]["revision"] == before["revision"] + 1


def _finding_payload(coordinator, run_id: str, work_ref, target_ref):
    from research_tree.evidence import provenance_group_for
    from research_tree.sqlite_ledger import SQLiteRunLedger

    ledger = SQLiteRunLedger(coordinator.database.parents[1])
    evidence = ledger.append_artifact(
        run_id=run_id,
        artifact_id="evidence-dispatch",
        kind="evidence-artifact",
        payload={
            "evidence_id": "evidence-dispatch",
            "run_id": run_id,
            "revision": 1,
            "media_type": "text/plain",
            "locator": {"kind": "source", "ref": "fixture:dispatch"},
            "content_digest": "e" * 64,
            "size_bytes": 8,
            "acquired_at": "2026-08-06T00:01:00Z",
            "acquisition_method": "fixture",
            "provenance_origin": "fixture:dispatch",
            "provenance_group": provenance_group_for("fixture:dispatch", "fixture"),
            "source_revision": None,
            "applicability": "The active Blueprint Target.",
            "confidence": "high",
            "limitations": [],
            "license_note": None,
            "extractor_version": "fixture-1",
            "status": "active",
        },
        actor_kind="worker",
        actor_id="worker-a",
        status="active",
        expected_run_revision=coordinator.status(run_id)["revision"],
    )
    payload = {
        "finding_id": "finding-dispatch",
        "run_id": run_id,
        "attempt_id": "attempt-work-dispatch-1",
        "work_item_ref": work_ref,
        "blueprint_target_ref": target_ref,
        "decision_slot_id": "slot-p0",
        "observations": [
            {
                "observation_id": "observation-dispatch",
                "class": "fact",
                "claim": "The runtime boundary exists.",
                "anchors": [
                    {
                        "artifact_digest": "e" * 64,
                        "artifact_revision": evidence["revision"],
                        "selector_type": "fragment",
                        "selector_value": {"fragment": "boundary"},
                        "extractor_version": "fixture-1",
                        "applicability": "The active Blueprint Target.",
                        "confidence": "high",
                        "limitations": [],
                    }
                ],
                "assumptions": [],
                "consequence": None,
                "reversal_condition": None,
                "unknown_reason": None,
                "next_acquisition_method": None,
                "confidence": "high",
                "limitations": [],
            }
        ],
        "option_effects": [
            {
                "option": "a",
                "effect": "supports",
                "observation_ids": ["observation-dispatch"],
            }
        ],
        "implementation_implications": ["Keep the runtime boundary."],
        "remaining_uncertainties": [],
        "research_continuations": [],
        "oracle_run_refs": [],
    }
    return payload, evidence


def _initialized_dispatch(tmp_path: Path):
    coordinator, state, handoff, target = _confirmed_initialization_fixture(tmp_path)
    initialized = coordinator.initialize_from_alignment(
        state["run_id"],
        handoff_ref={"run_id": state["run_id"], "artifact_id": handoff["id"], "revision": handoff["revision"], "content_hash": handoff["content_hash"]},
        blueprint_target_ref={"run_id": state["run_id"], "artifact_id": target["id"], "revision": target["revision"], "content_hash": target["content_hash"]},
        expected_revision=coordinator.status(state["run_id"])["revision"],
    )
    work_ref, target_ref = _dispatchable_work_item(coordinator, initialized, target)
    dispatched = coordinator.dispatch_action(
        state["run_id"],
        stage_id="dispatch-work-dispatch-ingest",
        work_item_ref=work_ref,
        blueprint_target_ref=target_ref,
        attempt_id="attempt-work-dispatch-1",
        owner="worker-a",
        started_at="2026-08-06T00:00:00Z",
        lease_expires_at="2026-08-06T00:15:00Z",
        expected_revision=coordinator.status(state["run_id"])["revision"],
    )
    payload, evidence = _finding_payload(
        coordinator, state["run_id"], work_ref, target_ref
    )
    return coordinator, state["run_id"], dispatched, payload, evidence


def test_ingest_finding_pack_commits_exact_lineage_and_attempt_disposition(
    tmp_path: Path,
) -> None:
    from research_tree.sqlite_ledger import SQLiteRunLedger

    coordinator, run_id, _dispatched, payload, evidence = _initialized_dispatch(tmp_path)
    before = coordinator.status(run_id)
    ingested = coordinator.ingest_finding_pack(
        run_id,
        stage_id="ingest-finding-dispatch",
        finding_pack=payload,
        expected_revision=before["revision"],
    )

    assert ingested["run"]["revision"] == before["revision"] + 1
    assert ingested["attempt"]["status"] == "submitted"
    assert coordinator.events(run_id)[-1]["event_type"] == "finding_ingested"
    stored = SQLiteRunLedger(tmp_path).resolve(
        run_id,
        ingested["finding_pack_ref"]["artifact_id"],
        ingested["finding_pack_ref"]["revision"],
    )
    parent_ids = {parent["artifact_id"] for parent in stored["parent_refs"]}
    assert parent_ids == {"work-dispatch", "blueprint-target", evidence["id"]}
    assert stored["content_hash"] == ingested["finding_pack_ref"]["content_hash"]

    events = coordinator.events(run_id)
    repeated = coordinator.ingest_finding_pack(
        run_id,
        stage_id="ingest-finding-dispatch",
        finding_pack=payload,
        expected_revision=before["revision"],
    )
    assert repeated == ingested
    assert coordinator.events(run_id) == events


def test_ingest_rejects_unresolved_anchor_and_rolls_back_faulted_artifact(
    tmp_path: Path,
) -> None:
    from copy import deepcopy
    from research_tree.coordinator import ResearchRunCoordinator
    from research_tree.sqlite_ledger import SQLiteLedgerError, SQLiteRunLedger

    coordinator, run_id, _dispatched, payload, _evidence = _initialized_dispatch(tmp_path)
    before = coordinator.status(run_id)
    before_events = coordinator.events(run_id)
    invalid = deepcopy(payload)
    invalid["finding_id"] = "finding-invalid-anchor"
    invalid["observations"][0]["anchors"][0]["artifact_digest"] = "f" * 64
    with pytest.raises(coordinator.error_type) as unresolved:
        coordinator.ingest_finding_pack(
            run_id,
            stage_id="ingest-invalid-anchor",
            finding_pack=invalid,
            expected_revision=before["revision"],
        )
    assert unresolved.value.code == "evidence_anchor_unresolved"
    assert coordinator.status(run_id) == before
    assert coordinator.events(run_id) == before_events

    def fail(boundary: str) -> None:
        if boundary == "ingest_after_artifact":
            raise RuntimeError(boundary)

    failing = ResearchRunCoordinator(tmp_path, fault_injector=fail)
    with pytest.raises(RuntimeError, match="ingest_after_artifact"):
        failing.ingest_finding_pack(
            run_id,
            stage_id="ingest-fault",
            finding_pack=payload,
            expected_revision=before["revision"],
        )
    reopened = ResearchRunCoordinator(tmp_path)
    assert reopened.status(run_id) == before
    assert reopened.events(run_id) == before_events
    with pytest.raises(SQLiteLedgerError, match="does not exist"):
        SQLiteRunLedger(tmp_path).resolve(run_id, payload["finding_id"], 1)


def test_ingest_uses_the_schema_identifier_contract_for_nested_ids(tmp_path: Path) -> None:
    from copy import deepcopy

    coordinator, run_id, _dispatched, payload, _evidence = _initialized_dispatch(tmp_path)
    invalid = deepcopy(payload)
    invalid["observations"][0]["observation_id"] = "INVALID_OBSERVATION"
    invalid["option_effects"][0]["observation_ids"] = ["INVALID_OBSERVATION"]

    with pytest.raises(coordinator.error_type) as rejected:
        coordinator.ingest_finding_pack(
            run_id,
            stage_id="ingest-invalid-observation-id",
            finding_pack=invalid,
            expected_revision=coordinator.status(run_id)["revision"],
        )

    assert rejected.value.code == "finding_pack_invalid"


def _ingested_finding(tmp_path: Path):
    coordinator, run_id, _dispatched, payload, _evidence = _initialized_dispatch(tmp_path)
    ingested = coordinator.ingest_finding_pack(
        run_id,
        stage_id="ingest-for-synthesis",
        finding_pack=payload,
        expected_revision=coordinator.status(run_id)["revision"],
    )
    return coordinator, run_id, ingested


def test_synthesis_commits_digest_obligation_state_and_event_once(tmp_path: Path) -> None:
    from research_tree.sqlite_ledger import SQLiteRunLedger

    coordinator, run_id, ingested = _ingested_finding(tmp_path)
    before = coordinator.status(run_id)
    synthesized = coordinator.synthesize_findings(
        run_id,
        stage_id="synthesize-batch-1",
        finding_pack_refs=[ingested["finding_pack_ref"]],
        digest_id="insight-batch-1",
        producer_version="insight-v1",
        expected_revision=before["revision"],
    )

    assert synthesized["run"]["revision"] == before["revision"] + 1
    assert synthesized["run"]["lifecycle_state"] == "synthesis"
    assert synthesized["insight_digest"]["gaps"] == []
    assert synthesized["insight_digest"]["contradictions"] == []
    insight_obligation = coordinator.obligations(run_id)["insight_clear"]
    assert insight_obligation["satisfied"] is True
    assert insight_obligation["evidence_ref"] == synthesized["insight_digest_ref"][
        "content_hash"
    ]
    stored = SQLiteRunLedger(tmp_path).resolve(
        run_id,
        synthesized["insight_digest_ref"]["artifact_id"],
        synthesized["insight_digest_ref"]["revision"],
    )
    assert stored["payload"] == synthesized["insight_digest"]
    assert stored["parent_refs"] == [
        {
            "run_id": run_id,
            "artifact_id": ingested["finding_pack_ref"]["artifact_id"],
            "revision": ingested["finding_pack_ref"]["revision"],
        }
    ]
    assert coordinator.events(run_id)[-1]["event_type"] == "batch_checkpoint"

    events = coordinator.events(run_id)
    repeated = coordinator.synthesize_findings(
        run_id,
        stage_id="synthesize-batch-1",
        finding_pack_refs=[ingested["finding_pack_ref"]],
        digest_id="insight-batch-1",
        producer_version="insight-v1",
        expected_revision=before["revision"],
    )
    assert repeated == synthesized
    assert coordinator.events(run_id) == events


def test_synthesis_fault_rolls_back_digest_obligation_and_transition(tmp_path: Path) -> None:
    from research_tree.coordinator import ResearchRunCoordinator
    from research_tree.sqlite_ledger import SQLiteLedgerError, SQLiteRunLedger

    coordinator, run_id, ingested = _ingested_finding(tmp_path)
    before = coordinator.status(run_id)
    before_events = coordinator.events(run_id)
    before_obligation = coordinator.obligations(run_id)["insight_clear"]

    def fail(boundary: str) -> None:
        if boundary == "synthesize_after_obligation":
            raise RuntimeError(boundary)

    failing = ResearchRunCoordinator(tmp_path, fault_injector=fail)
    with pytest.raises(RuntimeError, match="synthesize_after_obligation"):
        failing.synthesize_findings(
            run_id,
            stage_id="synthesize-fault",
            finding_pack_refs=[ingested["finding_pack_ref"]],
            digest_id="insight-fault",
            producer_version="insight-v1",
            expected_revision=before["revision"],
        )

    reopened = ResearchRunCoordinator(tmp_path)
    assert reopened.status(run_id) == before
    assert reopened.events(run_id) == before_events
    assert reopened.obligations(run_id)["insight_clear"] == before_obligation
    with pytest.raises(SQLiteLedgerError, match="does not exist"):
        SQLiteRunLedger(tmp_path).resolve(run_id, "insight-fault", 1)


def test_synthesis_rejects_checkpoint_while_attempt_is_still_running(
    tmp_path: Path,
) -> None:
    coordinator, run_id, _dispatched, _payload, _evidence = _initialized_dispatch(
        tmp_path
    )
    before = coordinator.status(run_id)

    with pytest.raises(coordinator.error_type) as rejected:
        coordinator.synthesize_findings(
            run_id,
            stage_id="synthesize-premature",
            finding_pack_refs=[],
            digest_id="insight-premature",
            producer_version="insight-v1",
            expected_revision=before["revision"],
        )

    assert rejected.value.code == "batch_incomplete"
    assert coordinator.status(run_id) == before


def test_synthesis_persists_an_uncovered_slot_as_blocking(tmp_path: Path) -> None:
    coordinator, state, handoff, target = _confirmed_initialization_fixture(tmp_path)
    run_id = state["run_id"]
    coordinator.initialize_from_alignment(
        run_id,
        handoff_ref={
            "run_id": run_id,
            "artifact_id": handoff["id"],
            "revision": handoff["revision"],
            "content_hash": handoff["content_hash"],
        },
        blueprint_target_ref={
            "run_id": run_id,
            "artifact_id": target["id"],
            "revision": target["revision"],
            "content_hash": target["content_hash"],
        },
        expected_revision=coordinator.status(run_id)["revision"],
    )

    synthesized = coordinator.synthesize_findings(
        run_id,
        stage_id="synthesize-uncovered",
        finding_pack_refs=[],
        digest_id="insight-uncovered",
        producer_version="insight-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )

    assert synthesized["insight_clear"] is False
    assert synthesized["insight_digest"]["gaps"] == [
        {
            "slot_id": "slot-p0",
            "reason": "No accepted Finding Pack covers this active Decision Slot.",
            "next_acquisition_method": "landscape",
        }
    ]
    obligation = coordinator.obligations(run_id)["insight_clear"]
    assert obligation["satisfied"] is False
    assert obligation["evidence_ref"] == synthesized["insight_digest_ref"][
        "content_hash"
    ]


def test_synthesis_requires_and_preserves_previous_digest_lineage(tmp_path: Path) -> None:
    from research_tree.sqlite_ledger import SQLiteRunLedger

    coordinator, run_id, ingested = _ingested_finding(tmp_path)
    first = coordinator.synthesize_findings(
        run_id,
        stage_id="synthesize-lineage-1",
        finding_pack_refs=[ingested["finding_pack_ref"]],
        digest_id="insight-lineage-1",
        producer_version="insight-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )
    resumed = coordinator.transition(
        run_id,
        event="closure_deficit",
        actor="coordinator",
        expected_revision=first["run"]["revision"],
        payload={"reason": "Recompute with an explicit predecessor."},
    )
    before_rejected = coordinator.status(run_id)

    with pytest.raises(coordinator.error_type) as missing_previous:
        coordinator.synthesize_findings(
            run_id,
            stage_id="synthesize-lineage-missing",
            finding_pack_refs=[ingested["finding_pack_ref"]],
            digest_id="insight-lineage-missing",
            producer_version="insight-v1",
            expected_revision=resumed["revision"],
        )
    assert missing_previous.value.code == "previous_digest_required"
    assert coordinator.status(run_id) == before_rejected

    second = coordinator.synthesize_findings(
        run_id,
        stage_id="synthesize-lineage-2",
        finding_pack_refs=[ingested["finding_pack_ref"]],
        digest_id="insight-lineage-2",
        producer_version="insight-v1",
        previous_digest_ref=first["insight_digest_ref"],
        expected_revision=resumed["revision"],
    )

    assert second["insight_digest"]["previous_digest_ref"] == (
        "insight-digest:insight-lineage-1@1#"
        + first["insight_digest_ref"]["content_hash"]
    )
    stored = SQLiteRunLedger(tmp_path).resolve(run_id, "insight-lineage-2", 1)
    assert {parent["artifact_id"] for parent in stored["parent_refs"]} == {
        "finding-dispatch",
        "insight-lineage-1",
    }
    original = SQLiteRunLedger(tmp_path).resolve(run_id, "insight-lineage-1", 1)
    assert original["content_hash"] == first["insight_digest_ref"]["content_hash"]


def _decision_entry_for(ingested, synthesized, target_ref):
    finding_ref = ingested["finding_pack_ref"]
    return {
        "decision_id": "decision-slot-p0",
        "run_id": finding_ref["run_id"],
        "blueprint_target_ref": target_ref,
        "decision_slot_id": "slot-p0",
        "finding_pack_refs": [finding_ref],
        "insight_digest_ref": synthesized["insight_digest_ref"],
        "status": "selected",
        "selected_option": "a",
        "alternatives": [
            {
                "option": "b",
                "disposition": "rejected",
                "reason": "The accepted observation supports option A instead.",
            }
        ],
        "evidence_basis": [
            {
                "finding_pack_ref": finding_ref,
                "observation_ids": ["observation-dispatch"],
            }
        ],
        "rationale": "The accepted Finding Pack supports option A.",
        "design_consequence": "Keep the canonical runtime boundary.",
        "repository_touchpoints": [],
        "validation": {
            "oracle_run_refs": [],
            "status": "pending",
            "limitations": ["The required oracle remains pending."],
        },
        "change_tasks": [],
        "assumptions": [],
        "fallback": "Block the transition and retain the current boundary.",
        "reversal_condition": "Independent evidence contradicts option A.",
        "revision_reason": "Initial evidence-backed decision.",
        "previous_decision_ref": None,
        "producer_version": "decision-v1",
        "limitations": ["The required oracle remains pending."],
    }


def test_convergence_commits_decision_record_deficit_and_event_once(tmp_path: Path) -> None:
    from research_tree.sqlite_ledger import SQLiteRunLedger

    coordinator, run_id, ingested = _ingested_finding(tmp_path)
    synthesized = coordinator.synthesize_findings(
        run_id,
        stage_id="synthesize-for-convergence",
        finding_pack_refs=[ingested["finding_pack_ref"]],
        digest_id="insight-for-convergence",
        producer_version="insight-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )
    finding_artifact = SQLiteRunLedger(tmp_path).resolve(
        run_id,
        ingested["finding_pack_ref"]["artifact_id"],
        ingested["finding_pack_ref"]["revision"],
    )
    decision = _decision_entry_for(
        ingested, synthesized, finding_artifact["payload"]["blueprint_target_ref"]
    )
    before = coordinator.status(run_id)

    converged = coordinator.converge_decisions(
        run_id,
        stage_id="converge-batch-1",
        convergence_id="convergence-batch-1",
        insight_digest_ref=synthesized["insight_digest_ref"],
        decision_entries=[decision],
        producer_version="convergence-v1",
        expected_revision=before["revision"],
    )

    assert converged["run"]["revision"] == before["revision"] + 1
    assert converged["run"]["lifecycle_state"] == "autonomous_research"
    assert converged["convergence_record"]["outcome"] == "closure_deficit"
    assert any(
        item["slot_id"] == "slot-p0" and item["kind"] == "closure_missing"
        for item in converged["convergence_record"]["deficits"]
    )
    ledger = SQLiteRunLedger(tmp_path)
    decision_artifact = ledger.resolve(run_id, "decision-slot-p0", 1)
    convergence_artifact = ledger.resolve(run_id, "convergence-batch-1", 1)
    assert decision_artifact["payload"] == decision
    assert convergence_artifact["payload"] == converged["convergence_record"]
    assert coordinator.events(run_id)[-1]["event_type"] == "closure_deficit"

    events = coordinator.events(run_id)
    repeated = coordinator.converge_decisions(
        run_id,
        stage_id="converge-batch-1",
        convergence_id="convergence-batch-1",
        insight_digest_ref=synthesized["insight_digest_ref"],
        decision_entries=[decision],
        producer_version="convergence-v1",
        expected_revision=before["revision"],
    )
    assert repeated == converged
    assert coordinator.events(run_id) == events


def test_convergence_fault_rolls_back_decisions_record_and_transition(tmp_path: Path) -> None:
    from research_tree.coordinator import ResearchRunCoordinator
    from research_tree.sqlite_ledger import SQLiteLedgerError, SQLiteRunLedger

    coordinator, run_id, ingested = _ingested_finding(tmp_path)
    synthesized = coordinator.synthesize_findings(
        run_id,
        stage_id="synthesize-for-convergence-fault",
        finding_pack_refs=[ingested["finding_pack_ref"]],
        digest_id="insight-for-convergence-fault",
        producer_version="insight-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )
    finding_artifact = SQLiteRunLedger(tmp_path).resolve(
        run_id,
        ingested["finding_pack_ref"]["artifact_id"],
        ingested["finding_pack_ref"]["revision"],
    )
    decision = _decision_entry_for(
        ingested, synthesized, finding_artifact["payload"]["blueprint_target_ref"]
    )
    decision["decision_id"] = "decision-convergence-fault"
    before = coordinator.status(run_id)
    before_events = coordinator.events(run_id)

    def fail(boundary: str) -> None:
        if boundary == "converge_after_decisions":
            raise RuntimeError(boundary)

    failing = ResearchRunCoordinator(tmp_path, fault_injector=fail)
    with pytest.raises(RuntimeError, match="converge_after_decisions"):
        failing.converge_decisions(
            run_id,
            stage_id="converge-fault",
            convergence_id="convergence-fault",
            insight_digest_ref=synthesized["insight_digest_ref"],
            decision_entries=[decision],
            producer_version="convergence-v1",
            expected_revision=before["revision"],
        )

    reopened = ResearchRunCoordinator(tmp_path)
    assert reopened.status(run_id) == before
    assert reopened.events(run_id) == before_events
    with pytest.raises(SQLiteLedgerError, match="does not exist"):
        SQLiteRunLedger(tmp_path).resolve(run_id, "decision-convergence-fault", 1)
    with pytest.raises(SQLiteLedgerError, match="does not exist"):
        SQLiteRunLedger(tmp_path).resolve(run_id, "convergence-fault", 1)


def _persist_oracle_for_convergence(coordinator, tmp_path: Path, run_id: str):
    from research_tree import OracleAttempt, OracleRun, OracleSpec, SQLiteRunLedger
    from research_tree.contracts import canonical_json_bytes

    spec = OracleSpec.create(
        "oracle-1",
        "integration-test",
        "integration-test",
        expected="The canonical boundary passes integration validation.",
    )
    coordinator.record_oracle_spec(
        run_id, spec, expected_revision=coordinator.status(run_id)["revision"]
    )
    spec_digest = coordinator.oracle_specs(run_id)["oracle-1@1"]["contract_digest"]
    attempt = OracleAttempt.from_mapping(
        {
            "oracle_attempt_id": "oracle-attempt-convergence",
            "run_id": run_id,
            "action_attempt_id": "attempt-work-dispatch-1",
            "oracle_spec_id": "oracle-1",
            "oracle_spec_version": 1,
            "oracle_spec_digest": spec_digest,
            "method": "integration-test",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64,
            "started_at": "2026-08-06T01:00:00+00:00",
        }
    )
    coordinator.record_oracle_attempt(
        run_id,
        attempt,
        expected_revision=coordinator.status(run_id)["revision"],
    )
    ledger = SQLiteRunLedger(tmp_path)
    result_artifact = ledger.append_artifact(
        run_id=run_id,
        artifact_id="oracle-result-convergence",
        kind="oracle-result",
        payload={"status": "passed"},
        actor_kind="oracle",
        actor_id="core-v1",
        status="active",
        expected_run_revision=coordinator.status(run_id)["revision"],
    )
    oracle = OracleRun.from_mapping(
        {
            "oracle_run_id": "oracle-run-convergence",
            "oracle_attempt_id": attempt.oracle_attempt_id,
            "oracle_spec_id": "oracle-1",
            "oracle_spec_version": 1,
            "attempt_id": "attempt-work-dispatch-1",
            "method": "integration-test",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64,
            "tool_event_refs": [],
            "verdict": "passed",
            "exit_code": 0,
            "timed_out": False,
            "result_artifact_refs": [
                {
                    "run_id": run_id,
                    "artifact_id": result_artifact["id"],
                    "revision": result_artifact["revision"],
                    "content_hash": result_artifact["content_hash"],
                }
            ],
            "evaluator": "core-v1",
            "limitations": [],
            "reproducibility_status": "reproducible",
        }
    )
    coordinator.record_oracle_run(
        run_id,
        oracle,
        expected_revision=coordinator.status(run_id)["revision"],
    )
    payload = oracle.to_contract_dict()
    payload_digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return oracle, payload_digest


def _run_at_readiness(tmp_path: Path):
    from research_tree import SlotClosureAssessment
    from research_tree.sqlite_ledger import SQLiteRunLedger

    coordinator, run_id, ingested = _ingested_finding(tmp_path)
    first_insight = coordinator.synthesize_findings(
        run_id,
        stage_id="synthesize-before-closure",
        finding_pack_refs=[ingested["finding_pack_ref"]],
        digest_id="insight-before-closure",
        producer_version="insight-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )
    oracle, oracle_digest = _persist_oracle_for_convergence(
        coordinator, tmp_path, run_id
    )
    finding_artifact = SQLiteRunLedger(tmp_path).resolve(
        run_id,
        ingested["finding_pack_ref"]["artifact_id"],
        ingested["finding_pack_ref"]["revision"],
    )
    decision = _decision_entry_for(
        ingested,
        first_insight,
        finding_artifact["payload"]["blueprint_target_ref"],
    )
    decision["validation"] = {
        "oracle_run_refs": [
            {
                "oracle_run_id": oracle.oracle_run_id,
                "payload_digest": oracle_digest,
            }
        ],
        "status": "passed",
        "limitations": [],
    }
    decision["limitations"] = []
    first_convergence = coordinator.converge_decisions(
        run_id,
        stage_id="converge-before-closure",
        convergence_id="convergence-before-closure",
        insight_digest_ref=first_insight["insight_digest_ref"],
        decision_entries=[decision],
        producer_version="convergence-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )
    assert first_convergence["run"]["lifecycle_state"] == "autonomous_research"

    decision_ref = first_convergence["decision_refs"][0]
    assessment = SlotClosureAssessment.assess_alpha2(
        slot_id="slot-p0",
        assessment_revision=1,
        decision_ref=decision_ref,
        decision_status="selected",
        evidence=[
            {
                "evidence_id": "evidence-a",
                "provenance_group": "source-a",
                "classes": ["repository"],
            },
            {
                "evidence_id": "evidence-b",
                "provenance_group": "source-b",
                "classes": ["repository"],
            },
        ],
        oracle_runs=[oracle.to_contract_dict()],
        contradictions=[],
        required_classes=["repository"],
        counterevidence_search={"completed": True},
        fallback=decision["fallback"],
        reversal_condition=decision["reversal_condition"],
        assessor_version="core-v1",
    )
    assert assessment.status == "passed"
    coordinator.record_closure_assessment(
        run_id,
        assessment,
        expected_revision=coordinator.status(run_id)["revision"],
    )
    assert coordinator.obligations(run_id)["p0_closure"]["satisfied"] is True

    second_insight = coordinator.synthesize_findings(
        run_id,
        stage_id="synthesize-after-closure",
        finding_pack_refs=[ingested["finding_pack_ref"]],
        digest_id="insight-after-closure",
        producer_version="insight-v1",
        previous_digest_ref=first_insight["insight_digest_ref"],
        expected_revision=coordinator.status(run_id)["revision"],
    )
    final = coordinator.converge_decisions(
        run_id,
        stage_id="converge-after-closure",
        convergence_id="convergence-after-closure",
        insight_digest_ref=second_insight["insight_digest_ref"],
        decision_entries=[],
        producer_version="convergence-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )

    assert final["run"]["lifecycle_state"] == "readiness"
    assert final["convergence_record"]["outcome"] == "all_slots_closed"
    assert final["convergence_record"]["deficits"] == []
    assert final["convergence_record"]["decision_refs"] == [decision_ref]
    stored_convergence = SQLiteRunLedger(tmp_path).resolve(
        run_id, "convergence-after-closure", 1
    )
    assert decision_ref["artifact_id"] in {
        parent["artifact_id"] for parent in stored_convergence["parent_refs"]
    }
    assert coordinator.events(run_id)[-1]["event_type"] == "all_slots_closed"
    return coordinator, run_id, final


def test_convergence_enters_readiness_only_after_current_p0_closure(tmp_path: Path) -> None:
    _run_at_readiness(tmp_path)


def test_readiness_deficit_is_persisted_and_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    from research_tree.sqlite_ledger import SQLiteRunLedger

    coordinator, run_id, convergence = _run_at_readiness(tmp_path)
    before = coordinator.status(run_id)
    result = coordinator.evaluate_readiness(
        run_id,
        stage_id="readiness-missing-evaluation",
        readiness_id="readiness-missing-evaluation",
        convergence_record_ref=convergence["convergence_record_ref"],
        risk_tier="standard",
        producer_version="readiness-v1",
        expected_revision=before["revision"],
    )

    assert result["run"]["lifecycle_state"] == "autonomous_research"
    assert result["readiness_record"]["status"] == "not_ready"
    assert result["readiness_record"]["deficits"][0]["kind"] == "evaluation_missing"
    assert coordinator.obligations(run_id)["readiness"]["satisfied"] is False
    assert coordinator.events(run_id)[-1]["event_type"] == "readiness_deficit"
    stored = SQLiteRunLedger(tmp_path).resolve(
        run_id, "readiness-missing-evaluation", 1
    )
    parent_ids = {item["artifact_id"] for item in stored["parent_refs"]}
    assert {
        "blueprint-target",
        "convergence-after-closure",
        "insight-after-closure",
        "decision-slot-p0",
    } <= parent_ids

    events = coordinator.events(run_id)
    repeated = coordinator.evaluate_readiness(
        run_id,
        stage_id="readiness-missing-evaluation",
        readiness_id="readiness-missing-evaluation",
        convergence_record_ref=convergence["convergence_record_ref"],
        risk_tier="standard",
        producer_version="readiness-v1",
        expected_revision=before["revision"],
    )
    assert repeated == result
    assert coordinator.events(run_id) == events


def test_readiness_passes_only_with_current_evaluation_obligation(
    tmp_path: Path,
) -> None:
    coordinator, run_id, convergence = _run_at_readiness(tmp_path)
    coordinator.record_obligation(
        run_id,
        "evaluation",
        evidence_ref="evaluation-suite-1",
        expected_revision=coordinator.status(run_id)["revision"],
    )

    result = coordinator.evaluate_readiness(
        run_id,
        stage_id="readiness-passed",
        readiness_id="readiness-passed",
        convergence_record_ref=convergence["convergence_record_ref"],
        risk_tier="standard",
        producer_version="readiness-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )

    assert result["run"]["lifecycle_state"] == "delivery_pending"
    assert result["readiness_record"]["status"] == "ready"
    readiness_obligation = coordinator.obligations(run_id)["readiness"]
    assert readiness_obligation["satisfied"] is True
    assert (
        readiness_obligation["evidence_ref"]
        == result["readiness_record_ref"]["content_hash"]
    )
    assert coordinator.events(run_id)[-1]["event_type"] == "readiness_passed"


def test_readiness_fault_after_artifact_rolls_back_the_stage(tmp_path: Path) -> None:
    from research_tree.coordinator import ResearchRunCoordinator
    from research_tree.sqlite_ledger import SQLiteLedgerError, SQLiteRunLedger

    coordinator, run_id, convergence = _run_at_readiness(tmp_path)
    before = coordinator.status(run_id)
    before_events = coordinator.events(run_id)

    def fail(boundary: str) -> None:
        if boundary == "readiness_after_record":
            raise RuntimeError(boundary)

    failing = ResearchRunCoordinator(tmp_path, fault_injector=fail)
    with pytest.raises(RuntimeError, match="readiness_after_record"):
        failing.evaluate_readiness(
            run_id,
            stage_id="readiness-fault",
            readiness_id="readiness-fault",
            convergence_record_ref=convergence["convergence_record_ref"],
            risk_tier="standard",
            producer_version="readiness-v1",
            expected_revision=before["revision"],
        )

    reopened = ResearchRunCoordinator(tmp_path)
    assert reopened.status(run_id) == before
    assert reopened.events(run_id) == before_events
    assert reopened.obligations(run_id)["readiness"]["satisfied"] is False
    with pytest.raises(SQLiteLedgerError, match="does not exist"):
        SQLiteRunLedger(tmp_path).resolve(run_id, "readiness-fault", 1)


def _run_with_readiness_deficit(tmp_path: Path):
    coordinator, run_id, convergence = _run_at_readiness(tmp_path)
    readiness = coordinator.evaluate_readiness(
        run_id,
        stage_id="readiness-for-successor",
        readiness_id="readiness-for-successor",
        convergence_record_ref=convergence["convergence_record_ref"],
        risk_tier="standard",
        producer_version="readiness-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )
    return coordinator, run_id, readiness


def test_successor_work_is_deterministic_and_bound_to_exact_deficit(
    tmp_path: Path,
) -> None:
    from research_tree.sqlite_ledger import SQLiteLedgerError, SQLiteRunLedger

    coordinator, run_id, readiness = _run_with_readiness_deficit(tmp_path)
    before = coordinator.status(run_id)
    result = coordinator.schedule_successor_work(
        run_id,
        stage_id="successor-readiness-deficit",
        trigger_ref=readiness["readiness_record_ref"],
        permission_profile="research-read-only",
        expected_revision=before["revision"],
    )

    assert result["run"]["lifecycle_state"] == "autonomous_research"
    assert len(result["work_item_refs"]) == 1
    work_ref = result["work_item_refs"][0]
    stored = SQLiteRunLedger(tmp_path).resolve(
        run_id, work_ref["artifact_id"], work_ref["revision"]
    )
    assert stored["payload"]["action_kind"] == "validation"
    assert stored["payload"]["slot_id"] == "readiness"
    assert stored["parent_refs"] == [
        {
            "run_id": run_id,
            "artifact_id": readiness["readiness_record_ref"]["artifact_id"],
            "revision": readiness["readiness_record_ref"]["revision"],
        }
    ]
    assert coordinator.events(run_id)[-1]["event_type"] == "successor_work_created"

    events = coordinator.events(run_id)
    repeated = coordinator.schedule_successor_work(
        run_id,
        stage_id="successor-readiness-deficit",
        trigger_ref=readiness["readiness_record_ref"],
        permission_profile="research-read-only",
        expected_revision=before["revision"],
    )
    assert repeated == result
    assert coordinator.events(run_id) == events
    with pytest.raises(SQLiteLedgerError, match="does not exist"):
        SQLiteRunLedger(tmp_path).resolve(run_id, work_ref["artifact_id"], 2)


def test_successor_work_rejects_a_ready_record_without_mutation(tmp_path: Path) -> None:
    coordinator, run_id, convergence = _run_at_readiness(tmp_path)
    coordinator.record_obligation(
        run_id,
        "evaluation",
        evidence_ref="evaluation-suite-1",
        expected_revision=coordinator.status(run_id)["revision"],
    )
    readiness = coordinator.evaluate_readiness(
        run_id,
        stage_id="readiness-no-deficit",
        readiness_id="readiness-no-deficit",
        convergence_record_ref=convergence["convergence_record_ref"],
        risk_tier="standard",
        producer_version="readiness-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )
    before = coordinator.status(run_id)
    before_events = coordinator.events(run_id)

    with pytest.raises(coordinator.error_type) as rejected:
        coordinator.schedule_successor_work(
            run_id,
            stage_id="successor-without-deficit",
            trigger_ref=readiness["readiness_record_ref"],
            permission_profile="research-read-only",
            expected_revision=before["revision"],
        )

    assert rejected.value.code == "successor_trigger_closed"
    assert coordinator.status(run_id) == before
    assert coordinator.events(run_id) == before_events


def test_successor_work_fault_rolls_back_entire_batch(tmp_path: Path) -> None:
    from research_tree.coordinator import ResearchRunCoordinator
    from research_tree.sqlite_ledger import SQLiteLedgerError, SQLiteRunLedger

    coordinator, run_id, readiness = _run_with_readiness_deficit(tmp_path)
    before = coordinator.status(run_id)
    before_events = coordinator.events(run_id)

    def fail(boundary: str) -> None:
        if boundary == "successor_after_work_items":
            raise RuntimeError(boundary)

    failing = ResearchRunCoordinator(tmp_path, fault_injector=fail)
    with pytest.raises(RuntimeError, match="successor_after_work_items"):
        failing.schedule_successor_work(
            run_id,
            stage_id="successor-fault",
            trigger_ref=readiness["readiness_record_ref"],
            permission_profile="research-read-only",
            expected_revision=before["revision"],
        )

    reopened = ResearchRunCoordinator(tmp_path)
    assert reopened.status(run_id) == before
    assert reopened.events(run_id) == before_events
    work_id = "work-" + hashlib.sha256(
        json.dumps(
            {
                "trigger_ref": readiness["readiness_record_ref"],
                "deficit": readiness["readiness_record"]["deficits"][0],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    with pytest.raises(SQLiteLedgerError, match="does not exist"):
        SQLiteRunLedger(tmp_path).resolve(run_id, work_id, 1)


def test_successor_work_accepts_exact_convergence_deficit(tmp_path: Path) -> None:
    coordinator, run_id, ingested = _ingested_finding(tmp_path)
    insight = coordinator.synthesize_findings(
        run_id,
        stage_id="synthesize-for-successor",
        finding_pack_refs=[ingested["finding_pack_ref"]],
        digest_id="insight-for-successor",
        producer_version="insight-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )
    convergence = coordinator.converge_decisions(
        run_id,
        stage_id="converge-for-successor",
        convergence_id="convergence-for-successor",
        insight_digest_ref=insight["insight_digest_ref"],
        decision_entries=[],
        producer_version="convergence-v1",
        expected_revision=coordinator.status(run_id)["revision"],
    )
    assert convergence["convergence_record"]["outcome"] == "closure_deficit"

    result = coordinator.schedule_successor_work(
        run_id,
        stage_id="successor-convergence-deficit",
        trigger_ref=convergence["convergence_record_ref"],
        permission_profile="research-read-only",
        expected_revision=coordinator.status(run_id)["revision"],
    )

    assert result["work_item_refs"]
    assert all(
        reference["artifact_id"].startswith("work-")
        for reference in result["work_item_refs"]
    )


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
    from research_tree.coordinator import ResearchRunCoordinator

    ResearchRunCoordinator(tmp_path).create("run-cli")
    assert main(["run", "status", "--workspace", str(tmp_path), "--run-id", "run-cli"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["lifecycle_state"] == "alignment"
    assert main(["run", "replay", "--workspace", str(tmp_path), "--run-id", "run-cli"]) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["run_id"] == "run-cli"
    assert replay["events"]
