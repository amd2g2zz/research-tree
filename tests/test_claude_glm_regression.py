from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
CASE_PATH = ROOT / "evaluation/cases/claude-glm-regression-synthetic-v1.json"


def case_payload() -> dict[str, object]:
    return json.loads(CASE_PATH.read_text(encoding="utf-8"))


def fixture_module():
    path = ROOT / "evaluation/harness/claude_glm_regression.py"
    spec = importlib.util.spec_from_file_location("claude_glm_regression", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runner_module():
    path = ROOT / "evaluation/harness/run_claude_glm_regression.py"
    spec = importlib.util.spec_from_file_location("run_claude_glm_regression", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def control_trace() -> list[dict[str, object]]:
    return [
        {"event": "activate_skill", "task_id": "decision-target"},
        {"event": "reference_quote", "task_id": "decision-target", "source_id": "source-1"},
        {
            "event": "alignment_question",
            "task_id": "decision-target",
            "question_id": "decision-boundary",
            "open": True,
        },
        {
            "event": "correction",
            "task_id": "decision-target",
            "correction_id": "scope-repair",
            "invalidated_artifacts": ["strategy-1"],
        },
        {
            "event": "strategy_revised",
            "task_id": "decision-target",
            "strategy_id": "strategy-2",
            "supersedes": ["strategy-1"],
        },
        {
            "event": "research_attempt",
            "task_id": "decision-target",
            "attempt_id": "attempt-1",
            "strategy_id": "strategy-2",
            "decision_slot": "integration-contract",
            "closure_state": "open",
        },
        {
            "event": "research_continuation",
            "task_id": "decision-target",
            "from_attempt_id": "attempt-1",
            "to_attempt_id": "attempt-2",
            "reason": "decision_slot_open",
        },
        {
            "event": "research_attempt",
            "task_id": "decision-target",
            "attempt_id": "attempt-2",
            "strategy_id": "strategy-2",
            "decision_slot": "integration-contract",
            "closure_state": "decision_specific",
        },
        {
            "event": "delivery",
            "task_id": "decision-target",
            "delivery_kind": "technical-package",
            "claim_refs": ["evidence-technical"],
            "decision_refs": ["integration-contract"],
        },
        {
            "event": "delivery",
            "task_id": "decision-target",
            "delivery_kind": "human-brief",
            "claim_refs": ["evidence-human"],
            "decision_refs": ["integration-contract"],
        },
    ]


def unavailable_comparison() -> dict[str, object]:
    return {
        "status": "unavailable",
        "blocker_id": "glm52-runtime-unavailable",
        "blocker": "No configured GLM5.2 runtime is available to the fixture runner.",
        "causal_attribution": "unresolved",
        "fixed_inputs": {
            "brief": "brief-digest",
            "context_pack": "context-pack-digest",
            "skill_revision": "skill-digest",
            "tools": "tool-manifest-digest",
            "authority": "authority-digest",
            "environment": "environment-digest",
            "success_oracle": "oracle-digest",
        },
        "varying_factors": ["runtime"],
    }


def check_status(result: dict[str, object], name: str) -> str:
    checks = result["checks"]
    assert isinstance(checks, list)
    check = next(item for item in checks if item["name"] == name)
    return check["status"]


def test_public_case_is_explicitly_synthetic_and_opaque() -> None:
    payload = case_payload()

    assert payload["fixture_class"] == "synthetic-regression"
    assert payload["historical_status"] == "non-historical"
    assert payload["runtime_comparison"]["causal_attribution"] == "unresolved"
    assert payload["runtime_comparison"]["unavailable_is_passing"] is False
    assert isinstance(payload["oracle_id"], str)
    assert fixture_module().validate_case(payload) == []


def test_semantic_control_passes_but_unavailable_comparison_cannot_pass() -> None:
    result = fixture_module().evaluate_fixture(case_payload(), control_trace(), unavailable_comparison())

    assert result["control_status"] == "passed"
    assert result["status"] == "unavailable"
    assert result["passed"] is False
    assert result["blockers"] == ["glm52-runtime-unavailable"]
    assert all(check["status"] == "pass" for check in result["checks"])


def mutate_activation(trace: list[dict[str, object]]) -> None:
    trace.insert(0, {"event": "reference_quote", "task_id": "decision-target", "source_id": "early-source"})


def mutate_question(trace: list[dict[str, object]]) -> None:
    trace.insert(
        3,
        {
            "event": "alignment_question",
            "task_id": "decision-target",
            "question_id": "second-question",
            "open": True,
        },
    )


def mutate_correction(trace: list[dict[str, object]]) -> None:
    trace[3]["invalidated_artifacts"] = []


def mutate_stale_strategy(trace: list[dict[str, object]]) -> None:
    trace[5]["strategy_id"] = "strategy-1"


def mutate_unbound_strategy(trace: list[dict[str, object]]) -> None:
    del trace[5]["strategy_id"]


def mutate_task_identity(trace: list[dict[str, object]]) -> None:
    trace[5]["task_id"] = "diagnostic-subject"


def mutate_continuation(trace: list[dict[str, object]]) -> None:
    del trace[6]


def mutate_delivery(trace: list[dict[str, object]]) -> None:
    trace[9]["claim_refs"] = []


@pytest.mark.parametrize(
    ("mutate", "expected_check"),
    [
        (mutate_activation, "activation_before_reference"),
        (mutate_question, "one_open_question"),
        (mutate_correction, "correction_invalidation"),
        (mutate_stale_strategy, "correction_invalidation"),
        (mutate_unbound_strategy, "correction_invalidation"),
        (mutate_task_identity, "task_identity_isolation"),
        (mutate_continuation, "recursive_continuation"),
        (mutate_delivery, "dual_delivery"),
    ],
)
def test_fixture_rejects_each_required_control(mutate, expected_check: str) -> None:
    trace = control_trace()
    mutate(trace)

    result = fixture_module().evaluate_fixture(case_payload(), trace, unavailable_comparison())

    assert result["control_status"] == "failed"
    assert result["status"] == "failed"
    assert check_status(result, expected_check) == "fail"


def test_fixture_rejects_unsupported_glm_causal_attribution() -> None:
    comparison = unavailable_comparison()
    comparison["status"] = "completed"
    comparison["blocker_id"] = None
    comparison["causal_attribution"] = "GLM5.2 caused the observed behavior"
    comparison["varying_factors"] = ["runtime", "skill_revision"]

    result = fixture_module().evaluate_fixture(case_payload(), control_trace(), comparison)

    assert result["control_status"] == "failed"
    assert result["status"] == "failed"
    assert check_status(result, "attribution_boundary") == "fail"


def test_runner_can_expect_the_honest_unavailable_status(capsys: pytest.CaptureFixture[str]) -> None:
    assert runner_module().main(["--case", str(CASE_PATH), "--expect-status", "unavailable"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "unavailable"
    assert output["passed"] is False
