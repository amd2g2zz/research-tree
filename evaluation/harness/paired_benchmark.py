"""Validate and analyze a sealed, host-specific paired research benchmark."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import hashlib
import hmac
import importlib.util
import json
from math import isfinite
from numbers import Real
from pathlib import Path
import re
import sys
from typing import Any


__all__ = [
    "PairedBenchmarkError",
    "analyze_benchmark",
    "benchmark_unavailable",
    "review_score_attestation",
    "validate_result_records",
    "validate_sealed_manifest",
]


_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_HOSTS = frozenset({"claude_code", "hermes_agent"})
_CONDITIONS = frozenset({"baseline", "alpha1", "alpha2"})
_ROLES = frozenset({"integrity", "primary", "reliability"})
_INTEGRITY_FIELDS = frozenset(
    {"completion_forgery", "correction_regression", "source_capture_missing", "unresolved_evidence"}
)
_TOKEN_FIELDS = frozenset({"cache_hit_input_tokens", "cache_miss_input_tokens", "output_tokens"})
_QUALITY_ASSESSMENT_FIELDS = frozenset(
    {
        "protocol",
        "review_bundle_digest",
        "reviewer_assignment_digest",
        "arm_and_host_hidden",
        "synthetic_user_scored",
        "review_attestation",
    }
)
_FINAL_MINIMUMS = {
    "primary_unique_tasks": 80,
    "reliability_unique_tasks": 20,
    "reliability_repeats": 5,
    "integrity_unique_tasks": 12,
    "integrity_repeats": 5,
}
_CACHE_HIT_INPUT_CNY_PER_MILLION = 0.02
_CACHE_MISS_INPUT_CNY_PER_MILLION = 1.0
_OUTPUT_CNY_PER_MILLION = 2.0


class PairedBenchmarkError(ValueError):
    """Raised when a benchmark boundary, plan, or measurement is invalid."""


def benchmark_unavailable(reason: str) -> dict[str, str]:
    """Return the only honest result before evaluator-owned inputs are supplied."""

    return {
        "status": "unavailable",
        "evidence_kind": "synthetic-user-proxy",
        "human_evidence_status": "unavailable",
        "reason": _text(reason, "reason", maximum=512),
    }


def validate_sealed_manifest(raw: Mapping[str, object]) -> dict[str, Any]:
    """Validate a private manifest without accepting hidden answer material."""

    payload = _mapping(raw, "sealed benchmark manifest")
    _assert_no_private_material(payload)
    required = {
        "schema_version",
        "benchmark_id",
        "phase",
        "model",
        "cells",
        "episode_plan",
        "task_plan_digest",
        "task_budget",
        "randomization",
        "corpus",
        "execution_envelope",
        "metrics",
        "review",
        "budget",
        "source_access",
        "synthetic_user",
        "human_evidence_status",
    }
    _require_exact_fields(payload, required, "sealed benchmark manifest")
    if payload["schema_version"] != 1:
        raise PairedBenchmarkError("sealed benchmark manifest has an unsupported schema version")
    if _text(payload["benchmark_id"], "benchmark_id", maximum=128) != "paired-research-v1":
        raise PairedBenchmarkError("sealed benchmark manifest has an unexpected benchmark id")
    phase = _text(payload["phase"], "phase", maximum=64)
    if phase not in {"calibration", "sealed-validation", "sealed-final"}:
        raise PairedBenchmarkError("sealed benchmark manifest has an unsupported phase")
    if payload["human_evidence_status"] != "unavailable":
        raise PairedBenchmarkError("synthetic benchmark cannot claim human evidence")

    model = _validate_model(payload["model"])
    cells = _validate_cells(payload["cells"])
    plan = _validate_episode_plan(payload["episode_plan"], cells)
    task_budget = _validate_task_budget(payload["task_budget"])
    _validate_plan_budget(plan, task_budget, phase)
    _validate_randomization(payload["randomization"])
    corpus = _validate_corpus(payload["corpus"])
    execution_envelope = _validate_execution_envelope(payload["execution_envelope"])
    metrics = _validate_metrics(payload["metrics"])
    review = _validate_review(payload["review"])
    budget = _validate_budget(payload["budget"])
    _validate_source_access(payload["source_access"])
    policy = _validate_synthetic_policy(payload["synthetic_user"])

    return {
        "schema_version": 1,
        "benchmark_id": "paired-research-v1",
        "phase": phase,
        "model": model,
        "cells": cells,
        "episode_plan": plan,
        "task_plan_digest": _digest(payload["task_plan_digest"], "task_plan_digest"),
        "task_budget": task_budget,
        "randomization": {"seed_commitment": payload["randomization"]["seed_commitment"]},
        "corpus": corpus,
        "execution_envelope": execution_envelope,
        "metrics": metrics,
        "review": review,
        "budget": budget,
        "source_access": {"mode": "live-capture-proxy", "replay_mode": "after-live-only"},
        "synthetic_user": {
            "evidence_kind": policy.evidence_kind,
            "human_experience_status": policy.human_experience_status,
            "persona_set_digest": policy.persona_set_digest,
            "prompt_family_digest": policy.prompt_family_digest,
            "heldout_task_set_digest": policy.heldout_task_set_digest,
            "assignment_digest": policy.assignment_digest,
            "turn_limit": policy.turn_limit,
        },
        "human_evidence_status": "unavailable",
    }


def validate_result_records(
    raw: Mapping[str, object], manifest: Mapping[str, object], *, review_attestation_key: bytes
) -> dict[str, Any]:
    """Bind blinded scores and provider usage to the evaluator-owned episode plan."""

    _review_attestation_key(review_attestation_key)
    normalized_manifest = validate_sealed_manifest(manifest)
    payload = _mapping(raw, "benchmark records")
    _assert_no_private_material(payload)
    _require_exact_fields(payload, {"schema_version", "records"}, "benchmark records")
    if payload["schema_version"] != 1:
        raise PairedBenchmarkError("benchmark records have an unsupported schema version")
    if not isinstance(payload["records"], list):
        raise PairedBenchmarkError("benchmark records must contain a record list")

    plan_by_episode = {entry["episode_id"]: entry for entry in normalized_manifest["episode_plan"]}
    seen: set[str] = set()
    measurements: list[dict[str, object]] = []
    normalized_records: list[dict[str, object]] = []
    integrity_failures: set[str] = set()
    for raw_record in payload["records"]:
        record = _validate_record(
            raw_record,
            plan_by_episode,
            seen,
            review_attestation_key=review_attestation_key,
        )
        plan_entry = plan_by_episode[record["episode_id"]]
        seen.add(record["episode_id"])
        measurements.append(
            {
                "host": plan_entry["host"],
                "task": plan_entry["task_id"],
                "condition": plan_entry["condition"],
                "repeat": plan_entry["repeat"],
                "value": record["quality_score"],
            }
        )
        integrity_failures.update(key for key, passed in record["integrity"].items() if passed)
        normalized_records.append(record)
    if set(plan_by_episode) != seen:
        raise PairedBenchmarkError("benchmark records are incomplete for the sealed episode plan")

    try:
        _statistics().validate_balanced_rows(measurements, conditions=("baseline", "alpha1", "alpha2"))
    except _statistics().PairedStatisticsError as error:
        raise PairedBenchmarkError("benchmark records are not host-specific paired measurements") from error
    return {
        "manifest": normalized_manifest,
        "measurements": measurements,
        "records": normalized_records,
        "integrity_failures": sorted(integrity_failures),
        "token_usage": _summarize_token_usage(normalized_records, plan_by_episode),
    }


def analyze_benchmark(
    manifest: Mapping[str, object],
    records: Mapping[str, object],
    *,
    review_attestation_key: bytes,
    bootstrap_samples: int = 10_000,
    permutations: int = 10_000,
    seed: int = 0,
) -> dict[str, object]:
    """Analyze Alpha1/Alpha2 contrasts independently for each host.

    The result is a synthetic-user proxy finding. It never pools hosts or
    claims that a model-based proxy establishes a human-experience outcome.
    """

    validated = validate_result_records(records, manifest, review_attestation_key=review_attestation_key)
    contrasts: list[dict[str, object]] = []
    for comparison in ("alpha1", "alpha2"):
        try:
            analyses = _statistics().analyze_paired_rows(
                validated["measurements"],
                baseline_condition="baseline",
                comparison_condition=comparison,
                bootstrap_samples=bootstrap_samples,
                permutations=permutations,
                seed=seed,
            )
        except _statistics().PairedStatisticsError as error:
            raise PairedBenchmarkError("host-specific paired analysis could not be computed") from error
        for analysis in analyses:
            contrasts.append(
                {
                    "host": analysis.host,
                    "comparison": comparison,
                    "mean_quality_difference": analysis.mean_difference,
                    "bootstrap_ci": {
                        "confidence_level": analysis.bootstrap_ci.confidence_level,
                        "lower": analysis.bootstrap_ci.lower,
                        "upper": analysis.bootstrap_ci.upper,
                    },
                    "raw_p_value": analysis.raw_p_value,
                    "holm_adjusted_p_value": analysis.holm_adjusted_p_value,
                }
            )
    integrity_failures = validated["integrity_failures"]
    return {
        "status": "failed-integrity" if integrity_failures else "analyzed",
        "evidence_kind": "synthetic-user-proxy",
        "human_evidence_status": "unavailable",
        "phase": validated["manifest"]["phase"],
        "host_pooling": "forbidden",
        "contrasts": sorted(contrasts, key=lambda entry: (entry["host"], entry["comparison"])),
        "integrity_failures": integrity_failures,
        "token_usage": validated["token_usage"],
    }


def _validate_model(raw: object) -> dict[str, str]:
    model = _mapping(raw, "model")
    _require_exact_fields(model, {"id", "version"}, "model")
    if model["id"] != "deepseek-v4-flash":
        raise PairedBenchmarkError("all benchmark cells must use deepseek-v4-flash")
    return {
        "id": "deepseek-v4-flash",
        "version": _text(model["version"], "model version", maximum=256),
    }


def _validate_cells(raw: object) -> tuple[dict[str, str], ...]:
    if not isinstance(raw, list):
        raise PairedBenchmarkError("benchmark cells must be a list")
    expected_pairs = {(host, condition) for host in _HOSTS for condition in _CONDITIONS}
    cells: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    condition_interventions: dict[str, set[str]] = defaultdict(set)
    host_runtimes: dict[str, set[str]] = defaultdict(set)
    for raw_cell in raw:
        cell = _mapping(raw_cell, "benchmark cell")
        _require_exact_fields(
            cell,
            {
                "host",
                "condition",
                "runtime_digest",
                "intervention_digest",
                "host_binding_digest",
                "guest_rootfs_digest",
                "host_package_digest",
                "host_settings_digest",
                "host_hooks_digest",
                "environment_digest",
                "host_command",
                "host_command_digest",
            },
            "benchmark cell",
        )
        host = _text(cell["host"], "cell host", maximum=64)
        condition = _text(cell["condition"], "cell condition", maximum=64)
        if host not in _HOSTS or condition not in _CONDITIONS:
            raise PairedBenchmarkError("benchmark cell has an unsupported host or condition")
        pair = (host, condition)
        if pair in seen_pairs:
            raise PairedBenchmarkError("benchmark cells contain a duplicate host-condition pair")
        seen_pairs.add(pair)
        runtime_digest = _digest(cell["runtime_digest"], "runtime_digest")
        intervention_digest = _digest(cell["intervention_digest"], "intervention_digest")
        host_binding_digest = _digest(cell["host_binding_digest"], "host_binding_digest")
        guest_rootfs_digest = _digest(cell["guest_rootfs_digest"], "guest_rootfs_digest")
        host_package_digest = _digest(cell["host_package_digest"], "host_package_digest")
        host_settings_digest = _digest(cell["host_settings_digest"], "host_settings_digest")
        host_hooks_digest = _digest(cell["host_hooks_digest"], "host_hooks_digest")
        environment_digest = _digest(cell["environment_digest"], "environment_digest")
        host_command = _text(cell["host_command"], "host_command", maximum=4_096)
        if host_command.count("{episode_input_path}") != 1 or host_command.count("{episode_output_path}") != 1:
            raise PairedBenchmarkError("host command must bind exactly one episode input and output path")
        host_command_digest = _digest(cell["host_command_digest"], "host_command_digest")
        if host_command_digest != _digest_text(host_command):
            raise PairedBenchmarkError("host command digest does not match the frozen command")
        condition_interventions[condition].add(intervention_digest)
        host_runtimes[host].add(runtime_digest)
        cells.append(
            {
                "host": host,
                "condition": condition,
                "runtime_digest": runtime_digest,
                "intervention_digest": intervention_digest,
                "host_binding_digest": host_binding_digest,
                "guest_rootfs_digest": guest_rootfs_digest,
                "host_package_digest": host_package_digest,
                "host_settings_digest": host_settings_digest,
                "host_hooks_digest": host_hooks_digest,
                "environment_digest": environment_digest,
                "host_command": host_command,
                "host_command_digest": host_command_digest,
            }
        )
    if seen_pairs != expected_pairs:
        raise PairedBenchmarkError("benchmark cells must contain exactly the six host-specific paired cells")
    if any(len(values) != 1 for values in condition_interventions.values()):
        raise PairedBenchmarkError("each condition must use the same frozen intervention across hosts")
    if any(len(values) != 1 for values in host_runtimes.values()):
        raise PairedBenchmarkError("each host must use one frozen runtime across conditions")
    return tuple(sorted(cells, key=lambda cell: (cell["host"], cell["condition"])))


def _validate_episode_plan(raw: object, cells: tuple[dict[str, str], ...]) -> tuple[dict[str, object], ...]:
    if not isinstance(raw, list) or not raw:
        raise PairedBenchmarkError("sealed episode plan must be a non-empty list")
    valid_pairs = {(cell["host"], cell["condition"]) for cell in cells}
    expected_pairs = {(host, condition) for host in _HOSTS for condition in _CONDITIONS}
    seen_episode_ids: set[str] = set()
    plan: list[dict[str, object]] = []
    pairings: dict[tuple[str, int, str], set[tuple[str, str]]] = defaultdict(set)
    paired_runner_inputs: dict[tuple[str, int, str], set[str]] = defaultdict(set)
    paired_synthetic_assignments: dict[tuple[str, int, str], set[str]] = defaultdict(set)
    for raw_entry in raw:
        entry = _mapping(raw_entry, "sealed episode plan entry")
        _require_exact_fields(
            entry,
            {
                "episode_id",
                "task_id",
                "host",
                "condition",
                "repeat",
                "role",
                "runner_input_digest",
                "synthetic_user_assignment_digest",
            },
            "sealed episode plan entry",
        )
        episode_id = _text(entry["episode_id"], "episode_id", maximum=256)
        if episode_id in seen_episode_ids:
            raise PairedBenchmarkError("sealed episode plan contains duplicate episode ids")
        seen_episode_ids.add(episode_id)
        task_id = _text(entry["task_id"], "task_id", maximum=256)
        host = _text(entry["host"], "plan host", maximum=64)
        condition = _text(entry["condition"], "plan condition", maximum=64)
        if (host, condition) not in valid_pairs:
            raise PairedBenchmarkError("sealed episode plan refers to an unknown benchmark cell")
        repeat = _positive_int(entry["repeat"], "repeat", maximum=100)
        role = _text(entry["role"], "role", maximum=64)
        if role not in _ROLES:
            raise PairedBenchmarkError("sealed episode plan has an unsupported task role")
        pairing_key = (task_id, repeat, role)
        pairings[pairing_key].add((host, condition))
        runner_input_digest = _digest(entry["runner_input_digest"], "runner_input_digest")
        synthetic_assignment_digest = _digest(
            entry["synthetic_user_assignment_digest"], "synthetic_user_assignment_digest"
        )
        paired_runner_inputs[pairing_key].add(runner_input_digest)
        paired_synthetic_assignments[pairing_key].add(synthetic_assignment_digest)
        plan.append(
            {
                "episode_id": episode_id,
                "task_id": task_id,
                "host": host,
                "condition": condition,
                "repeat": repeat,
                "role": role,
                "runner_input_digest": runner_input_digest,
                "synthetic_user_assignment_digest": synthetic_assignment_digest,
            }
        )
    if any(pairs != expected_pairs for pairs in pairings.values()):
        raise PairedBenchmarkError("every task-repeat must be paired across all six benchmark cells")
    if any(len(digests) != 1 for digests in paired_runner_inputs.values()):
        raise PairedBenchmarkError("paired cells must receive identical runner input")
    if any(len(digests) != 1 for digests in paired_synthetic_assignments.values()):
        raise PairedBenchmarkError("paired cells must use the same synthetic-user assignment")
    return tuple(sorted(plan, key=lambda entry: entry["episode_id"]))


def _validate_task_budget(raw: object) -> dict[str, int]:
    budget = _mapping(raw, "task_budget")
    _require_exact_fields(budget, set(_FINAL_MINIMUMS), "task_budget")
    return {
        "primary_unique_tasks": _positive_int(budget["primary_unique_tasks"], "primary_unique_tasks", maximum=10_000),
        "reliability_unique_tasks": _nonnegative_int(
            budget["reliability_unique_tasks"], "reliability_unique_tasks", maximum=10_000
        ),
        "reliability_repeats": _nonnegative_int(budget["reliability_repeats"], "reliability_repeats", maximum=100),
        "integrity_unique_tasks": _nonnegative_int(
            budget["integrity_unique_tasks"], "integrity_unique_tasks", maximum=10_000
        ),
        "integrity_repeats": _nonnegative_int(budget["integrity_repeats"], "integrity_repeats", maximum=100),
    }


def _validate_plan_budget(plan: tuple[dict[str, object], ...], budget: dict[str, int], phase: str) -> None:
    reference_entries = [entry for entry in plan if entry["host"] == "claude_code" and entry["condition"] == "baseline"]
    by_role: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for entry in reference_entries:
        by_role[str(entry["role"])][str(entry["task_id"])].add(int(entry["repeat"]))
    observed = {
        "primary_unique_tasks": len(by_role["primary"]),
        "reliability_unique_tasks": len(by_role["reliability"]),
        "reliability_repeats": _single_repeat_count(by_role["reliability"], "reliability"),
        "integrity_unique_tasks": len(by_role["integrity"]),
        "integrity_repeats": _single_repeat_count(by_role["integrity"], "integrity"),
    }
    if phase == "calibration":
        return
    if observed != budget:
        raise PairedBenchmarkError(f"{phase} benchmark plan does not match its declared task budget")
    if phase == "sealed-final" and any(budget[key] < minimum for key, minimum in _FINAL_MINIMUMS.items()):
        raise PairedBenchmarkError("sealed-final benchmark does not meet the minimum reliability panel")


def _single_repeat_count(tasks: Mapping[str, set[int]], role: str) -> int:
    if not tasks:
        return 0
    counts = {len(repeats) for repeats in tasks.values()}
    if len(counts) != 1:
        raise PairedBenchmarkError(f"{role} tasks must have a uniform repeat count")
    return counts.pop()


def _validate_randomization(raw: object) -> None:
    value = _mapping(raw, "randomization")
    _require_exact_fields(value, {"seed_commitment", "unblind_after"}, "randomization")
    _digest(value["seed_commitment"], "seed_commitment")
    if value["unblind_after"] != "all-episodes-complete":
        raise PairedBenchmarkError("benchmark unblinding must wait for all episodes")


def _validate_corpus(raw: object) -> dict[str, str]:
    value = _mapping(raw, "benchmark corpus")
    _require_exact_fields(
        value,
        {"revision", "sampling_seed", "strata_digest", "deterministic_case_set_digest", "dynamic_sampling_policy"},
        "benchmark corpus",
    )
    if value["dynamic_sampling_policy"] != "stratified-after-deterministic":
        raise PairedBenchmarkError("benchmark corpus must run deterministic cases before stratified dynamic sampling")
    return {
        "revision": _text(value["revision"], "corpus revision", maximum=256),
        "sampling_seed": _text(value["sampling_seed"], "sampling seed", maximum=256),
        "strata_digest": _digest(value["strata_digest"], "strata_digest"),
        "deterministic_case_set_digest": _digest(
            value["deterministic_case_set_digest"], "deterministic_case_set_digest"
        ),
        "dynamic_sampling_policy": "stratified-after-deterministic",
    }


def _validate_execution_envelope(raw: object) -> dict[str, str]:
    value = _mapping(raw, "execution envelope")
    _require_exact_fields(
        value,
        {"isolation_profile", "raw_artifact_root", "tool_recording_mode", "live_web_variation_policy"},
        "execution envelope",
    )
    if value["isolation_profile"] != "docker-internal-network-v1":
        raise PairedBenchmarkError("benchmark must use the sealed Docker execution envelope")
    if value["tool_recording_mode"] != "captured":
        raise PairedBenchmarkError("benchmark tools must retain captured evidence")
    if value["live_web_variation_policy"] != "report-as-environmental-variation":
        raise PairedBenchmarkError("live-web differences must be reported as environmental variation")
    root = _text(value["raw_artifact_root"], "raw artifact root", maximum=512)
    if not root.startswith(".research-tree/evaluation-runs/"):
        raise PairedBenchmarkError("raw benchmark artifacts must remain in disposable evaluation runs")
    return {
        "isolation_profile": "docker-internal-network-v1",
        "raw_artifact_root": root,
        "tool_recording_mode": "captured",
        "live_web_variation_policy": "report-as-environmental-variation",
    }


def _validate_metrics(raw: object) -> dict[str, str]:
    value = _mapping(raw, "benchmark metrics")
    _require_exact_fields(
        value,
        {
            "metric_catalog_digest",
            "quality_aggregation",
            "missing_data_rule",
            "confidence_interval_method",
            "integrity_separate",
        },
        "benchmark metrics",
    )
    if value["quality_aggregation"] != "host-specific-paired-task-mean":
        raise PairedBenchmarkError("benchmark metric aggregation must remain host-specific and paired")
    if value["missing_data_rule"] != "retain-failure-and-exclude-no-cell":
        raise PairedBenchmarkError("benchmark missing-data rule must retain failures")
    if value["confidence_interval_method"] != "stratified-bootstrap-and-sign-flip":
        raise PairedBenchmarkError("benchmark confidence-interval method is unsupported")
    if value["integrity_separate"] is not True:
        raise PairedBenchmarkError("benchmark integrity gates must remain separate from quality metrics")
    return {
        "metric_catalog_digest": _digest(value["metric_catalog_digest"], "metric_catalog_digest"),
        "quality_aggregation": "host-specific-paired-task-mean",
        "missing_data_rule": "retain-failure-and-exclude-no-cell",
        "confidence_interval_method": "stratified-bootstrap-and-sign-flip",
    }


def _validate_review(raw: object) -> dict[str, str]:
    value = _mapping(raw, "benchmark review")
    _require_exact_fields(
        value, {"protocol", "reviewer_assignment_digest", "disagreement_retention"}, "benchmark review"
    )
    if value["protocol"] != "blinded-independent-review-v1":
        raise PairedBenchmarkError("benchmark review must remain blinded and independent")
    if value["disagreement_retention"] != "retain-and-report-inter-rater-agreement":
        raise PairedBenchmarkError("benchmark review must retain disagreement and inter-rater agreement")
    return {
        "protocol": "blinded-independent-review-v1",
        "reviewer_assignment_digest": _digest(value["reviewer_assignment_digest"], "reviewer_assignment_digest"),
        "disagreement_retention": "retain-and-report-inter-rater-agreement",
    }


def _validate_budget(raw: object) -> dict[str, object]:
    value = _mapping(raw, "benchmark budget")
    _require_exact_fields(value, {"currency", "maximum_cost", "failure_treatment"}, "benchmark budget")
    maximum_cost = value["maximum_cost"]
    if (
        not isinstance(maximum_cost, Real)
        or isinstance(maximum_cost, bool)
        or not isfinite(maximum_cost)
        or maximum_cost <= 0
    ):
        raise PairedBenchmarkError("benchmark budget maximum_cost must be a positive finite number")
    if value["currency"] != "CNY" or value["failure_treatment"] != "report-without-exclusion":
        raise PairedBenchmarkError("benchmark budget must retain failures and use declared CNY cost")
    return {"currency": "CNY", "maximum_cost": float(maximum_cost), "failure_treatment": "report-without-exclusion"}


def _validate_source_access(raw: object) -> None:
    value = _mapping(raw, "source_access")
    _require_exact_fields(value, {"mode", "replay_mode", "direct_runner_egress"}, "source_access")
    if value["mode"] != "live-capture-proxy" or value["replay_mode"] != "after-live-only":
        raise PairedBenchmarkError("benchmark sources must be live and captured before replay")
    if value["direct_runner_egress"] is not False:
        raise PairedBenchmarkError("runner must not have direct source-network egress")


def _validate_synthetic_policy(raw: object):
    try:
        return _synthetic_protocol().validate_synthetic_user_policy(_mapping(raw, "synthetic_user"))
    except _synthetic_protocol().SyntheticUserProtocolError as error:
        raise PairedBenchmarkError(str(error)) from error


def _validate_record(
    raw: object,
    plan_by_episode: Mapping[str, Mapping[str, object]],
    seen: set[str],
    *,
    review_attestation_key: bytes,
) -> dict[str, object]:
    record = _mapping(raw, "benchmark record")
    _assert_no_private_material(record)
    identity_fields = {"arm", "condition", "host"}.intersection(record)
    if identity_fields:
        raise PairedBenchmarkError("runner records must not supply arm identity")
    required = {
        "episode_id",
        "status",
        "quality_score",
        "source_capture_digest",
        "transcript_digest",
        "token_usage",
        "integrity",
        "synthetic_user",
        "quality_assessment",
    }
    _require_exact_fields(record, required, "benchmark record")
    episode_id = _text(record["episode_id"], "record episode_id", maximum=256)
    if episode_id not in plan_by_episode:
        raise PairedBenchmarkError("benchmark record does not bind to the sealed plan")
    if episode_id in seen:
        raise PairedBenchmarkError("benchmark records contain duplicate episode ids")
    if record["status"] != "completed":
        raise PairedBenchmarkError("only completed benchmark episodes may be analyzed")
    quality_score = _quality_score(record["quality_score"])
    token_usage = _validate_token_usage(record["token_usage"])
    integrity = _validate_integrity(record["integrity"])
    synthetic_user = _validate_recorded_synthetic_user(
        record["synthetic_user"],
        expected_assignment_digest=plan_by_episode[episode_id]["synthetic_user_assignment_digest"],
    )
    quality_assessment = _validate_quality_assessment(
        record["quality_assessment"],
        episode_id=episode_id,
        quality_score=quality_score,
        review_attestation_key=review_attestation_key,
    )
    return {
        "episode_id": episode_id,
        "quality_score": quality_score,
        "source_capture_digest": _digest(record["source_capture_digest"], "source_capture_digest"),
        "transcript_digest": _digest(record["transcript_digest"], "transcript_digest"),
        "token_usage": token_usage,
        "integrity": integrity,
        "synthetic_user": synthetic_user,
        "quality_assessment": quality_assessment,
    }


def _validate_token_usage(raw: object) -> dict[str, int]:
    usage = _mapping(raw, "token_usage")
    _require_exact_fields(usage, set(_TOKEN_FIELDS), "token_usage")
    return {field: _nonnegative_int(usage[field], field, maximum=1_000_000_000) for field in sorted(_TOKEN_FIELDS)}


def _validate_integrity(raw: object) -> dict[str, bool]:
    integrity = _mapping(raw, "integrity")
    _require_exact_fields(integrity, set(_INTEGRITY_FIELDS), "integrity")
    if not all(isinstance(value, bool) for value in integrity.values()):
        raise PairedBenchmarkError("integrity fields must be boolean")
    return {field: bool(integrity[field]) for field in sorted(_INTEGRITY_FIELDS)}


def _validate_recorded_synthetic_user(raw: object, *, expected_assignment_digest: object) -> dict[str, object]:
    value = _mapping(raw, "recorded synthetic_user")
    _require_exact_fields(
        value,
        {
            "evidence_kind",
            "human_experience_status",
            "turn_count",
            "canary_status",
            "assignment_digest",
            "session_receipt_digest",
        },
        "recorded synthetic_user",
    )
    if value["evidence_kind"] != "synthetic-user-proxy" or value["human_experience_status"] != "unavailable":
        raise PairedBenchmarkError("recorded synthetic-user evidence is mislabeled")
    turn_count = _nonnegative_int(value["turn_count"], "turn_count", maximum=50)
    if value["canary_status"] != "clear":
        raise PairedBenchmarkError("synthetic-user canary did not clear")
    assignment_digest = _digest(value["assignment_digest"], "synthetic-user assignment_digest")
    if assignment_digest != expected_assignment_digest:
        raise PairedBenchmarkError("recorded synthetic-user assignment does not match the sealed plan")
    return {
        "turn_count": turn_count,
        "assignment_digest": assignment_digest,
        "session_receipt_digest": _digest(value["session_receipt_digest"], "session_receipt_digest"),
    }


def _validate_quality_assessment(
    raw: object, *, episode_id: str, quality_score: float, review_attestation_key: bytes
) -> dict[str, object]:
    value = _mapping(raw, "quality assessment")
    _require_exact_fields(value, set(_QUALITY_ASSESSMENT_FIELDS), "quality assessment")
    if value["protocol"] != "blinded-independent-review-v1":
        raise PairedBenchmarkError("quality assessment must use blinded independent review")
    if value["arm_and_host_hidden"] is not True:
        raise PairedBenchmarkError("quality assessment must hide arm and host identity")
    if value["synthetic_user_scored"] is not False:
        raise PairedBenchmarkError("synthetic user cannot score its own interaction")
    review_bundle_digest = _digest(value["review_bundle_digest"], "review_bundle_digest")
    reviewer_assignment_digest = _digest(value["reviewer_assignment_digest"], "reviewer_assignment_digest")
    supplied_attestation = _review_attestation(value["review_attestation"])
    expected_attestation = review_score_attestation(
        review_attestation_key,
        episode_id=episode_id,
        quality_score=quality_score,
        review_bundle_digest=review_bundle_digest,
        reviewer_assignment_digest=reviewer_assignment_digest,
    )
    if not hmac.compare_digest(supplied_attestation, expected_attestation):
        raise PairedBenchmarkError("quality assessment attestation does not match the blinded review")
    return {
        "protocol": "blinded-independent-review-v1",
        "review_bundle_digest": review_bundle_digest,
        "reviewer_assignment_digest": reviewer_assignment_digest,
        "review_attestation": supplied_attestation,
    }


def review_score_attestation(
    key: bytes,
    *,
    episode_id: str,
    quality_score: float,
    review_bundle_digest: str,
    reviewer_assignment_digest: str,
) -> str:
    """Create an evaluator-held HMAC binding a score to its blinded review."""

    payload = {
        "episode_id": _text(episode_id, "record episode_id", maximum=256),
        "protocol": "blinded-independent-review-v1",
        "quality_score": _quality_score(quality_score),
        "review_bundle_digest": _digest(review_bundle_digest, "review_bundle_digest"),
        "reviewer_assignment_digest": _digest(reviewer_assignment_digest, "reviewer_assignment_digest"),
    }
    canonical_payload = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
    return hmac.new(_review_attestation_key(key), canonical_payload, hashlib.sha256).hexdigest()


def _summarize_token_usage(
    records: list[dict[str, object]], plan_by_episode: Mapping[str, Mapping[str, object]]
) -> dict[str, object]:
    by_cell: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {field: 0 for field in _TOKEN_FIELDS})
    totals = {field: 0 for field in _TOKEN_FIELDS}
    for record in records:
        usage = record["token_usage"]
        if not isinstance(usage, Mapping):
            raise PairedBenchmarkError("normalized token usage is unavailable")
        plan_entry = plan_by_episode[str(record["episode_id"])]
        cell_totals = by_cell[(str(plan_entry["host"]), str(plan_entry["condition"]))]
        for field in _TOKEN_FIELDS:
            amount = int(usage[field])
            totals[field] += amount
            cell_totals[field] += amount
    estimated_cost = (
        totals["cache_hit_input_tokens"] * _CACHE_HIT_INPUT_CNY_PER_MILLION
        + totals["cache_miss_input_tokens"] * _CACHE_MISS_INPUT_CNY_PER_MILLION
        + totals["output_tokens"] * _OUTPUT_CNY_PER_MILLION
    ) / 1_000_000
    return {
        "measurement_status": "measured-from-provider-usage",
        "totals": {field: totals[field] for field in sorted(_TOKEN_FIELDS)},
        "estimated_cost_cny": estimated_cost,
        "by_cell": [
            {"host": host, "condition": condition, **{field: values[field] for field in sorted(_TOKEN_FIELDS)}}
            for (host, condition), values in sorted(by_cell.items())
        ],
    }


def _quality_score(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) or not 0 <= value <= 1:
        raise PairedBenchmarkError("quality_score must be a finite value from zero through one")
    return float(value)


def _assert_no_private_material(value: object) -> None:
    try:
        _synthetic_protocol().assert_no_private_material(value)
    except _synthetic_protocol().SyntheticUserProtocolError as error:
        raise PairedBenchmarkError(str(error)) from error


def _statistics():
    return _load_local_module("paired_statistics", "paired_statistics.py")


def _synthetic_protocol():
    return _load_local_module("synthetic_user_protocol", "synthetic_user_protocol.py")


def _load_local_module(name: str, filename: str):
    module_name = f"_research_tree_evaluation_{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PairedBenchmarkError(f"unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise PairedBenchmarkError(f"{label} must be a mapping with string keys")
    return value


def _require_exact_fields(payload: Mapping[str, object], required: set[str], label: str) -> None:
    if set(payload).difference(required):
        raise PairedBenchmarkError(f"{label} contains unsupported fields")
    if required.difference(payload):
        raise PairedBenchmarkError(f"{label} is missing required fields")


def _text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise PairedBenchmarkError(f"{label} must be a non-empty bounded string")
    return value


def _digest(value: object, label: str) -> str:
    digest = _text(value, label, maximum=80)
    if not _DIGEST_PATTERN.fullmatch(digest):
        raise PairedBenchmarkError(f"{label} must be a SHA-256 digest")
    return digest


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _review_attestation(value: object) -> str:
    attestation = _text(value, "review_attestation", maximum=64)
    if not re.fullmatch(r"[0-9a-f]{64}", attestation):
        raise PairedBenchmarkError("review_attestation must be an HMAC-SHA256 digest")
    return attestation


def _review_attestation_key(value: object) -> bytes:
    if not isinstance(value, bytes) or not 16 <= len(value) <= 4_096:
        raise PairedBenchmarkError("review attestation key must be evaluator-owned bounded bytes")
    return value


def _positive_int(value: object, label: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise PairedBenchmarkError(f"{label} must be an integer between one and {maximum}")
    return value


def _nonnegative_int(value: object, label: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise PairedBenchmarkError(f"{label} must be an integer between zero and {maximum}")
    return value
