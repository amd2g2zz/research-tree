from __future__ import annotations

import hashlib

import pytest

from research_tree.domain import ArtifactRef
from research_tree.oracles import (
    ORACLE_ATTEMPT_KIND,
    ORACLE_RUN_KIND,
    ORACLE_SPEC_KIND,
    InvalidOracleError,
    OracleRun,
    OracleService,
    OracleSpec,
)
from research_tree.closure import ASSESSMENT_KIND, ClosureAssessmentError, SlotClosureAssessment, SlotClosureAssessor
from research_tree.run_ledger import RunLedger


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _append(ledger: RunLedger, run_id: str, artifact_id: str, kind: str, payload: dict, parents=()):
    return ledger.append_artifact(
        run_id,
        artifact_id,
        kind,
        payload,
        parent_refs=parents,
        expected_revision=ledger.get_revision(run_id),
    )


def _service(tmp_path):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-oracle")
    return ledger, OracleService(ledger)


def _spec() -> OracleSpec:
    return OracleSpec(
        oracle_spec_id="oracle-spec-1",
        version=1,
        objective="verify generated artifact",
        input_schema_digest=_digest("input-schema"),
        invocation_adapter="pytest",
        permissions={"read_roots": ["workspace"], "write_roots": [], "network": "none", "commands": ["pytest"]},
        resource_limits={"cpu_seconds": 60, "memory_bytes": 1024, "output_bytes": 4096},
        timeout_seconds=60,
        expected_result_schema_digest=_digest("result-schema"),
        retry_policy={"max_attempts": 2, "backoff_seconds": [0, 1], "switch_method_after": 2},
        flaky_policy="repeat_once_then_inconclusive",
        isolation_profile="sandbox",
        human_only=False,
    )


def _oracle_run(service: OracleService, ledger: RunLedger, *, verdict: str = "passed"):
    input_artifact = _append(ledger, "run-oracle", "input-1", "input", {"value": "current"})
    result_artifact = _append(ledger, "run-oracle", "result-1", "result", {"value": "ok"})
    event_artifact = _append(ledger, "run-oracle", "event-1", "tool-event", {"exit": 0})
    spec = service.create_spec(
        round_id="run-oracle",
        spec_id="oracle-spec-1",
        spec=_spec(),
        expected_revision=ledger.get_revision("run-oracle"),
    )
    attempt = service.start_attempt(
        round_id="run-oracle",
        attempt_id="oracle-attempt-1",
        spec=spec,
        input_refs=(ArtifactRef("run-oracle", input_artifact.id, input_artifact.revision),),
        method="pytest",
        environment_digest=_digest("environment"),
        expected_revision=ledger.get_revision("run-oracle"),
    )
    run = service.record_run(
        round_id="run-oracle",
        run=OracleRun(
            oracle_run_id="oracle-run-1",
            oracle_spec_ref=ArtifactRef("run-oracle", spec.id, spec.revision),
            attempt_ref=ArtifactRef("run-oracle", attempt.id, attempt.revision),
            input_refs=(ArtifactRef("run-oracle", input_artifact.id, input_artifact.revision),),
            method="pytest",
            environment_digest=_digest("environment"),
            toolchain_digest=_digest("toolchain"),
            tool_event_refs=(ArtifactRef("run-oracle", event_artifact.id, event_artifact.revision),),
            result_artifact_refs=(ArtifactRef("run-oracle", result_artifact.id, result_artifact.revision),),
            verdict=verdict,
            exit_code=0 if verdict == "passed" else 1,
            timed_out=False,
            evaluator="independent-evaluator",
            limitations=(),
            reproducibility_status="reproducible",
        ),
        expected_revision=ledger.get_revision("run-oracle"),
    )
    return spec, attempt, run


def _assessment_inputs(ledger: RunLedger):
    target = _append(
        ledger,
        "run-oracle",
        "target-1",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1", "priority": "P0", "alternatives": ["a", "b"]}]},
    )
    finding = _append(
        ledger,
        "run-oracle",
        "finding-1",
        "finding-pack",
        {"decision_slot_id": "slot-1", "option_effects": [{"option": "a", "effect": "supports"}]},
        (ArtifactRef("run-oracle", target.id, target.revision),),
    )
    decision = _append(
        ledger,
        "run-oracle",
        "decision-1",
        "decision-ledger-entry",
        {
            "decision_slot_id": "slot-1",
            "status": "selected",
            "selected_option": "a",
            "fallback": "use option b",
            "reversal_condition": "new counterevidence",
        },
        (
            ArtifactRef("run-oracle", target.id, target.revision),
            ArtifactRef("run-oracle", finding.id, finding.revision),
        ),
    )
    return target, decision, finding


def test_oracle_artifacts_are_persisted_with_exact_lineage(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    spec, attempt, run = _oracle_run(service, ledger)

    assert (spec.kind, attempt.kind, run.kind) == (
        ORACLE_SPEC_KIND,
        ORACLE_ATTEMPT_KIND,
        ORACLE_RUN_KIND,
    )
    assert ArtifactRef("run-oracle", spec.id, spec.revision) in attempt.parent_refs
    assert ArtifactRef("run-oracle", attempt.id, attempt.revision) in run.parent_refs


def test_oracle_run_rejects_stale_or_cross_attempt_reference(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    spec, attempt, _ = _oracle_run(service, ledger)
    with pytest.raises(ClosureAssessmentError, match="attempt"):
        service.record_run(
            round_id="run-oracle",
            run=OracleRun(
                oracle_run_id="bad-run",
                oracle_spec_ref=ArtifactRef("run-oracle", spec.id, spec.revision),
                attempt_ref=ArtifactRef("run-oracle", attempt.id, attempt.revision + 1),
                input_refs=(),
                method="pytest",
                environment_digest=_digest("environment"),
                toolchain_digest=_digest("toolchain"),
                tool_event_refs=(),
                result_artifact_refs=(),
                verdict="passed",
                exit_code=0,
                timed_out=False,
                evaluator="independent-evaluator",
                limitations=(),
                reproducibility_status="reproducible",
            ),
            expected_revision=ledger.get_revision("run-oracle"),
        )


def test_forged_worker_pass_cannot_issue_closure_token(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    target, decision, finding = _assessment_inputs(ledger)
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = assessor.assess(
        round_id="run-oracle",
        assessment_id="assessment-1",
        slot_id="slot-1",
        blueprint_target=target,
        decision=decision,
        findings=(finding,),
        oracle_runs=(),
        evaluator_id="core-evaluator",
        provenance_groups=("independent-source", "independent-test"),
        counterevidence_disposition="searched and found none",
        active_contradiction=False,
        expected_revision=ledger.get_revision("run-oracle"),
    )

    assert assessment.kind == ASSESSMENT_KIND
    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["closure_token"] is None
    assert "validation" in assessment.payload["successor_kinds"]


def test_core_evaluator_issues_revision_bound_closure_token(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, finding = _assessment_inputs(ledger)
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = assessor.assess(
        round_id="run-oracle",
        assessment_id="assessment-passed",
        slot_id="slot-1",
        blueprint_target=target,
        decision=decision,
        findings=(finding,),
        oracle_runs=(run,),
        evaluator_id="core-evaluator",
        provenance_groups=("independent-source", "independent-test"),
        counterevidence_disposition="searched and found none",
        active_contradiction=False,
        expected_revision=ledger.get_revision("run-oracle"),
    )

    assert assessment.payload["status"] == "passed"
    assert isinstance(assessment.payload["closure_token"], str)
    assert assessment.payload["closure_token"].startswith("closure-")
    assert SlotClosureAssessment.from_dict(assessment.payload).closure_token == assessment.payload["closure_token"]


def test_non_core_evaluator_cannot_manually_close_slot(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, finding = _assessment_inputs(ledger)
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    with pytest.raises(ClosureAssessmentError, match="core evaluator"):
        assessor.assess(
            round_id="run-oracle",
            assessment_id="assessment-1",
            slot_id="slot-1",
            blueprint_target=target,
            decision=decision,
            findings=(finding,),
            oracle_runs=(run,),
            evaluator_id="worker-claims-close",
            provenance_groups=("independent-source", "independent-test"),
            counterevidence_disposition="searched and found none",
            active_contradiction=False,
            expected_revision=ledger.get_revision("run-oracle"),
        )


def test_active_contradiction_yields_adversarial_successor_and_replay_is_idempotent(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, finding = _assessment_inputs(ledger)
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")
    arguments = dict(
        round_id="run-oracle",
        assessment_id="assessment-contradiction",
        slot_id="slot-1",
        blueprint_target=target,
        decision=decision,
        findings=(finding,),
        oracle_runs=(run,),
        evaluator_id="core-evaluator",
        provenance_groups=("independent-source", "independent-test"),
        counterevidence_disposition="contradiction unresolved",
        active_contradiction=True,
        expected_revision=ledger.get_revision("run-oracle"),
    )

    first = assessor.assess(**arguments)
    replay = assessor.assess(**arguments)

    assert first.payload["status"] == "inconclusive"
    assert "adversarial" in first.payload["successor_kinds"]
    assert replay == first
