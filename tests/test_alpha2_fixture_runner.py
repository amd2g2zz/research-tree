from __future__ import annotations


def test_black_box_fixture_reports_earliest_control_failure() -> None:
    from evaluation.harness.claude_glm52_fixture import evaluate_trace

    result = evaluate_trace(
        [
            {"phase": "reference_read", "revision": 0},
            {"phase": "alignment_turn", "prompt_count": 2},
            {"phase": "correction", "invalidated": False},
            {"phase": "research_attempt", "attempt_id": "a1"},
            {"phase": "delivery", "technical_depth": 1, "human_depth": 1},
        ]
    )
    assert result["passed"] is False
    assert result["earliest_failure"] == "activation_before_reference"


def test_black_box_fixture_accepts_recursive_corrected_dual_delivery_trace() -> None:
    from evaluation.harness.claude_glm52_fixture import evaluate_trace

    result = evaluate_trace(
        [
            {"phase": "activation", "revision": 1},
            {"phase": "alignment_turn", "prompt_count": 1, "task_identity": "target-a"},
            {"phase": "correction", "invalidated": True, "task_identity": "target-b"},
            {"phase": "replan", "strategy_revision": 2},
            {"phase": "research_attempt", "attempt_id": "a1"},
            {"phase": "research_attempt", "attempt_id": "a2"},
            {"phase": "delivery", "technical_depth": 8, "human_depth": 8, "claim_refs": 3},
        ]
    )
    assert result["passed"] is True
    assert all(check["status"] == "pass" for check in result["checks"])
