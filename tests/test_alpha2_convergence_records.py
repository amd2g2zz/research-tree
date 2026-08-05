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


def _record() -> dict[str, object]:
    return {
        "convergence_id": "convergence-1",
        "run_id": "run-1",
        "blueprint_target_ref": _ref("blueprint-target", "1"),
        "insight_digest_ref": _ref("insight-1", "2"),
        "decision_refs": [_ref("decision-1", "3")],
        "p0_closure_aggregate_ref": {
            "run_id": "run-1",
            "aggregate_revision": 2,
            "aggregate_digest": "4" * 64,
        },
        "outcome": "closure_deficit",
        "deficits": [
            {
                "deficit_id": "deficit-1",
                "slot_id": "slot-1",
                "kind": "closure_missing",
                "trigger": "P0 closure status is missing.",
                "action": "validation",
                "source_refs": ["p0-closure:2#" + "4" * 64],
            }
        ],
        "producer_version": "convergence-v1",
    }


def test_convergence_record_accepts_exact_deficit_lineage():
    from research_tree.convergence_records import validate_convergence_record_payload

    record = _record()
    assert validate_convergence_record_payload(record, run_id="run-1") == record


@pytest.mark.parametrize(
    "mutate",
    [
        lambda record: record.update(outcome="all_slots_closed"),
        lambda record: record["deficits"][0].update(source_refs=[]),
        lambda record: record.update(run_id="run-2"),
    ],
)
def test_convergence_record_rejects_inconsistent_outcome_or_scope(mutate):
    from research_tree.convergence_records import (
        ConvergenceRecordContractError,
        validate_convergence_record_payload,
    )

    invalid = deepcopy(_record())
    mutate(invalid)

    with pytest.raises(ConvergenceRecordContractError):
        validate_convergence_record_payload(invalid, run_id="run-1")
