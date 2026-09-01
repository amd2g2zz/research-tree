"""Track B supplement contract tests: contradiction detection + contamination gate."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluation" / "harness"))

import pytest
from v2_contradiction_contamination import run_supplements  # noqa: E402


@pytest.fixture(scope="module")
def receipt(tmp_path_factory):
    return run_supplements(tmp_path_factory.mktemp("supplements"))


def test_supplements_both_stages_pass(receipt):
    assert receipt["status"] == "passed"
    assert {stage["stage"] for stage in receipt["stages"]} == {
        "contradiction-detection",
        "contamination-gate",
    }


def test_contradiction_stage_separates_authority_from_conflict(receipt):
    stage = next(s for s in receipt["stages"] if s["stage"] == "contradiction-detection")
    checks = stage["checks"]
    assert checks["contested_pair_detected"]
    assert checks["contested_pair_lacks_decision_authority"]
    assert checks["scope_separated_pair_detected"]
    assert checks["scope_separated_pair_keeps_authority"]
    assert checks["packets_survive_ledger_round_trip"]


def test_contamination_stage_enforces_sealing_and_budget(receipt):
    stage = next(s for s in receipt["stages"] if s["stage"] == "contamination-gate")
    checks = stage["checks"]
    assert checks["unsealed_active_output_rejected"]["ok"]
    assert checks["sealed_active_output_readable"]["ok"]
    assert checks["dispositions_fresh_cached_replayed"]["ok"]
    assert checks["discovery_excludes_unsealed_active_output"]["ok"]
    assert checks["exhausted_budget_blocks_further_reads"]["ok"]
    assert checks["declared_budget_exceeded_is_resumable_checkpoint"]["ok"]
    assert checks["ledger_receipt_claims_no_completion_authority"]["ok"]
    assert checks["resume_reopens_next_wave"]["ok"]
