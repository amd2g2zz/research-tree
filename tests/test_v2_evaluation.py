"""Track B governed evaluation contract tests (#468, senior-user-ux-v2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation" / "harness"))

from run_v2_evaluation import (  # noqa: E402
    RUNTIME_ORACLES,
    WAIVED_REASONS,
    run_governed_evaluation,
)
from v2_oracles import SUCCESS_ORACLES  # noqa: E402


@pytest.fixture(scope="module")
def receipt(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("v2-trackb") / "workspace"
    return run_governed_evaluation(workspace, scenarios=("interruption",), hosts=("codex",))


def test_all_thirteen_oracles_have_exactly_one_honest_verdict(receipt):
    per_oracle = receipt["per_oracle"]
    assert set(per_oracle) == {oracle["id"] for oracle in SUCCESS_ORACLES}
    assert len(per_oracle) == len(SUCCESS_ORACLES) == 13
    satisfied = {oracle_id for oracle_id, verdict in per_oracle.items() if verdict == "satisfied"}
    assert satisfied == set(RUNTIME_ORACLES)
    waived = {oracle_id for oracle_id, verdict in per_oracle.items() if verdict == "waived"}
    assert waived == set(WAIVED_REASONS)


def test_completion_gate_completes_and_matrix_subset_passes(receipt):
    assert receipt["status"] == "passed"
    assert receipt["completion_gate"]["decision"] == "completed"
    assert receipt["coverage"]["cells"] == 1
    assert receipt["cells"][0]["status"] == "passed"


def test_disclosures_survive_in_the_receipt(receipt):
    disclosures = receipt["disclosures"]
    assert disclosures["host_process_invoked"] is False
    assert set(disclosures["waived_oracles"]) == set(WAIVED_REASONS)
    assert disclosures["declared_budget"] is None and disclosures["declared_budget_reason"]


def test_review_identities_are_distinct_and_present(receipt):
    review = receipt["independent_review"]
    identities = {review["alignment_verifier"], review["delivery_verifier"], review["session_context"]}
    assert len(identities) == 3
    assert review["delivery_review"]["artifact_id"]
