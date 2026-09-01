"""Evaluate the public synthetic Claude Code and GLM regression fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

CASE_KEYS = {
    "schema_version",
    "id",
    "fixture_class",
    "historical_status",
    "redaction_policy",
    "public_turns",
    "control_obligations",
    "oracle_id",
    "runtime_comparison",
    "limitations",
}
CONTROL_OBLIGATIONS = (
    "activation_before_reference",
    "one_open_question",
    "correction_invalidation",
    "task_identity_isolation",
    "recursive_continuation",
    "attribution_boundary",
    "dual_delivery",
)
FORBIDDEN_PUBLIC_KEYS = {
    "hidden_oracle",
    "oracle_body",
    "reference_patch",
    "expected_patch",
    "private_prompt",
    "provider_transcript",
    "credential",
    "secret",
}
COMPARISON_CONSTANTS = {
    "brief",
    "context_pack",
    "skill_revision",
    "tools",
    "authority",
    "environment",
    "success_oracle",
}


def load_case(path: str | Path) -> dict[str, Any]:
    """Load a public case manifest without reading operator-owned run material."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture case must be a JSON object")
    return payload


def validate_case(case: Mapping[str, Any]) -> list[str]:
    """Return stable errors when a public case violates the fixture contract."""

    errors: list[str] = []
    if set(case) != CASE_KEYS:
        errors.append("case keys must exactly match the synthetic public contract")
    if case.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if case.get("fixture_class") != "synthetic-regression":
        errors.append("fixture_class must be synthetic-regression")
    if case.get("historical_status") != "non-historical":
        errors.append("historical_status must be non-historical")
    if not isinstance(case.get("id"), str) or not case["id"]:
        errors.append("case id must be non-empty")
    if not isinstance(case.get("oracle_id"), str) or not case["oracle_id"]:
        errors.append("oracle_id must be an opaque non-empty identifier")
    if not isinstance(case.get("redaction_policy"), str) or not case["redaction_policy"]:
        errors.append("redaction_policy must be declared")
    if not _valid_public_turns(case.get("public_turns")):
        errors.append("public_turns must contain only labelled synthetic turns")
    if tuple(case.get("control_obligations", ())) != CONTROL_OBLIGATIONS:
        errors.append("control_obligations must preserve the registered order")
    if not _valid_runtime_contract(case.get("runtime_comparison")):
        errors.append("runtime_comparison must retain unresolved attribution and non-passing unavailability")
    if not isinstance(case.get("limitations"), list) or not case["limitations"]:
        errors.append("limitations must be a non-empty list")
    forbidden = _forbidden_path(case)
    if forbidden:
        errors.append(f"public case contains forbidden evaluator material at {forbidden}")
    return errors


def evaluate_fixture(
    case: Mapping[str, Any], trace: Sequence[Mapping[str, Any]], comparison: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate a synthetic trace and retain unavailable runtime evidence honestly."""

    case_errors = validate_case(case)
    records = [dict(record) for record in trace]
    checks = [
        _check("case_contract", not case_errors, "; ".join(case_errors) or "public synthetic contract is valid"),
        _activation_check(records),
        _question_check(records),
        _correction_check(records),
        _task_identity_check(records),
        _continuation_check(records),
        _attribution_check(comparison),
        _delivery_check(records),
        _unavailable_check(case, comparison),
    ]
    control_status = "passed" if all(check["status"] == "pass" for check in checks) else "failed"
    comparison_status = comparison.get("status")
    if control_status == "failed":
        status = "failed"
    elif comparison_status == "unavailable":
        status = "unavailable"
    elif comparison_status == "completed" and comparison.get("outcome") == "passed":
        status = "passed"
    else:
        status = "failed"
    blocker_id = comparison.get("blocker_id")
    blockers = [blocker_id] if comparison_status == "unavailable" and isinstance(blocker_id, str) else []
    failed = [check["name"] for check in checks if check["status"] == "fail"]
    return {
        "schema_version": 1,
        "case_id": case.get("id"),
        "fixture_class": case.get("fixture_class"),
        "historical_status": case.get("historical_status"),
        "control_status": control_status,
        "comparison_status": comparison_status,
        "status": status,
        "passed": status == "passed",
        "earliest_failure": failed[0] if failed else None,
        "checks": checks,
        "blockers": blockers,
        "causal_attribution": comparison.get("causal_attribution"),
    }


def synthetic_control_trace() -> list[dict[str, Any]]:
    """Return evaluator-owned synthetic control events, never a provider session."""

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


def unavailable_comparison() -> dict[str, Any]:
    """Describe the external GLM runtime blocker without treating it as success."""

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


def _valid_public_turns(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(
        isinstance(turn, Mapping)
        and set(turn) == {"id", "role", "content", "synthetic"}
        and isinstance(turn.get("id"), str)
        and isinstance(turn.get("role"), str)
        and isinstance(turn.get("content"), str)
        and turn.get("synthetic") is True
        for turn in value
    )


def _valid_runtime_contract(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return (
        value.get("required_runtimes") == ["claude-code-native", "glm5.2"]
        and value.get("unavailable_is_passing") is False
        and value.get("causal_attribution") == "unresolved"
        and value.get("constant_inputs") == sorted(COMPARISON_CONSTANTS)
        and value.get("varying_factor") == "runtime"
    )


def _forbidden_path(value: Any, prefix: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in FORBIDDEN_PUBLIC_KEYS:
                return path
            forbidden = _forbidden_path(child, path)
            if forbidden:
                return forbidden
    elif isinstance(value, list):
        for index, child in enumerate(value):
            forbidden = _forbidden_path(child, f"{prefix}[{index}]")
            if forbidden:
                return forbidden
    return None


def _check(name: str, passed: bool, reason: str) -> dict[str, str]:
    return {"name": name, "status": "pass" if passed else "fail", "reason": reason}


def _activation_check(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    first_activation = _first_index(records, "activate_skill")
    first_reference = _first_index(records, "reference_quote")
    passed = first_activation == 0 and first_reference > first_activation
    return _check(
        "activation_before_reference",
        passed,
        "skill activation must be the first event and precede every quoted reference",
    )


def _question_check(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    questions = [record for record in records if record.get("event") == "alignment_question" and record.get("open")]
    passed = len(questions) == 1 and questions[0].get("question_id") == "decision-boundary"
    return _check("one_open_question", passed, "the synthetic ambiguity permits one bounded open question")


def _correction_check(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    correction_index = _first_index(records, "correction")
    if correction_index < 0:
        return _check("correction_invalidation", False, "a material correction is required")
    correction = records[correction_index]
    invalidated = correction.get("invalidated_artifacts")
    if not isinstance(invalidated, list) or not all(isinstance(value, str) for value in invalidated) or not invalidated:
        return _check("correction_invalidation", False, "the correction must invalidate named dependent artifacts")
    successor = next(
        (
            record
            for record in records[correction_index + 1 :]
            if record.get("event") == "strategy_revised"
            and isinstance(record.get("supersedes"), list)
            and set(record["supersedes"]).intersection(invalidated)
        ),
        None,
    )
    if successor is None or not isinstance(successor.get("strategy_id"), str):
        return _check("correction_invalidation", False, "a successor strategy must supersede the invalidated artifact")
    successor_id = successor["strategy_id"]
    stale = [
        record
        for record in records[correction_index + 1 :]
        if record.get("event") == "research_attempt" and record.get("strategy_id") != successor_id
    ]
    return _check(
        "correction_invalidation",
        not stale,
        "research after correction must use the successor strategy rather than invalidated or unbound state",
    )


def _task_identity_check(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    task_ids = [record.get("task_id") for record in records]
    passed = (
        bool(task_ids) and all(isinstance(task_id, str) and task_id for task_id in task_ids) and len(set(task_ids)) == 1
    )
    return _check(
        "task_identity_isolation",
        passed,
        "diagnostic evidence must not silently replace the registered task target",
    )


def _continuation_check(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    attempts = [record for record in records if record.get("event") == "research_attempt"]
    attempt_ids = {record.get("attempt_id") for record in attempts if isinstance(record.get("attempt_id"), str)}
    closed_attempts = {
        record.get("attempt_id")
        for record in attempts
        if record.get("closure_state") == "decision_specific" and isinstance(record.get("attempt_id"), str)
    }
    continued = any(
        record.get("event") == "research_continuation"
        and record.get("reason") == "decision_slot_open"
        and record.get("from_attempt_id") in attempt_ids
        and record.get("to_attempt_id") in closed_attempts
        for record in records
    )
    passed = len(attempt_ids) >= 2 and continued
    return _check(
        "recursive_continuation",
        passed,
        "an open decision slot must produce a successor attempt before decision-specific closure",
    )


def _attribution_check(comparison: Mapping[str, Any]) -> dict[str, str]:
    status = comparison.get("status")
    fixed_inputs = comparison.get("fixed_inputs")
    factors = comparison.get("varying_factors")
    common = (
        status in {"unavailable", "completed"}
        and comparison.get("causal_attribution") == "unresolved"
        and isinstance(fixed_inputs, Mapping)
        and set(fixed_inputs) == COMPARISON_CONSTANTS
        and factors == ["runtime"]
    )
    if status == "unavailable":
        passed = common and isinstance(comparison.get("blocker_id"), str) and bool(comparison.get("blocker"))
        return _check(
            "attribution_boundary",
            passed,
            "an unavailable runtime must retain a named blocker and unresolved attribution",
        )
    passed = common and comparison.get("outcome") in {"passed", "failed"}
    return _check(
        "attribution_boundary",
        passed,
        "a completed comparison may vary only runtime and must retain unresolved attribution in this fixture",
    )


def _delivery_check(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    deliveries = [record for record in records if record.get("event") == "delivery"]
    by_kind = {record.get("delivery_kind"): record for record in deliveries}
    required = {"technical-package", "human-brief"}
    if set(by_kind) != required:
        return _check("dual_delivery", False, "both technical-package and human-brief deliveries are required")
    passed = all(
        _nonempty_string_list(by_kind[kind].get("claim_refs"))
        and _nonempty_string_list(by_kind[kind].get("decision_refs"))
        for kind in required
    )
    return _check(
        "dual_delivery",
        passed,
        "each delivery must bind consequential claims and decisions to resolvable references",
    )


def _unavailable_check(case: Mapping[str, Any], comparison: Mapping[str, Any]) -> dict[str, str]:
    contract = case.get("runtime_comparison")
    unavailable_is_passing = contract.get("unavailable_is_passing") if isinstance(contract, Mapping) else None
    passed = comparison.get("status") != "unavailable" or (
        unavailable_is_passing is False and comparison.get("counts_as_pass") is not True
    )
    return _check("unavailable_is_not_pass", passed, "unavailable runtime evidence cannot count as a pass")


def _first_index(records: Sequence[Mapping[str, Any]], event: str) -> int:
    return next((index for index, record in enumerate(records) if record.get("event") == event), -1)


def _nonempty_string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value)
