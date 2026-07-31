from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pytest

from test_readiness import complete_conditional_package


def api():
    from research_tree import (
        BlueprintEvaluationSuite,
        EvaluationCheck,
        EvaluationDiagnosis,
        IndependentEvaluationResult,
        InvalidEvaluationError,
        ReadinessVerifier,
        SimplerBaselineResult,
        TimeSplitCase,
    )

    return {
        "BlueprintEvaluationSuite": BlueprintEvaluationSuite,
        "EvaluationCheck": EvaluationCheck,
        "EvaluationDiagnosis": EvaluationDiagnosis,
        "IndependentEvaluationResult": IndependentEvaluationResult,
        "InvalidEvaluationError": InvalidEvaluationError,
        "ReadinessVerifier": ReadinessVerifier,
        "SimplerBaselineResult": SimplerBaselineResult,
        "TimeSplitCase": TimeSplitCase,
    }


def case_mapping() -> dict[str, object]:
    return {
        "id": "case-worker-isolation",
        "corpus_version": "2026.1",
        "source": {
            "locator": "https://github.com/example/worker-service",
            "permission": "public repository fixture",
        },
        "baseline": {
            "revision": "2f4a1b7",
            "sha256": "a" * 64,
        },
        "environment": {
            "image": "python:3.12-slim",
            "digest": "sha256:" + "b" * 64,
            "recipe": "uv sync --locked; uv run python -m pytest -q",
        },
        "public_materials": (
            {
                "kind": "issue",
                "locator": "https://github.com/example/worker-service/issues/42",
            },
        ),
        "hidden_oracle_id": "oracle-worker-isolation-v2",
        "limitations": ("The fixture omits deployment-only behavior.",),
    }


def test_versioned_public_case_set_has_pinned_baselines_without_hidden_material() -> None:
    api_modules = api()
    path = Path(__file__).parents[1] / "evaluation" / "cases" / "v1.json"
    case_set = json.loads(path.read_text(encoding="utf-8"))

    assert case_set["schema_version"] == "1"
    assert case_set["corpus_version"] == "2026.1"
    cases = tuple(
        api_modules["TimeSplitCase"].from_mapping(case)
        for case in case_set["cases"]
    )
    assert {case.id for case in cases} == {
        "click-isolated-filesystem",
        "requests-contributing-link",
    }
    for case in cases:
        assert len(case.baseline["revision"]) == 40
        assert len(case.baseline["sha256"]) == 64
        assert case.environment["digest"].startswith("sha256:")
        assert "pull" not in case.to_dict()["public_materials"][0]["locator"]


@dataclass
class CapturingRunner:
    result: object
    request: object | None = None

    def run(self, request):
        self.request = request
        return self.result


def result_for(api_modules, *, fail_to_pass: str = "pass", diagnoses=()):
    check = api_modules["EvaluationCheck"]
    return api_modules["IndependentEvaluationResult"](
        checks=(
            check(
                name="build",
                status="pass",
                command="uv run python -m compileall -q src",
                summary="The isolated build completed.",
            ),
            check(
                name="fail_to_pass",
                status=fail_to_pass,
                command="uv run python -m pytest -q hidden_acceptance",
                summary="The hidden behavior was evaluated.",
            ),
            check(
                name="pass_to_pass",
                status="pass",
                command="uv run python -m pytest -q regression",
                summary="The pre-existing regression suite was evaluated.",
            ),
        ),
        diagnoses=diagnoses,
        limitations=("The evaluator does not measure rollout behavior.",),
    )


def baseline_for(api_modules):
    check = api_modules["EvaluationCheck"]
    return api_modules["SimplerBaselineResult"](
        name="direct-issue-summary",
        checks=(
            check(
                name="build",
                status="pass",
                command="uv run python -m compileall -q src",
                summary="The simpler baseline built.",
            ),
            check(
                name="fail_to_pass",
                status="fail",
                command="uv run python -m pytest -q hidden_acceptance",
                summary="The simpler baseline missed the requested behavior.",
            ),
            check(
                name="pass_to_pass",
                status="pass",
                command="uv run python -m pytest -q regression",
                summary="The simpler baseline retained regression behavior.",
            ),
        ),
        limitations=("It has no Decision Ledger or readiness evidence.",),
    )


def readiness_for(api_modules, store, round_record, package, root: Path):
    return api_modules["ReadinessVerifier"](store).verify(
        round_id=round_record.id,
        readiness_id="readiness-evaluation",
        technical_package=package,
        repository_roots={"input-repository": root},
        risk_tier="default",
    )


def test_case_rejects_eventual_patch_discussion_and_hidden_test_material() -> None:
    api_modules = api()
    invalid = case_mapping()
    invalid["eventual_patch"] = "diff --git a/secret"

    with pytest.raises(api_modules["InvalidEvaluationError"], match="hidden"):
        api_modules["TimeSplitCase"].from_mapping(invalid)


def test_evaluation_persists_structural_quality_and_isolated_outcome(tmp_path: Path) -> None:
    api_modules = api()
    _modules, store, round_record, package = complete_conditional_package(tmp_path)
    readiness = readiness_for(
        api_modules, store, round_record, package, tmp_path / "repository"
    )
    runner = CapturingRunner(result_for(api_modules))
    case = api_modules["TimeSplitCase"].from_mapping(case_mapping())

    record = api_modules["BlueprintEvaluationSuite"](store).evaluate(
        round_id=round_record.id,
        evaluation_id="evaluation-worker-isolation",
        case=case,
        technical_package=package,
        readiness_record=readiness,
        cost={"tool_calls": 42, "seconds": 810},
        clarification_burden={"asked": 2, "unanswered": 0},
        implementation_runner=runner,
        baseline_result=baseline_for(api_modules),
    )

    request = runner.request
    assert request is not None
    assert not hasattr(request, "hidden_oracle_id")
    assert not hasattr(request, "eventual_patch")
    assert request.baseline == {"revision": "2f4a1b7", "sha256": "a" * 64}
    assert request.technical_package["ref"]["artifact_id"] == package.id
    assert request.readiness["ref"]["artifact_id"] == readiness.id
    assert record.kind == "blueprint-evaluation"
    assert record.payload["case"]["corpus_version"] == "2026.1"
    assert record.payload["structural_quality"]["decision_closure"] == "pass"
    assert record.payload["structural_quality"]["traceability"] == "pass"
    assert record.payload["implementation_outcome"]["checks"][1]["name"] == "fail_to_pass"
    assert record.payload["implementation_outcome"]["checks"][2]["name"] == "pass_to_pass"
    assert record.payload["comparison"]["baseline"]["name"] == "direct-issue-summary"
    assert record.payload["cost"] == {"tool_calls": 42, "seconds": 810}
    assert record.payload["clarification_burden"] == {"asked": 2, "unanswered": 0}


def test_failed_outcome_diagnoses_a_product_component_not_a_global_score(tmp_path: Path) -> None:
    api_modules = api()
    _modules, store, round_record, package = complete_conditional_package(tmp_path)
    readiness = readiness_for(
        api_modules, store, round_record, package, tmp_path / "repository"
    )
    diagnosis = api_modules["EvaluationDiagnosis"](
        component="technical_package",
        summary="The package omits the migration sequencing needed by hidden acceptance.",
        decision_slot_id="slot-isolation",
        work_item_id="work-isolation",
    )
    runner = CapturingRunner(
        result_for(api_modules, fail_to_pass="fail", diagnoses=(diagnosis,))
    )

    record = api_modules["BlueprintEvaluationSuite"](store).evaluate(
        round_id=round_record.id,
        evaluation_id="evaluation-diagnosis",
        case=api_modules["TimeSplitCase"].from_mapping(case_mapping()),
        technical_package=package,
        readiness_record=readiness,
        cost={"tool_calls": 12, "seconds": 90},
        clarification_burden={"asked": 0, "unanswered": 0},
        implementation_runner=runner,
        baseline_result=baseline_for(api_modules),
    )

    assert record.payload["implementation_outcome"]["checks"][1]["status"] == "fail"
    assert record.payload["diagnoses"] == (
        {
            "component": "technical_package",
            "summary": "The package omits the migration sequencing needed by hidden acceptance.",
            "decision_slot_id": "slot-isolation",
            "work_item_id": "work-isolation",
        },
    )


def test_invalid_diagnosis_is_rejected_without_partial_record(tmp_path: Path) -> None:
    api_modules = api()
    _modules, store, round_record, package = complete_conditional_package(tmp_path)
    readiness = readiness_for(
        api_modules, store, round_record, package, tmp_path / "repository"
    )
    invalid_diagnosis = api_modules["EvaluationDiagnosis"](
        component="global",
        summary="A global score does not identify a product component.",
    )
    runner = CapturingRunner(result_for(api_modules, diagnoses=(invalid_diagnosis,)))

    with pytest.raises(api_modules["InvalidEvaluationError"], match="component"):
        api_modules["BlueprintEvaluationSuite"](store).evaluate(
            round_id=round_record.id,
            evaluation_id="evaluation-invalid-diagnosis",
            case=api_modules["TimeSplitCase"].from_mapping(case_mapping()),
            technical_package=package,
            readiness_record=readiness,
            cost={"tool_calls": 1, "seconds": 1},
            clarification_burden={"asked": 0, "unanswered": 0},
            implementation_runner=runner,
            baseline_result=baseline_for(api_modules),
        )

    assert not [
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.kind == "blueprint-evaluation"
    ]


def test_not_applicable_behavior_retains_its_reason(tmp_path: Path) -> None:
    api_modules = api()
    _modules, store, round_record, package = complete_conditional_package(tmp_path)
    readiness = readiness_for(
        api_modules, store, round_record, package, tmp_path / "repository"
    )
    check = api_modules["EvaluationCheck"]
    runner = CapturingRunner(
        api_modules["IndependentEvaluationResult"](
            checks=(
                check("build", "pass", "uv run python -m compileall -q src", "Build completed."),
                check("fail_to_pass", "not_applicable", "none", "No hidden acceptance exists for this change."),
                check("pass_to_pass", "pass", "uv run python -m pytest -q regression", "Regression completed."),
            ),
            diagnoses=(),
            limitations=("The historical change had no feature-specific oracle.",),
        )
    )

    record = api_modules["BlueprintEvaluationSuite"](store).evaluate(
        round_id=round_record.id,
        evaluation_id="evaluation-not-applicable",
        case=api_modules["TimeSplitCase"].from_mapping(case_mapping()),
        technical_package=package,
        readiness_record=readiness,
        cost={"tool_calls": 3, "seconds": 20},
        clarification_burden={"asked": 0, "unanswered": 0},
        implementation_runner=runner,
        baseline_result=baseline_for(api_modules),
    )

    outcome = record.payload["implementation_outcome"]["checks"][1]
    assert outcome == {
        "name": "fail_to_pass",
        "status": "not_applicable",
        "command": "none",
        "summary": "No hidden acceptance exists for this change.",
    }
