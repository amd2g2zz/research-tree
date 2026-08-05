from __future__ import annotations

import pytest


def canonical_spec() -> dict[str, object]:
    return {
        "oracle_spec_id": "oracle-build",
        "version": 2,
        "objective": "The repository compiles without errors.",
        "input_schema_digest": "a" * 64,
        "invocation_adapter": "python-compileall",
        "permissions": {"read_roots": ["src"], "write_roots": [], "network": "none", "commands": ["python -m compileall -q src"]},
        "resource_limits": {"cpu_seconds": 60, "memory_bytes": 268435456, "output_bytes": 1048576},
        "timeout_seconds": 60,
        "expected_result_schema_digest": "b" * 64,
        "retry_policy": {"max_attempts": 2, "backoff_seconds": [0], "switch_method_after": 2},
        "flaky_policy": "repeat_once_then_inconclusive",
        "isolation_profile": "read-only-repository",
        "human_only": False,
    }


def canonical_oracle_attempt() -> dict[str, object]:
    return {
        "oracle_attempt_id": "oracle-attempt-1",
        "run_id": "run-oracle",
        "action_attempt_id": "attempt-1",
        "oracle_spec_id": "oracle-build",
        "oracle_spec_version": 2,
        "oracle_spec_digest": "2" * 64,
        "method": "python-compileall",
        "input_digests": ["c" * 64],
        "environment_digest": "d" * 64,
        "toolchain_digest": "e" * 64,
        "started_at": "2026-08-05T00:00:00+00:00",
    }


def decision_ref() -> dict[str, object]:
    return {"run_id": "run-oracle", "artifact_id": "decision-a", "revision": 1, "content_hash": "9" * 64}


def result_artifact_ref(
    *,
    run_id: str = "run-oracle",
    artifact_id: str = "oracle-result",
    revision: int = 1,
    content_hash: str = "8" * 64,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "artifact_id": artifact_id,
        "revision": revision,
        "content_hash": content_hash,
    }


def persist_oracle_boundary(ledger, state):
    from research_tree import AttemptLease, OracleAttempt, OracleSpec

    coordinator = ledger.coordinator
    spec = OracleSpec.create(
        "oracle-build",
        "integration-test",
        "integration-test",
        expected="The integration test passes.",
        version=1,
    )
    state = coordinator.record_oracle_spec(
        "run-oracle", spec, expected_revision=state["revision"]
    )
    state = coordinator.issue_lease(
        AttemptLease.create(
            attempt_id="attempt-1",
            work_item_id="work-1",
            run_id="run-oracle",
            owner="worker-1",
            dispatch_digest="f" * 64,
            started_at="2026-08-05T00:00:00Z",
            lease_expires_at="2026-08-05T01:00:00Z",
        ),
        expected_revision=state["revision"],
    )
    spec_digest = coordinator.oracle_specs("run-oracle")["oracle-build@1"][
        "contract_digest"
    ]
    attempt = OracleAttempt.from_mapping(
        {
            "oracle_attempt_id": "oracle-attempt-1",
            "run_id": "run-oracle",
            "action_attempt_id": "attempt-1",
            "oracle_spec_id": "oracle-build",
            "oracle_spec_version": 1,
            "oracle_spec_digest": spec_digest,
            "method": "integration-test",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64,
            "started_at": "2026-08-05T00:00:00+00:00",
        }
    )
    state = coordinator.record_oracle_attempt(
        "run-oracle", attempt, expected_revision=state["revision"]
    )
    return state, attempt


def bind_blueprint(ledger, slot_ids, *, artifact_revision=0):
    coordinator = ledger.coordinator
    target = ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="blueprint-target",
        kind="blueprint-target",
        payload={
            "slots": [
                {
                    "id": slot_id,
                    "priority": "P0",
                    "status": "open",
                    "fallback": f"Defer {slot_id}.",
                    "reversal_condition": f"New evidence reverses {slot_id}.",
                }
                for slot_id in slot_ids
            ]
        },
        actor_kind="coordinator",
        actor_id="blueprint-compiler",
        status="active",
        expected_revision=artifact_revision,
    )
    state = coordinator.bind_blueprint_target(
        "run-oracle",
        {
            "run_id": "run-oracle",
            "artifact_id": "blueprint-target",
            "revision": target["revision"],
            "content_hash": target["content_hash"],
        },
        expected_revision=coordinator.status("run-oracle")["revision"],
    )
    return state, target


def passing_assessment(slot_id, decision, oracle_run):
    from research_tree import SlotClosureAssessment

    return SlotClosureAssessment.assess_alpha2(
        slot_id=slot_id,
        assessment_revision=1,
        decision_ref={
            "run_id": "run-oracle",
            "artifact_id": decision["id"],
            "revision": decision["revision"],
            "content_hash": decision["content_hash"],
        },
        decision_status="selected",
        evidence=[
            {
                "evidence_id": f"evidence-{slot_id}-repository",
                "provenance_group": "source-a",
                "classes": ["repository"],
            },
            {
                "evidence_id": f"evidence-{slot_id}-experiment",
                "provenance_group": "source-b",
                "classes": ["experiment"],
            },
        ],
        oracle_runs=[oracle_run.to_contract_dict()],
        contradictions=[],
        required_classes=["repository", "experiment"],
        counterevidence_search={"completed": True},
        fallback=f"Defer {slot_id}.",
        reversal_condition=f"New evidence reverses {slot_id}.",
        assessor_version="core-v1",
    )


def test_canonical_oracle_spec_round_trips_exact_execution_boundary() -> None:
    from research_tree import OracleSpec

    spec = OracleSpec.from_mapping(canonical_spec())
    assert spec.to_contract_dict() == canonical_spec()


def test_canonical_oracle_attempt_round_trips_exact_spec_and_action_binding() -> None:
    from research_tree import OracleAttempt

    attempt = OracleAttempt.from_mapping(canonical_oracle_attempt())
    assert attempt.to_contract_dict() == canonical_oracle_attempt()


def test_coordinator_rejects_stale_oracle_spec_digest_without_advancing(
    tmp_path,
) -> None:
    from research_tree import AttemptLease, OracleAttempt, OracleSpec, SQLiteRunLedger

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    state = coordinator.create("run-oracle")
    spec = OracleSpec.create(
        "oracle-build",
        "integration-test",
        "integration-test",
        expected="The integration test passes.",
        version=1,
    )
    state = coordinator.record_oracle_spec(
        "run-oracle", spec, expected_revision=state["revision"]
    )
    state = coordinator.issue_lease(
        AttemptLease.create(
            attempt_id="attempt-1",
            work_item_id="work-1",
            run_id="run-oracle",
            owner="worker-1",
            dispatch_digest="f" * 64,
            started_at="2026-08-05T00:00:00Z",
            lease_expires_at="2026-08-05T01:00:00Z",
        ),
        expected_revision=state["revision"],
    )
    attempt = OracleAttempt.from_mapping(
        {
            "oracle_attempt_id": "oracle-attempt-1",
            "run_id": "run-oracle",
            "action_attempt_id": "attempt-1",
            "oracle_spec_id": "oracle-build",
            "oracle_spec_version": 1,
            "oracle_spec_digest": "0" * 64,
            "method": "integration-test",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64,
            "started_at": "2026-08-05T00:00:00+00:00",
        }
    )
    before = state["revision"]

    with pytest.raises(coordinator.error_type) as error:
        coordinator.record_oracle_attempt(
            "run-oracle", attempt, expected_revision=before
        )

    assert error.value.code == "stale_oracle_spec"
    assert coordinator.status("run-oracle")["revision"] == before
    assert coordinator.oracle_attempts("run-oracle") == {}


def test_canonical_oracle_run_binds_attempt_inputs_and_reproducibility() -> None:
    from research_tree import OracleError, OracleRun

    value = {
        "oracle_run_id": "oracle-run-1",
        "oracle_attempt_id": "oracle-attempt-1",
        "oracle_spec_id": "oracle-build",
        "oracle_spec_version": 2,
        "attempt_id": "attempt-1",
        "method": "python-compileall",
        "input_digests": ["c" * 64],
        "environment_digest": "d" * 64,
        "toolchain_digest": "e" * 64,
        "tool_event_refs": ["tool-event-1"],
        "verdict": "inconclusive",
        "exit_code": None,
        "timed_out": True,
        "result_artifact_refs": [result_artifact_ref()],
        "evaluator": "core-oracle-v1",
        "limitations": ["Execution exceeded the declared timeout."],
        "reproducibility_status": "unavailable",
    }
    run = OracleRun.from_mapping(value)
    assert run.to_contract_dict() == value
    legacy = dict(value)
    legacy["result_artifact_refs"] = ["artifact-timeout-log"]
    with pytest.raises(OracleError, match="contract fields mismatch"):
        OracleRun.from_mapping(legacy)
    invalid_digest = dict(value)
    invalid_digest["environment_digest"] = "not-a-digest"
    with pytest.raises(OracleError, match="environment_digest"):
        OracleRun.from_mapping(invalid_digest)


def test_oracle_contract_rejects_unbounded_or_unknown_policy() -> None:
    from research_tree import OracleError, OracleSpec

    value = canonical_spec()
    value["timeout_seconds"] = 0
    with pytest.raises(OracleError, match="positive"):
        OracleSpec.from_mapping(value)


def test_finding_pack_rejects_worker_verdict_and_accepts_exact_oracle_ref() -> None:
    from research_tree.ledger import (
        InvalidFindingPackError,
        _normalize_oracle_run_refs,
        _normalize_validation_result,
    )

    with pytest.raises(InvalidFindingPackError, match="not authoritative"):
        _normalize_validation_result(
            {"status": "passed", "oracle": "worker", "evidence_ref": "missing"}
        )
    refs = _normalize_oracle_run_refs(
        [
            {
                "oracle_run_id": "oracle-run-1",
                "oracle_attempt_id": "oracle-attempt-1",
                "oracle_spec_id": "oracle-build",
                "oracle_spec_version": 2,
                "attempt_id": "attempt-1",
            }
        ]
    )
    assert refs[0]["oracle_spec_version"] == 2


def test_alpha2_closure_rejects_forged_verdict_and_active_contradiction() -> None:
    from research_tree import SlotClosureAssessment

    evidence = [
        {"evidence_id": "e1", "provenance_group": "source-a", "classes": ["repository"]},
        {"evidence_id": "e2", "provenance_group": "source-b", "classes": ["experiment"]},
    ]
    assessment = SlotClosureAssessment.assess_alpha2(
        slot_id="slot-a", assessment_revision=1, decision_ref=decision_ref(), decision_status="selected", evidence=evidence,
        oracle_runs=[], contradictions=[{"id": "c1", "status": "active"}],
        required_classes=["repository", "experiment"],
        counterevidence_search={"completed": True, "query": "counterexample"},
        fallback="Use the current implementation.",
        reversal_condition="A failed integration test.", assessor_version="core-v1",
    )
    assert assessment.status == "open"
    assert assessment.token_digest is None
    assert assessment.checks["oracle_passed"] is False
    assert assessment.checks["contradictions_disposed"] is False


def test_alpha2_closure_token_is_replayable_and_revocable() -> None:
    from research_tree import SlotClosureAssessment, oracle_successor_actions

    assessment = SlotClosureAssessment.assess_alpha2(
        slot_id="slot-a", assessment_revision=2, decision_ref=decision_ref(), decision_status="selected",
        evidence=[
            {"evidence_id": "e1", "provenance_group": "source-a", "classes": ["repository"]},
            {"evidence_id": "e2", "provenance_group": "source-b", "classes": ["experiment"]},
        ],
        oracle_runs=[{"oracle_run_id": "run-1", "verdict": "passed", "reproducibility_status": "reproducible"}],
        contradictions=[], required_classes=["repository", "experiment"],
        counterevidence_search={"completed": True, "query": "counterexample"},
        fallback="Use the current implementation.",
        reversal_condition="A failed integration test.", assessor_version="core-v1",
    )
    assert assessment.status == "passed"
    assert len(assessment.token_digest or "") == 64
    assert assessment.to_contract_dict()["oracle_refs"] == ["run-1"]
    assert assessment.revoke(reason="parent evidence superseded").status == "revoked"
    assert oracle_successor_actions([{"oracle_run_id": "run-fail", "verdict": "failed"}])[0]["action"] == "method_switch"


def test_coordinator_persists_oracle_before_satisfying_closure_obligation(tmp_path) -> None:
    from research_tree import OracleRun, SQLiteRunLedger, SlotClosureAssessment

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    state = coordinator.create("run-oracle")
    state, blueprint = bind_blueprint(ledger, ["slot-a"])
    state, oracle_attempt = persist_oracle_boundary(ledger, state)
    result_artifact = ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="oracle-result",
        kind="oracle-result",
        payload={"exit_code": 0},
        actor_kind="oracle",
        actor_id="core-v1",
        status="active",
        expected_revision=0,
    )
    run = OracleRun.from_mapping(
        {
            "oracle_run_id": "oracle-run-1",
            "oracle_attempt_id": oracle_attempt.oracle_attempt_id,
            "oracle_spec_id": "oracle-build",
            "oracle_spec_version": 1, "attempt_id": "attempt-1", "method": "integration-test",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64, "toolchain_digest": "c" * 64,
            "tool_event_refs": [],
            "verdict": "passed", "exit_code": 0, "timed_out": False,
            "result_artifact_refs": [
                result_artifact_ref(content_hash=result_artifact["content_hash"])
            ], "evaluator": "core-v1",
            "limitations": [], "reproducibility_status": "reproducible",
        }
    )
    state = coordinator.record_oracle_run(
        "run-oracle",
        run,
        expected_revision=coordinator.status("run-oracle")["revision"],
    )
    decision = ledger.append_artifact(
        run_id="run-oracle", artifact_id="decision-a", kind="decision-ledger-entry",
        payload={
            "decision_slot_id": "slot-a",
            "blueprint_target_id": "blueprint-target",
            "status": "selected",
            "fallback": "Defer slot-a.",
            "reversal_condition": "New evidence reverses slot-a.",
        }, actor_kind="coordinator", actor_id="decision-compiler",
        status="active", parent_refs=[{"run_id": "run-oracle", "artifact_id": "blueprint-target", "revision": blueprint["revision"]}], expected_revision=0,
    )
    assessment = SlotClosureAssessment.assess_alpha2(
        slot_id="slot-a", assessment_revision=1,
        decision_ref={"run_id": "run-oracle", "artifact_id": "decision-a", "revision": 1, "content_hash": decision["content_hash"]},
        decision_status="selected",
        evidence=[
            {"evidence_id": "e1", "provenance_group": "source-a", "classes": ["repository"]},
            {"evidence_id": "e2", "provenance_group": "source-b", "classes": ["experiment"]},
        ],
        oracle_runs=[run.to_contract_dict()], contradictions=[],
        required_classes=["repository", "experiment"],
        counterevidence_search={"completed": True},
        fallback="Defer slot-a.",
        reversal_condition="New evidence reverses slot-a.", assessor_version="core-v1",
    )
    state = coordinator.record_closure_assessment("run-oracle", assessment, expected_revision=coordinator.status("run-oracle")["revision"])
    assert coordinator.oracle_runs("run-oracle")["oracle-run-1"]["attempt_id"] == "attempt-1"
    aggregate = coordinator.p0_closure_aggregates("run-oracle")[-1]
    assert coordinator.obligations("run-oracle")["p0_closure"]["evidence_ref"] == aggregate["aggregate_digest"]
    coordinator.record_feedback(
        {
            "feedback_id": "feedback-closure", "run_id": "run-oracle", "actor": "human",
            "kind": "correction", "message": "The decision premise changed.",
            "target_refs": ["decision:decision-a"], "materiality": "material",
            "created_at": "2026-08-05T02:00:00Z",
        },
        expected_revision=state["revision"],
    )
    history = coordinator.closure_assessments("run-oracle")
    assert [item["status"] for item in history] == ["passed", "revoked"]
    assert history[0]["token_digest"] == assessment.token_digest
    assert history[1]["token_digest"] is None
    assert history[1]["revocation_reason"].startswith("human feedback invalidated prior closure:")
    assert coordinator.obligations("run-oracle")["p0_closure"]["satisfied"] is False
    assert any(
        event["event_type"] == "slot_closure_revoked"
        and event["payload"]["reason"].startswith("human feedback invalidated prior closure:")
        for event in coordinator.events("run-oracle")
    )


def test_p0_closure_aggregates_every_active_blueprint_slot(tmp_path) -> None:
    from research_tree import OracleRun, SQLiteRunLedger

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    coordinator.create("run-oracle")
    state, blueprint = bind_blueprint(ledger, ["slot-a", "slot-b"])
    state, oracle_attempt = persist_oracle_boundary(ledger, state)
    result_artifact = ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="oracle-result",
        kind="oracle-result",
        payload={"exit_code": 0},
        actor_kind="oracle",
        actor_id="core-v1",
        status="active",
        expected_revision=0,
    )
    oracle_run = OracleRun.from_mapping(
        {
            "oracle_run_id": "oracle-run-1",
            "oracle_attempt_id": oracle_attempt.oracle_attempt_id,
            "oracle_spec_id": "oracle-build",
            "oracle_spec_version": 1,
            "attempt_id": "attempt-1",
            "method": "integration-test",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64,
            "tool_event_refs": [],
            "verdict": "passed",
            "exit_code": 0,
            "timed_out": False,
            "result_artifact_refs": [
                result_artifact_ref(content_hash=result_artifact["content_hash"])
            ],
            "evaluator": "core-v1",
            "limitations": [],
            "reproducibility_status": "reproducible",
        }
    )
    coordinator.record_oracle_run(
        "run-oracle",
        oracle_run,
        expected_revision=coordinator.status("run-oracle")["revision"],
    )
    decisions = {}
    for slot_id in ("slot-a", "slot-b"):
        decisions[slot_id] = ledger.append_artifact(
            run_id="run-oracle",
            artifact_id=f"decision-{slot_id}",
            kind="decision-ledger-entry",
            payload={
                "decision_slot_id": slot_id,
                "blueprint_target_id": "blueprint-target",
                "status": "selected",
                "fallback": f"Defer {slot_id}.",
                "reversal_condition": f"New evidence reverses {slot_id}.",
            },
            actor_kind="coordinator",
            actor_id="decision-compiler",
            status="active",
            parent_refs=[
                {
                    "run_id": "run-oracle",
                    "artifact_id": "blueprint-target",
                    "revision": blueprint["revision"],
                }
            ],
            expected_revision=0,
        )

    first = passing_assessment("slot-a", decisions["slot-a"], oracle_run)
    coordinator.record_closure_assessment(
        "run-oracle",
        first,
        expected_revision=coordinator.status("run-oracle")["revision"],
    )
    aggregate = coordinator.p0_closure_aggregates("run-oracle")[-1]
    assert aggregate["status"] == "open"
    assert [item["slot_id"] for item in aggregate["slots"]] == ["slot-a", "slot-b"]
    assert aggregate["slots"][1]["status"] == "missing"
    assert coordinator.obligations("run-oracle")["p0_closure"]["satisfied"] is False
    with pytest.raises(coordinator.error_type) as bypass:
        coordinator.record_obligation(
            "run-oracle",
            "p0_closure",
            evidence_ref=first.token_digest,
            expected_revision=coordinator.status("run-oracle")["revision"],
        )
    assert bypass.value.code == "closure_aggregate_required"

    second = passing_assessment("slot-b", decisions["slot-b"], oracle_run)
    coordinator.record_closure_assessment(
        "run-oracle",
        second,
        expected_revision=coordinator.status("run-oracle")["revision"],
    )
    aggregate = coordinator.p0_closure_aggregates("run-oracle")[-1]
    obligation = coordinator.obligations("run-oracle")["p0_closure"]
    assert aggregate["status"] == "passed"
    assert obligation == {
        **obligation,
        "satisfied": True,
        "evidence_ref": aggregate["aggregate_digest"],
    }
    assert aggregate["aggregate_digest"] not in {
        first.token_digest,
        second.token_digest,
    }

    newer = ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="blueprint-target",
        kind="blueprint-target",
        payload={
            "slots": [
                {
                    "id": "slot-a",
                    "priority": "P0",
                    "status": "open",
                    "fallback": "Defer slot-a.",
                    "reversal_condition": "New evidence reverses slot-a.",
                },
                {
                    "id": "slot-c",
                    "priority": "P0",
                    "status": "open",
                    "fallback": "Defer slot-c.",
                    "reversal_condition": "New evidence reverses slot-c.",
                },
            ]
        },
        actor_kind="coordinator",
        actor_id="blueprint-compiler",
        status="active",
        expected_revision=1,
    )
    coordinator.bind_blueprint_target(
        "run-oracle",
        {
            "run_id": "run-oracle",
            "artifact_id": newer["id"],
            "revision": newer["revision"],
            "content_hash": newer["content_hash"],
        },
        expected_revision=coordinator.status("run-oracle")["revision"],
    )
    rebound = coordinator.p0_closure_aggregates("run-oracle")[-1]
    assert rebound["status"] == "open"
    assert {item["status"] for item in rebound["slots"]} == {"missing"}
    assert rebound["blueprint_target_ref"]["revision"] == 2
    assert coordinator.obligations("run-oracle")["p0_closure"]["satisfied"] is False


def test_closure_rejects_decision_slot_mismatch_without_advancing(tmp_path) -> None:
    from research_tree import OracleRun, SQLiteRunLedger

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    coordinator.create("run-oracle")
    state, blueprint = bind_blueprint(ledger, ["slot-a", "slot-b"])
    state, oracle_attempt = persist_oracle_boundary(ledger, state)
    result_artifact = ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="oracle-result",
        kind="oracle-result",
        payload={"exit_code": 0},
        actor_kind="oracle",
        actor_id="core-v1",
        status="active",
        expected_revision=0,
    )
    oracle_run = OracleRun.from_mapping(
        {
            "oracle_run_id": "oracle-run-1",
            "oracle_attempt_id": oracle_attempt.oracle_attempt_id,
            "oracle_spec_id": "oracle-build",
            "oracle_spec_version": 1,
            "attempt_id": "attempt-1",
            "method": "integration-test",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64,
            "tool_event_refs": [],
            "verdict": "passed",
            "exit_code": 0,
            "timed_out": False,
            "result_artifact_refs": [
                result_artifact_ref(content_hash=result_artifact["content_hash"])
            ],
            "evaluator": "core-v1",
            "limitations": [],
            "reproducibility_status": "reproducible",
        }
    )
    coordinator.record_oracle_run(
        "run-oracle",
        oracle_run,
        expected_revision=coordinator.status("run-oracle")["revision"],
    )
    decision = ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="decision-slot-a",
        kind="decision-ledger-entry",
        payload={
            "decision_slot_id": "slot-a",
            "blueprint_target_id": "blueprint-target",
            "status": "selected",
            "fallback": "Defer slot-a.",
            "reversal_condition": "New evidence reverses slot-a.",
        },
        actor_kind="coordinator",
        actor_id="decision-compiler",
        status="active",
        parent_refs=[
            {
                "run_id": "run-oracle",
                "artifact_id": "blueprint-target",
                "revision": blueprint["revision"],
            }
        ],
        expected_revision=0,
    )
    forged = passing_assessment("slot-b", decision, oracle_run)
    before = coordinator.status("run-oracle")["revision"]

    with pytest.raises(coordinator.error_type) as error:
        coordinator.record_closure_assessment(
            "run-oracle", forged, expected_revision=before
        )

    assert error.value.code == "closure_slot_mismatch"
    assert coordinator.status("run-oracle")["revision"] == before
    assert coordinator.closure_assessments("run-oracle") == []


def test_decision_parent_supersession_revokes_prior_closure_in_same_append(tmp_path) -> None:
    from research_tree import OracleRun, SQLiteRunLedger

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    coordinator.create("run-oracle")
    state, blueprint = bind_blueprint(ledger, ["slot-a"])
    state, oracle_attempt = persist_oracle_boundary(ledger, state)
    result_artifact = ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="oracle-result",
        kind="oracle-result",
        payload={"exit_code": 0},
        actor_kind="oracle",
        actor_id="core-v1",
        status="active",
        expected_revision=0,
    )
    oracle_run = OracleRun.from_mapping(
        {
            "oracle_run_id": "oracle-run-1",
            "oracle_attempt_id": oracle_attempt.oracle_attempt_id,
            "oracle_spec_id": "oracle-build",
            "oracle_spec_version": 1,
            "attempt_id": "attempt-1",
            "method": "integration-test",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64,
            "tool_event_refs": [],
            "verdict": "passed",
            "exit_code": 0,
            "timed_out": False,
            "result_artifact_refs": [
                result_artifact_ref(content_hash=result_artifact["content_hash"])
            ],
            "evaluator": "core-v1",
            "limitations": [],
            "reproducibility_status": "reproducible",
        }
    )
    coordinator.record_oracle_run(
        "run-oracle",
        oracle_run,
        expected_revision=coordinator.status("run-oracle")["revision"],
    )
    decision = ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="decision-slot-a",
        kind="decision-ledger-entry",
        payload={
            "decision_slot_id": "slot-a",
            "blueprint_target_id": "blueprint-target",
            "status": "selected",
            "fallback": "Defer slot-a.",
            "reversal_condition": "New evidence reverses slot-a.",
        },
        actor_kind="coordinator",
        actor_id="decision-compiler",
        status="active",
        parent_refs=[
            {
                "run_id": "run-oracle",
                "artifact_id": "blueprint-target",
                "revision": blueprint["revision"],
            }
        ],
        expected_revision=0,
    )
    assessment = passing_assessment("slot-a", decision, oracle_run)
    coordinator.record_closure_assessment(
        "run-oracle",
        assessment,
        expected_revision=coordinator.status("run-oracle")["revision"],
    )
    assert coordinator.obligations("run-oracle")["p0_closure"]["satisfied"] is True

    ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="decision-slot-a",
        kind="decision-ledger-entry",
        payload={
            "decision_slot_id": "slot-a",
            "blueprint_target_id": "blueprint-target",
            "status": "selected",
            "fallback": "Defer slot-a after revision.",
            "reversal_condition": "New evidence reverses slot-a after revision.",
        },
        actor_kind="coordinator",
        actor_id="decision-compiler",
        status="active",
        parent_refs=[
            {
                "run_id": "run-oracle",
                "artifact_id": "blueprint-target",
                "revision": blueprint["revision"],
                },
            {
                "run_id": "run-oracle",
                "artifact_id": "decision-slot-a",
                "revision": decision["revision"],
            },
        ],
        expected_revision=1,
    )

    history = coordinator.closure_assessments("run-oracle")
    assert [item["status"] for item in history] == ["passed", "revoked"]
    assert history[-1]["revocation_reason"] == "decision ledger revision superseded the closure parent"
    assert coordinator.obligations("run-oracle")["p0_closure"]["satisfied"] is False
    assert coordinator.p0_closure_aggregates("run-oracle")[-1]["status"] == "open"


@pytest.mark.parametrize(
    ("reference", "expected_code"),
    [
        (result_artifact_ref(artifact_id="missing"), "result_artifact_not_found"),
        (result_artifact_ref(run_id="other-run"), "result_artifact_scope_mismatch"),
    ],
)
def test_coordinator_rejects_unresolved_result_artifact_without_advancing(
    tmp_path, reference, expected_code
) -> None:
    from research_tree import OracleRun, SQLiteRunLedger

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    state = coordinator.create("run-oracle")
    state, oracle_attempt = persist_oracle_boundary(ledger, state)
    before = state["revision"]
    run = OracleRun.from_mapping(
        {
            "oracle_run_id": "oracle-run-1",
            "oracle_attempt_id": oracle_attempt.oracle_attempt_id,
            "oracle_spec_id": "oracle-build",
            "oracle_spec_version": 1,
            "attempt_id": "attempt-1",
            "method": "integration-test",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64,
            "tool_event_refs": [],
            "verdict": "passed",
            "exit_code": 0,
            "timed_out": False,
            "result_artifact_refs": [reference],
            "evaluator": "core-v1",
            "limitations": [],
            "reproducibility_status": "reproducible",
        }
    )
    with pytest.raises(coordinator.error_type) as error:
        coordinator.record_oracle_run(
            "run-oracle", run, expected_revision=before
        )
    assert error.value.code == expected_code
    assert coordinator.status("run-oracle")["revision"] == before
    assert coordinator.oracle_runs("run-oracle") == {}


def test_coordinator_rejects_stale_result_artifact_digest(tmp_path) -> None:
    from research_tree import OracleRun, SQLiteRunLedger

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    state = coordinator.create("run-oracle")
    state, oracle_attempt = persist_oracle_boundary(ledger, state)
    artifact = ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="oracle-result",
        kind="oracle-result",
        payload={"exit_code": 0},
        actor_kind="oracle",
        actor_id="core-v1",
        status="active",
        expected_revision=0,
    )
    before = coordinator.status("run-oracle")["revision"]
    run = OracleRun.from_mapping(
        {
            "oracle_run_id": "oracle-run-1",
            "oracle_attempt_id": oracle_attempt.oracle_attempt_id,
            "oracle_spec_id": "oracle-build",
            "oracle_spec_version": 1,
            "attempt_id": "attempt-1",
            "method": "integration-test",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64,
            "tool_event_refs": [],
            "verdict": "passed",
            "exit_code": 0,
            "timed_out": False,
            "result_artifact_refs": [
                result_artifact_ref(content_hash="7" * 64)
            ],
            "evaluator": "core-v1",
            "limitations": [],
            "reproducibility_status": "reproducible",
        }
    )
    assert artifact["content_hash"] != "7" * 64
    with pytest.raises(coordinator.error_type) as error:
        coordinator.record_oracle_run(
            "run-oracle", run, expected_revision=before
        )
    assert error.value.code == "stale_result_artifact"
    assert coordinator.status("run-oracle")["revision"] == before


def test_coordinator_rejects_oracle_run_binding_mismatch(tmp_path) -> None:
    from research_tree import OracleRun, SQLiteRunLedger

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    state, oracle_attempt = persist_oracle_boundary(
        ledger, coordinator.create("run-oracle")
    )
    artifact = ledger.append_artifact(
        run_id="run-oracle",
        artifact_id="oracle-result",
        kind="oracle-result",
        payload={"exit_code": 0},
        actor_kind="oracle",
        actor_id="core-v1",
        status="active",
        expected_revision=0,
    )
    run = OracleRun.from_mapping(
        {
            "oracle_run_id": "oracle-run-1",
            "oracle_attempt_id": oracle_attempt.oracle_attempt_id,
            "oracle_spec_id": "oracle-build",
            "oracle_spec_version": 1,
            "attempt_id": "attempt-1",
            "method": "forged-method",
            "input_digests": ["a" * 64],
            "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64,
            "tool_event_refs": [],
            "verdict": "passed",
            "exit_code": 0,
            "timed_out": False,
            "result_artifact_refs": [
                result_artifact_ref(content_hash=artifact["content_hash"])
            ],
            "evaluator": "core-v1",
            "limitations": [],
            "reproducibility_status": "reproducible",
        }
    )
    before = coordinator.status("run-oracle")["revision"]
    with pytest.raises(coordinator.error_type) as error:
        coordinator.record_oracle_run("run-oracle", run, expected_revision=before)
    assert error.value.code == "oracle_attempt_binding_mismatch"
    assert coordinator.status("run-oracle")["revision"] == before


def test_coordinator_rejects_closure_with_unpersisted_oracle(tmp_path) -> None:
    from research_tree import SQLiteRunLedger, SlotClosureAssessment

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    state = coordinator.create("run-oracle")
    state, blueprint = bind_blueprint(ledger, ["slot-a"])
    decision = ledger.append_artifact(
        run_id="run-oracle", artifact_id="decision-a", kind="decision-ledger-entry",
        payload={
            "decision_slot_id": "slot-a",
            "blueprint_target_id": "blueprint-target",
            "status": "selected",
            "fallback": "Defer slot-a.",
            "reversal_condition": "New evidence reverses slot-a.",
        }, actor_kind="coordinator", actor_id="decision-compiler",
        status="active", parent_refs=[{"run_id": "run-oracle", "artifact_id": "blueprint-target", "revision": blueprint["revision"]}], expected_revision=0,
    )
    assessment = SlotClosureAssessment.assess_alpha2(
        slot_id="slot-a", assessment_revision=1,
        decision_ref={"run_id": "run-oracle", "artifact_id": "decision-a", "revision": 1, "content_hash": decision["content_hash"]},
        decision_status="selected",
        evidence=[
            {"evidence_id": "e1", "provenance_group": "source-a", "classes": ["repository"]},
            {"evidence_id": "e2", "provenance_group": "source-b", "classes": ["experiment"]},
        ],
        oracle_runs=[{"oracle_run_id": "missing", "verdict": "passed", "reproducibility_status": "reproducible"}],
        contradictions=[], required_classes=["repository", "experiment"],
        counterevidence_search={"completed": True},
        fallback="Defer slot-a.",
        reversal_condition="New evidence reverses slot-a.", assessor_version="core-v1",
    )
    with pytest.raises(coordinator.error_type) as error:
        coordinator.record_closure_assessment("run-oracle", assessment, expected_revision=coordinator.status("run-oracle")["revision"])
    assert error.value.code == "oracle_not_found"
