from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXPECTED = {
    "empty-frontier": "pending",
    "active-contradiction": "vulnerability_reproduced",
    "repeated-reconnaissance": "vulnerability_reproduced",
    "adapter-only-completion": "vulnerability_reproduced",
}


def test_state_trace_cases_have_independent_semantic_receipts(tmp_path: Path) -> None:
    from evaluation.harness.alpha1_adversarial_state_trace import (
        replay_state_trace_cases,
    )

    receipts = replay_state_trace_cases(repository_root=ROOT, work_root=tmp_path)

    assert set(receipts) == set(EXPECTED)
    for case_id, expected_status in EXPECTED.items():
        receipt = receipts[case_id]
        assert receipt["case_id"] == case_id
        assert receipt["status"] == expected_status
        assert receipt["baseline"] == {
            "tag": "0.0.1-a1",
            "commit": "8ab91ea4eb55c98441b5ee6001b80922a56ecdd1",
        }
        assert receipt["commands"]
        assert receipt["inputs"]
        assert receipt["observed"]
        assert receipt["limitations"]
        assert "fix_confirmed" not in json.dumps(receipt)
        assert str(tmp_path) not in json.dumps(receipt)

    empty = receipts["empty-frontier"]
    assert empty["semantic_predicate"] == "alpha1_empty_frontier_did_not_complete"
    assert empty["observed"]["status"] == "blocked"
    assert empty["observed"]["frontier_node_ids"] == []

    contradiction = receipts["active-contradiction"]
    assert contradiction["semantic_predicate"] == (
        "alpha1_closed_slot_while_active_contradiction_remained"
    )
    assert contradiction["observed"]["contradiction_count"] == 1
    assert contradiction["observed"]["slot_status"] == "closed"
    assert contradiction["observed"]["frontier_node_ids"] == []

    repeated = receipts["repeated-reconnaissance"]
    assert repeated["semantic_predicate"] == (
        "alpha1_repeated_reconnaissance_without_attempt_consumption"
    )
    assert repeated["observed"]["next_action"] == "reconnaissance"
    assert repeated["observed"]["stagnant_turns"] == 2
    assert repeated["observed"]["response_events"] == 3

    adapter = receipts["adapter-only-completion"]
    assert adapter["semantic_predicate"] == (
        "alpha1_adapter_completed_without_delegation_or_semantic_finding"
    )
    assert adapter["observed"]["status"] == "complete"
    assert adapter["observed"]["delegation_ids"] == []
    assert adapter["observed"]["finding_is_json"] is False


def test_state_trace_results_are_versioned_and_match_replays() -> None:
    from evaluation.harness.alpha1_adversarial_state_trace import CASE_IDS

    for case_id in CASE_IDS:
        path = ROOT / "evaluation" / "results" / "alpha1-adversarial-v1" / "state-trace" / f"{case_id}.json"
        assert path.is_file(), f"missing committed result: {path}"
        result = json.loads(path.read_text(encoding="utf-8"))
        assert result["schema_version"] == 1
        assert result["case_id"] == case_id
        assert result["status"] in {"pending", "vulnerability_reproduced", "inconclusive"}
        assert "fix_confirmed" not in json.dumps(result)
        assert result["commands"]
        assert result["inputs"]
        assert result["observed"]
        assert result["limitations"]


def test_state_trace_rejects_nonempty_work_root_without_mutation(tmp_path: Path) -> None:
    from evaluation.harness.alpha1_adversarial_state_trace import (
        Alpha1StateTraceError,
        replay_state_trace_cases,
    )

    (tmp_path / "sentinel").write_text("preserve me", encoding="utf-8")
    with pytest.raises(Alpha1StateTraceError, match="work_root must be empty"):
        replay_state_trace_cases(repository_root=ROOT, work_root=tmp_path)
    assert (tmp_path / "sentinel").read_text(encoding="utf-8") == "preserve me"
