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


def decision_ref() -> dict[str, object]:
    return {"run_id": "run-oracle", "artifact_id": "decision-a", "revision": 1, "content_hash": "9" * 64}


def test_canonical_oracle_spec_round_trips_exact_execution_boundary() -> None:
    from research_tree import OracleSpec

    spec = OracleSpec.from_mapping(canonical_spec())
    assert spec.to_contract_dict() == canonical_spec()


def test_canonical_oracle_run_binds_attempt_inputs_and_reproducibility() -> None:
    from research_tree import OracleRun

    value = {
        "oracle_run_id": "oracle-run-1",
        "oracle_spec_id": "oracle-build",
        "attempt_id": "attempt-1",
        "input_digests": ["c" * 64],
        "environment_digest": "d" * 64,
        "toolchain_digest": "e" * 64,
        "verdict": "inconclusive",
        "exit_code": None,
        "timed_out": True,
        "result_artifact_refs": ["artifact-timeout-log"],
        "evaluator": "core-oracle-v1",
        "limitations": ["Execution exceeded the declared timeout."],
        "reproducibility_status": "unavailable",
    }
    run = OracleRun.from_mapping(value)
    assert run.to_contract_dict() == value


def test_oracle_contract_rejects_unbounded_or_unknown_policy() -> None:
    from research_tree import OracleError, OracleSpec

    value = canonical_spec()
    value["timeout_seconds"] = 0
    with pytest.raises(OracleError, match="positive"):
        OracleSpec.from_mapping(value)


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
    from research_tree import AttemptLease, OracleRun, SQLiteRunLedger, SlotClosureAssessment

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    state = coordinator.create("run-oracle")
    lease = AttemptLease.create(
        attempt_id="attempt-1", work_item_id="work-1", run_id="run-oracle",
        owner="worker-1", dispatch_digest="f" * 64,
        started_at="2026-08-05T00:00:00Z", lease_expires_at="2026-08-05T01:00:00Z",
    )
    state = coordinator.issue_lease(lease, expected_revision=state["revision"])
    run = OracleRun.from_mapping(
        {
            "oracle_run_id": "oracle-run-1", "oracle_spec_id": "oracle-build",
            "attempt_id": "attempt-1", "input_digests": ["a" * 64],
            "environment_digest": "b" * 64, "toolchain_digest": "c" * 64,
            "verdict": "passed", "exit_code": 0, "timed_out": False,
            "result_artifact_refs": ["artifact-result"], "evaluator": "core-v1",
            "limitations": [], "reproducibility_status": "reproducible",
        }
    )
    state = coordinator.record_oracle_run("run-oracle", run, expected_revision=state["revision"])
    decision = ledger.append_artifact(
        run_id="run-oracle", artifact_id="decision-a", kind="decision-ledger-entry",
        payload={"status": "selected"}, actor_kind="coordinator", actor_id="decision-compiler",
        status="active", expected_revision=0,
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
        fallback="Use the current implementation.",
        reversal_condition="A failed integration test.", assessor_version="core-v1",
    )
    coordinator.record_closure_assessment("run-oracle", assessment, expected_revision=coordinator.status("run-oracle")["revision"])
    assert coordinator.oracle_runs("run-oracle")["oracle-run-1"]["attempt_id"] == "attempt-1"
    assert coordinator.obligations("run-oracle")["p0_closure"]["evidence_ref"] == assessment.token_digest


def test_coordinator_rejects_closure_with_unpersisted_oracle(tmp_path) -> None:
    from research_tree import SQLiteRunLedger, SlotClosureAssessment

    ledger = SQLiteRunLedger(tmp_path)
    coordinator = ledger.coordinator
    state = coordinator.create("run-oracle")
    decision = ledger.append_artifact(
        run_id="run-oracle", artifact_id="decision-a", kind="decision-ledger-entry",
        payload={"status": "selected"}, actor_kind="coordinator", actor_id="decision-compiler",
        status="active", expected_revision=0,
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
        fallback="Use the current implementation.",
        reversal_condition="A failed integration test.", assessor_version="core-v1",
    )
    with pytest.raises(coordinator.error_type) as error:
        coordinator.record_closure_assessment("run-oracle", assessment, expected_revision=coordinator.status("run-oracle")["revision"])
    assert error.value.code == "oracle_not_found"
