from __future__ import annotations

from copy import deepcopy

import pytest


def _ref(artifact_id: str, character: str) -> dict[str, object]:
    return {
        "run_id": "run-1",
        "artifact_id": artifact_id,
        "revision": 1,
        "content_hash": character * 64,
    }


def _inputs(*, evaluation_satisfied: bool = True) -> dict[str, object]:
    convergence = {
        "convergence_id": "convergence-1",
        "run_id": "run-1",
        "blueprint_target_ref": _ref("blueprint-target", "1"),
        "insight_digest_ref": _ref("insight-1", "3"),
        "decision_refs": [_ref("decision-1", "4")],
        "p0_closure_aggregate_ref": {
            "run_id": "run-1",
            "aggregate_revision": 2,
            "aggregate_digest": "5" * 64,
        },
        "outcome": "all_slots_closed",
        "deficits": [],
        "producer_version": "convergence-v1",
    }
    return {
        "readiness_id": "readiness-1",
        "run_id": "run-1",
        "blueprint_target_ref": convergence["blueprint_target_ref"],
        "convergence_record_ref": _ref("convergence-1", "2"),
        "convergence_record": convergence,
        "insight_digest_ref": convergence["insight_digest_ref"],
        "insight_digest": {
            "digest_id": "insight-1",
            "producer_version": "insight-v1",
            "source_refs": ["evidence:1"],
            "slot_refs": ["slot-1"],
            "statements": [],
            "contradictions": [],
            "gaps": [],
            "recommended_actions": [],
            "limitations": [],
            "previous_digest_ref": None,
        },
        "decision_refs": convergence["decision_refs"],
        "decisions": [{"decision_id": "decision-1", "status": "selected"}],
        "p0_closure_aggregate_ref": convergence["p0_closure_aggregate_ref"],
        "p0_closure_aggregate": {
            "run_id": "run-1",
            "aggregate_revision": 2,
            "blueprint_target_ref": convergence["blueprint_target_ref"],
            "slots": [],
            "status": "passed",
            "assessor_version": "closure-v1",
            "issued_at": "2026-08-06T00:00:00Z",
            "aggregate_digest": "5" * 64,
        },
        "evaluation_obligation": {
            "obligation": "evaluation",
            "satisfied": evaluation_satisfied,
            "evidence_ref": "evaluation-suite-1" if evaluation_satisfied else None,
        },
        "risk_tier": "standard",
        "producer_version": "readiness-v1",
    }


def test_canonical_readiness_evaluator_produces_exact_ready_record() -> None:
    from research_tree.readiness_records import evaluate_canonical_readiness

    record = evaluate_canonical_readiness(**_inputs())

    assert record["status"] == "ready"
    assert record["deficits"] == []
    assert {item["check_id"] for item in record["checks"]} == {
        "target_lineage",
        "convergence_closure",
        "decision_closure",
        "insight_clear",
        "evaluation_complete",
        "risk_disposition",
    }
    assert all(item["status"] == "pass" for item in record["checks"])


def test_canonical_readiness_evaluator_retains_actionable_evaluation_deficit() -> None:
    from research_tree.readiness_records import evaluate_canonical_readiness

    record = evaluate_canonical_readiness(**_inputs(evaluation_satisfied=False))

    assert record["status"] == "not_ready"
    assert record["deficits"] == [
        {
            "deficit_id": record["deficits"][0]["deficit_id"],
            "check_id": "evaluation_complete",
            "kind": "evaluation_missing",
            "trigger": "Required evaluation evidence has not been recorded.",
            "action": "validation",
            "source_refs": [
                {
                    "obligation": "evaluation",
                    "satisfied": False,
                    "evidence_ref": None,
                }
            ],
        }
    ]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda record: record["checks"].pop(),
        lambda record: record["checks"][0].update(status="unknown"),
        lambda record: record.update(source_digest="0" * 64),
    ],
)
def test_canonical_readiness_validator_rejects_false_ready_or_stale_digest(
    mutate,
) -> None:
    from research_tree.readiness_records import (
        ReadinessRecordContractError,
        evaluate_canonical_readiness,
        validate_canonical_readiness_record,
    )

    invalid = deepcopy(evaluate_canonical_readiness(**_inputs()))
    mutate(invalid)

    with pytest.raises(ReadinessRecordContractError):
        validate_canonical_readiness_record(invalid, run_id="run-1")
