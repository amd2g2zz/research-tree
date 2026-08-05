from __future__ import annotations

from research_tree import (
    AttemptLease,
    OracleAttempt,
    OracleRun,
    OracleSpec,
    SlotClosureAssessment,
    SQLiteRunLedger,
)


def satisfy_p0_closure(ledger: SQLiteRunLedger, state: dict[str, object], *, suffix: str = "main") -> dict[str, object]:
    coordinator = ledger.coordinator
    run_id = str(state["run_id"])
    slot_id = f"slot-{suffix}"
    blueprint = ledger.append_artifact(
        run_id=run_id,
        artifact_id=f"blueprint-target-{suffix}",
        kind="blueprint-target",
        payload={
            "slots": [
                {
                    "id": slot_id,
                    "priority": "P0",
                    "status": "open",
                    "fallback": "Use the prior implementation.",
                    "reversal_condition": "A failed integration test.",
                }
            ]
        },
        actor_kind="coordinator",
        actor_id="blueprint-compiler",
        status="active",
        expected_revision=0,
    )
    state = coordinator.bind_blueprint_target(
        run_id,
        {
            "run_id": run_id,
            "artifact_id": blueprint["id"],
            "revision": blueprint["revision"],
            "content_hash": blueprint["content_hash"],
        },
        expected_revision=int(coordinator.status(run_id)["revision"]),
    )
    spec_id = f"oracle-build-{suffix}"
    spec = OracleSpec.create(
        spec_id,
        "integration-test",
        "integration-test",
        expected="The integration test passes.",
        version=1,
    )
    state = coordinator.record_oracle_spec(
        run_id, spec, expected_revision=int(state["revision"])
    )
    lease = AttemptLease.create(
        attempt_id=f"attempt-closure-{suffix}", work_item_id=f"work-closure-{suffix}",
        run_id=run_id, owner="closure-worker", dispatch_digest="e" * 64,
        started_at="2026-08-05T00:00:00Z", lease_expires_at="2026-08-05T01:00:00Z",
    )
    state = coordinator.issue_lease(lease, expected_revision=int(state["revision"]))
    spec_digest = coordinator.oracle_specs(run_id)[f"{spec_id}@1"][
        "contract_digest"
    ]
    oracle_attempt = OracleAttempt.from_mapping(
        {
            "oracle_attempt_id": f"oracle-attempt-{suffix}",
            "run_id": run_id,
            "action_attempt_id": lease.attempt_id,
            "oracle_spec_id": spec_id,
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
        run_id, oracle_attempt, expected_revision=int(state["revision"])
    )
    result_artifact = ledger.append_artifact(
        run_id=run_id,
        artifact_id=f"oracle-result-{suffix}",
        kind="oracle-result",
        payload={"status": "passed"},
        actor_kind="oracle",
        actor_id="core-v1",
        status="active",
        expected_revision=0,
    )
    run = OracleRun.from_mapping(
        {
            "oracle_run_id": f"oracle-run-{suffix}",
            "oracle_attempt_id": oracle_attempt.oracle_attempt_id,
            "oracle_spec_id": spec_id,
            "oracle_spec_version": 1, "attempt_id": lease.attempt_id, "method": "integration-test",
            "input_digests": ["a" * 64], "environment_digest": "b" * 64,
            "toolchain_digest": "c" * 64, "tool_event_refs": [], "verdict": "passed",
            "exit_code": 0, "timed_out": False,
            "result_artifact_refs": [{
                "run_id": run_id,
                "artifact_id": f"oracle-result-{suffix}",
                "revision": 1,
                "content_hash": result_artifact["content_hash"],
            }],
            "evaluator": "core-v1", "limitations": [], "reproducibility_status": "reproducible",
        }
    )
    state = coordinator.record_oracle_run(
        run_id,
        run,
        expected_revision=int(coordinator.status(run_id)["revision"]),
    )
    decision = ledger.append_artifact(
        run_id=run_id, artifact_id=f"decision-{suffix}", kind="decision-ledger-entry",
        payload={
            "decision_slot_id": slot_id,
            "blueprint_target_id": blueprint["id"],
            "status": "selected",
            "fallback": "Use the prior implementation.",
            "reversal_condition": "A failed integration test.",
        }, actor_kind="coordinator", actor_id="decision-compiler",
        status="active",
        parent_refs=[
            {
                "run_id": run_id,
                "artifact_id": blueprint["id"],
                "revision": blueprint["revision"],
            }
        ],
        expected_revision=0,
    )
    assessment = SlotClosureAssessment.assess_alpha2(
        slot_id=slot_id, assessment_revision=1,
        decision_ref={"run_id": run_id, "artifact_id": f"decision-{suffix}", "revision": 1, "content_hash": decision["content_hash"]},
        decision_status="selected",
        evidence=[
            {"evidence_id": "e1", "provenance_group": "source-a", "classes": ["repository"]},
            {"evidence_id": "e2", "provenance_group": "source-b", "classes": ["experiment"]},
        ],
        oracle_runs=[run.to_contract_dict()], contradictions=[], required_classes=["repository", "experiment"],
        counterevidence_search={"completed": True}, fallback="Use the prior implementation.",
        reversal_condition="A failed integration test.", assessor_version="core-v1",
    )
    return coordinator.record_closure_assessment(
        run_id, assessment, expected_revision=coordinator.status(run_id)["revision"]
    )
