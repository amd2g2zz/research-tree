from __future__ import annotations

from pathlib import Path

from research_tree.alignment_protocol import AlignmentProtocol
from research_tree.run_ledger import RunLedger


def test_action_score_contains_all_semantic_factors(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-actions")
    service = AlignmentProtocol(ledger, "run-actions")
    planned = service.plan(
        [
            {
                "action_id": "action-1",
                "kind": "reconnaissance",
                "field": "scope",
                "objective": "Resolve scope.",
                "trigger_refs": ["brief-1"],
                "impact": 5,
                "human_exclusive": False,
                "researchable": True,
                "expected_ambiguity_reduction": 0.5,
                "decision_consequence": 4,
                "cognitive_load": 1,
                "repetition": 0,
                "closure_oracle": "scope is verified",
                "method_boundary": "repository",
            }
        ],
        seed=4,
    )
    assert set(planned["action"]["score_factors"]) >= {
        "impact",
        "human_exclusivity",
        "researchability",
        "ambiguity_reduction",
        "consequence",
        "cognitive_load",
        "repetition",
    }
