"""Surviving public-case, time-split-case, and evaluation-payload contract tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest


def api():
    from research_tree import (
        EvaluationDiagnosis,
        InvalidEvaluationError,
        TimeSplitCase,
        validate_blueprint_evaluation_payload,
    )

    return {
        "EvaluationDiagnosis": EvaluationDiagnosis,
        "InvalidEvaluationError": InvalidEvaluationError,
        "TimeSplitCase": TimeSplitCase,
        "validate_blueprint_evaluation_payload": validate_blueprint_evaluation_payload,
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


def _check(name: str, status: str, command: str, summary: str) -> dict[str, str]:
    return {"name": name, "status": status, "command": command, "summary": summary}


def evaluation_payload() -> dict[str, object]:
    build = _check(
        "build",
        "pass",
        "uv run python -m compileall -q src",
        "The isolated build completed.",
    )
    fail_to_pass = _check(
        "fail_to_pass",
        "pass",
        "local run of the hidden acceptance commands",
        "The hidden behavior was evaluated.",
    )
    pass_to_pass = _check(
        "pass_to_pass",
        "pass",
        "uv run python -m pytest -q regression",
        "The pre-existing regression suite was evaluated.",
    )
    baseline_miss = _check(
        "fail_to_pass",
        "fail",
        "local run of the hidden acceptance commands",
        "The simpler baseline missed the requested behavior.",
    )
    return {
        "case": case_mapping(),
        "technical_package_ref": {
            "round_id": "round-001",
            "artifact_id": "package-worker-isolation",
            "revision": 3,
        },
        "readiness_record_ref": {
            "round_id": "round-001",
            "artifact_id": "readiness-worker-isolation",
            "revision": 1,
        },
        "structural_quality": {
            "decision_closure": "pass",
            "traceability": "pass",
            "repository_anchor_accuracy": {"status": "pass", "resolved": 9, "total": 10},
        },
        "implementation_outcome": {
            "checks": (build, fail_to_pass, pass_to_pass),
            "diagnoses": (),
            "limitations": ("The evaluator does not measure rollout behavior.",),
        },
        "diagnoses": (),
        "comparison": {
            "baseline": {
                "name": "direct-issue-summary",
                "checks": (build, baseline_miss, pass_to_pass),
                "limitations": ("It has no Decision Ledger or readiness evidence.",),
            }
        },
        "cost": {"tool_calls": 42, "seconds": 810},
        "clarification_burden": {"asked": 2, "unanswered": 0},
    }


def test_versioned_public_case_set_has_pinned_baselines_without_hidden_material() -> None:
    api_modules = api()
    path = Path(__file__).parents[1] / "evaluation" / "cases" / "v1.json"
    case_set = json.loads(path.read_text(encoding="utf-8"))

    assert case_set["schema_version"] == "1"
    assert case_set["corpus_version"] == "2026.1"
    cases = tuple(api_modules["TimeSplitCase"].from_mapping(case) for case in case_set["cases"])
    assert {case.id for case in cases} == {
        "click-isolated-filesystem",
        "requests-contributing-link",
    }
    for case in cases:
        assert len(case.baseline["revision"]) == 40
        assert len(case.baseline["sha256"]) == 64
        assert case.environment["digest"].startswith("sha256:")
        assert "pull" not in case.to_dict()["public_materials"][0]["locator"]


def test_case_rejects_eventual_patch_discussion_and_hidden_test_material() -> None:
    api_modules = api()
    invalid = case_mapping()
    invalid["eventual_patch"] = "diff --git a/secret"

    with pytest.raises(api_modules["InvalidEvaluationError"], match="hidden"):
        api_modules["TimeSplitCase"].from_mapping(invalid)


def test_blueprint_evaluation_payload_accepts_a_complete_record() -> None:
    modules = api()
    payload = evaluation_payload()
    snapshot = copy.deepcopy(payload)

    assert modules["validate_blueprint_evaluation_payload"](payload) is None
    assert payload == snapshot


def test_blueprint_evaluation_payload_accepts_failed_outcome_with_component_diagnosis() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["implementation_outcome"]["checks"][1]["status"] = "fail"
    payload["diagnoses"] = (
        modules["EvaluationDiagnosis"](
            component="technical_package",
            summary="The package omits the migration sequencing needed by hidden acceptance.",
            decision_slot_id="slot-isolation",
            work_item_id="work-isolation",
        ),
    )
    payload["implementation_outcome"]["diagnoses"] = (
        {
            "component": "technical_package",
            "summary": "The package omits the migration sequencing needed by hidden acceptance.",
            "decision_slot_id": "slot-isolation",
            "work_item_id": "work-isolation",
        },
    )

    assert modules["validate_blueprint_evaluation_payload"](payload) is None


def test_blueprint_evaluation_payload_rejects_a_payload_that_is_not_a_mapping() -> None:
    modules = api()

    for invalid_payload in (["blueprint-evaluation"], "blueprint-evaluation", None):
        with pytest.raises(modules["InvalidEvaluationError"], match="blueprint evaluation payload must be a mapping"):
            modules["validate_blueprint_evaluation_payload"](invalid_payload)


def test_blueprint_evaluation_payload_rejects_missing_and_extra_top_level_keys() -> None:
    modules = api()

    missing_comparison = evaluation_payload()
    del missing_comparison["comparison"]
    with pytest.raises(modules["InvalidEvaluationError"]) as missing:
        modules["validate_blueprint_evaluation_payload"](missing_comparison)
    assert "missing=['comparison']" in str(missing.value)

    extra_key = evaluation_payload()
    extra_key["hidden_oracle"] = {"oracle_body": "hidden"}
    with pytest.raises(modules["InvalidEvaluationError"]) as extra:
        modules["validate_blueprint_evaluation_payload"](extra_key)
    assert "extra=['hidden_oracle']" in str(extra.value)


def test_blueprint_evaluation_payload_rejects_an_unsupported_check_name() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["implementation_outcome"]["checks"][1]["name"] = "hidden_acceptance"

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    message = str(raised.value)
    assert "implementation_outcome checks[1].name is unsupported: hidden_acceptance" in message


def test_blueprint_evaluation_payload_rejects_a_repeated_check_name() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["implementation_outcome"]["checks"][1]["name"] = "build"

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    message = str(raised.value)
    assert "implementation_outcome checks repeats check build" in message


def test_blueprint_evaluation_payload_rejects_incomplete_checks() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["implementation_outcome"]["checks"] = payload["implementation_outcome"]["checks"][:2]

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    message = str(raised.value)
    assert "implementation_outcome checks must include exactly: build, fail_to_pass, pass_to_pass" in message


def test_blueprint_evaluation_payload_rejects_an_invalid_structural_quality() -> None:
    modules = api()

    unsupported_closure = evaluation_payload()
    unsupported_closure["structural_quality"]["decision_closure"] = "global"
    with pytest.raises(modules["InvalidEvaluationError"]) as closure:
        modules["validate_blueprint_evaluation_payload"](unsupported_closure)
    assert "structural_quality.decision_closure is unsupported: global" in str(closure.value)

    overcounted = evaluation_payload()
    overcounted["structural_quality"]["repository_anchor_accuracy"] = {
        "status": "pass",
        "resolved": 11,
        "total": 10,
    }
    with pytest.raises(modules["InvalidEvaluationError"]) as overcount:
        modules["validate_blueprint_evaluation_payload"](overcounted)
    assert "repository_anchor_accuracy.resolved cannot exceed total" in str(overcount.value)

    empty_status = evaluation_payload()
    empty_status["structural_quality"]["repository_anchor_accuracy"] = {
        "status": "pass",
        "resolved": 0,
        "total": 0,
    }
    with pytest.raises(modules["InvalidEvaluationError"]) as empty:
        modules["validate_blueprint_evaluation_payload"](empty_status)
    assert "empty repository_anchor_accuracy must be not_applicable" in str(empty.value)

    nonempty_status = evaluation_payload()
    nonempty_status["structural_quality"]["repository_anchor_accuracy"] = {
        "status": "not_applicable",
        "resolved": 0,
        "total": 5,
    }
    with pytest.raises(modules["InvalidEvaluationError"]) as nonempty:
        modules["validate_blueprint_evaluation_payload"](nonempty_status)
    assert "nonempty repository_anchor_accuracy cannot be not_applicable" in str(nonempty.value)


def test_blueprint_evaluation_payload_rejects_an_invalid_comparison() -> None:
    modules = api()

    without_baseline = evaluation_payload()
    without_baseline["comparison"] = {}
    with pytest.raises(modules["InvalidEvaluationError"]) as without:
        modules["validate_blueprint_evaluation_payload"](without_baseline)
    assert "comparison has unexpected keys; missing=['baseline']" in str(without.value)

    non_mapping = evaluation_payload()
    non_mapping["comparison"] = ["direct-issue-summary"]
    with pytest.raises(modules["InvalidEvaluationError"]) as non:
        modules["validate_blueprint_evaluation_payload"](non_mapping)
    assert "comparison must be a mapping" in str(non.value)


def test_blueprint_evaluation_payload_rejects_mismatched_top_level_diagnoses() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["diagnoses"] = (
        {
            "component": "technical_package",
            "summary": "The package omits the migration sequencing needed by hidden acceptance.",
            "decision_slot_id": "slot-isolation",
            "work_item_id": "work-isolation",
        },
    )

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "diagnoses must exactly match implementation_outcome diagnoses" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_a_global_only_diagnosis_component() -> None:
    modules = api()
    payload = evaluation_payload()
    invalid_diagnosis = {
        "component": "global",
        "summary": "A global score does not identify a product component.",
        "decision_slot_id": None,
        "work_item_id": None,
    }
    payload["diagnoses"] = (invalid_diagnosis,)
    payload["implementation_outcome"]["diagnoses"] = (invalid_diagnosis,)

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "diagnoses[0].component is unsupported: global" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_invalid_cost_and_clarification_burden() -> None:
    modules = api()

    negative_cost = evaluation_payload()
    negative_cost["cost"] = {"tool_calls": -1, "seconds": 810}
    with pytest.raises(modules["InvalidEvaluationError"]) as negative:
        modules["validate_blueprint_evaluation_payload"](negative_cost)
    assert "cost.tool_calls must be a nonnegative integer" in str(negative.value)

    boolean_cost = evaluation_payload()
    boolean_cost["cost"] = {"tool_calls": True, "seconds": 810}
    with pytest.raises(modules["InvalidEvaluationError"]) as boolean:
        modules["validate_blueprint_evaluation_payload"](boolean_cost)
    assert "cost.tool_calls must be a nonnegative integer" in str(boolean.value)

    over_answered = evaluation_payload()
    over_answered["clarification_burden"] = {"asked": 1, "unanswered": 2}
    with pytest.raises(modules["InvalidEvaluationError"]) as over:
        modules["validate_blueprint_evaluation_payload"](over_answered)
    assert "clarification_burden.unanswered cannot exceed asked" in str(over.value)

    missing_burden_key = evaluation_payload()
    missing_burden_key["clarification_burden"] = {"asked": 1}
    with pytest.raises(modules["InvalidEvaluationError"]) as missing_burden:
        modules["validate_blueprint_evaluation_payload"](missing_burden_key)
    assert "missing=['unanswered']" in str(missing_burden.value)


def test_blueprint_evaluation_payload_rejects_environment_digest_without_sha256_prefix() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["case"]["environment"]["digest"] = "registry.example/python:3.12"

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "time-split case environment digest must use sha256:" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_empty_public_materials() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["case"]["public_materials"] = ()

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "time-split case public_materials must not be empty" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_string_diagnoses() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["diagnoses"] = "technical_package"

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "diagnoses must be a sequence of EvaluationDiagnosis values" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_non_diagnosis_entries() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["diagnoses"] = (42,)

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "diagnoses[0] must be an EvaluationDiagnosis or mapping" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_checks_that_are_not_a_sequence_of_mappings() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["implementation_outcome"]["checks"] = {"build": "pass"}

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "implementation_outcome checks must be a sequence of mappings" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_non_mapping_check_entries() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["implementation_outcome"]["checks"] = ("build",)

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "implementation_outcome checks[0] must be a mapping" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_limitations_that_are_not_a_string_sequence() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["implementation_outcome"]["limitations"] = "The evaluator does not measure rollout behavior."

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "implementation_outcome limitations must be a sequence of strings" in str(raised.value)


def _invalidate_identifier(payload: dict[str, object], route: str) -> None:
    if route == "technical_package_ref.round_id":
        payload["technical_package_ref"]["round_id"] = "Round_001"
    elif route == "readiness_record_ref.artifact_id":
        payload["readiness_record_ref"]["artifact_id"] = "readiness/worker"
    elif route == "case.id":
        payload["case"]["id"] = "Case_ID"
    else:
        raise AssertionError(f"unknown identifier route: {route}")


@pytest.mark.parametrize(
    ("route", "label"),
    [
        ("technical_package_ref.round_id", "technical_package_ref.round_id"),
        ("readiness_record_ref.artifact_id", "readiness_record_ref.artifact_id"),
        ("case.id", "time-split case id"),
    ],
)
def test_blueprint_evaluation_payload_rejects_invalid_identifiers(route: str, label: str) -> None:
    modules = api()
    payload = evaluation_payload()
    _invalidate_identifier(payload, route)

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert f"{label} must match" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_non_hex_baseline_digest() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["case"]["baseline"]["sha256"] = "g" * 64

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "time-split case baseline sha256 must be a lowercase SHA-256 hex digest" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_non_positive_revision() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["technical_package_ref"]["revision"] = 0

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "technical_package_ref.revision must be a positive integer" in str(raised.value)


def test_blueprint_evaluation_payload_rejects_an_empty_check_command() -> None:
    modules = api()
    payload = evaluation_payload()
    payload["implementation_outcome"]["checks"][0]["command"] = "   "

    with pytest.raises(modules["InvalidEvaluationError"]) as raised:
        modules["validate_blueprint_evaluation_payload"](payload)

    assert "implementation_outcome checks[0].command must be a nonempty string" in str(raised.value)


def test_not_applicable_behavior_retains_its_reason() -> None:
    modules = api()
    payload = evaluation_payload()
    not_applicable = _check(
        "fail_to_pass",
        "not_applicable",
        "none",
        "No hidden acceptance exists for this change.",
    )
    payload["implementation_outcome"]["checks"] = (
        _check("build", "pass", "uv run python -m compileall -q src", "The isolated build completed."),
        not_applicable,
        _check(
            "pass_to_pass",
            "pass",
            "uv run python -m pytest -q regression",
            "The pre-existing regression suite was evaluated.",
        ),
    )

    assert modules["validate_blueprint_evaluation_payload"](payload) is None

    outcome = payload["implementation_outcome"]["checks"][1]
    assert outcome == {
        "name": "fail_to_pass",
        "status": "not_applicable",
        "command": "none",
        "summary": "No hidden acceptance exists for this change.",
    }
