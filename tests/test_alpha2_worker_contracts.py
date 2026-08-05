import pytest

from research_tree import AttemptPolicy, CanonicalWorkItem, FindingSubmission, WorkerContractError


def test_canonical_work_item_requires_oracle_and_bounded_retry_policy():
    item = CanonicalWorkItem.create(work_item_id="work-1", slot_id="slot-1", action_kind="deep_dive", objective="inspect", inputs=["input-1"], method="repository", expected_output="finding", success_oracle="oracle-1", permission_profile="read-only", completion_evidence=["evidence-1"])
    assert item.attempt_policy.max_attempts == 3
    with pytest.raises(WorkerContractError):
        AttemptPolicy.create(max_attempts=4)
    with pytest.raises(WorkerContractError):
        CanonicalWorkItem.create(work_item_id="work-1", slot_id="slot-1", action_kind="deep_dive", objective="inspect", inputs=["input-1"], method="repository", expected_output="finding", success_oracle="", permission_profile="read-only")


def test_finding_submission_preserves_partial_and_empty_dispositions():
    empty = FindingSubmission.from_dict({"attempt_id": "attempt-1"})
    assert empty.status == "empty_submission"
    partial = FindingSubmission.from_dict({"attempt_id": "attempt-2", "observations": [{"claim": "valid"}, {"bad": True}]})
    assert partial.status == "partial_submission"
    assert partial.next_action == "retry"
    assert partial.errors
