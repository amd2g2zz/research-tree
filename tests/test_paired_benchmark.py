from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def benchmark_module():
    path = ROOT / "evaluation/harness/paired_benchmark.py"
    spec = importlib.util.spec_from_file_location("paired_benchmark", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BENCHMARK = benchmark_module()
PairedBenchmarkError = BENCHMARK.PairedBenchmarkError
analyze_benchmark = BENCHMARK.analyze_benchmark
benchmark_unavailable = BENCHMARK.benchmark_unavailable
review_score_attestation = BENCHMARK.review_score_attestation
validate_sealed_manifest = BENCHMARK.validate_sealed_manifest


REVIEW_KEY = b"evaluator-owned-test-key-v1"


def digest(character: str) -> str:
    return "sha256:" + character * 64


def text_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def sealed_manifest(*, phase: str = "calibration") -> dict[str, object]:
    cells = []
    episode_plan = []
    for host, runtime_character in (("claude_code", "b"), ("hermes_agent", "c")):
        for condition, artifact_character in (("baseline", "d"), ("alpha1", "e"), ("alpha2", "f")):
            episode_id = f"{host}-{condition}-task-1-repeat-1"
            host_command = (
                f"docker run --rm {host} --condition {condition} {{episode_input_path}} {{episode_output_path}}"
            )
            cells.append(
                {
                    "host": host,
                    "condition": condition,
                    "runtime_digest": digest(runtime_character),
                    "intervention_digest": digest(artifact_character),
                    "host_binding_digest": digest(f"{runtime_character}{artifact_character}"[0]),
                    "guest_rootfs_digest": digest(f"{artifact_character}{runtime_character}"[0]),
                    "host_package_digest": digest("8" if host == "claude_code" else "9"),
                    "host_settings_digest": digest("a" if host == "claude_code" else "b"),
                    "host_hooks_digest": digest("c" if host == "claude_code" else "d"),
                    "environment_digest": digest("e" if host == "claude_code" else "f"),
                    "host_command": host_command,
                    "host_command_digest": text_digest(host_command),
                }
            )
            episode_plan.append(
                {
                    "episode_id": episode_id,
                    "task_id": "opaque-task-1",
                    "host": host,
                    "condition": condition,
                    "repeat": 1,
                    "role": "primary",
                    "runner_input_digest": digest("1"),
                    "synthetic_user_assignment_digest": digest("7"),
                }
            )
    return {
        "schema_version": 1,
        "benchmark_id": "paired-research-v1",
        "phase": phase,
        "model": {"id": "deepseek-v4-flash", "version": "DeepSeek-V4-Flash-0731"},
        "cells": cells,
        "episode_plan": episode_plan,
        "task_plan_digest": digest("2"),
        "task_budget": {
            "primary_unique_tasks": 1,
            "reliability_unique_tasks": 0,
            "reliability_repeats": 0,
            "integrity_unique_tasks": 0,
            "integrity_repeats": 0,
        },
        "randomization": {"seed_commitment": digest("3"), "unblind_after": "all-episodes-complete"},
        "corpus": {
            "revision": "corpus-test-v1",
            "sampling_seed": "seed-test-v1",
            "strata_digest": digest("a"),
            "deterministic_case_set_digest": digest("b"),
            "dynamic_sampling_policy": "stratified-after-deterministic",
        },
        "execution_envelope": {
            "isolation_profile": "docker-internal-network-v1",
            "raw_artifact_root": ".research-tree/evaluation-runs/test",
            "tool_recording_mode": "captured",
            "live_web_variation_policy": "report-as-environmental-variation",
        },
        "metrics": {
            "metric_catalog_digest": digest("c"),
            "quality_aggregation": "host-specific-paired-task-mean",
            "missing_data_rule": "retain-failure-and-exclude-no-cell",
            "confidence_interval_method": "stratified-bootstrap-and-sign-flip",
            "integrity_separate": True,
        },
        "review": {
            "protocol": "blinded-independent-review-v1",
            "reviewer_assignment_digest": digest("d"),
            "disagreement_retention": "retain-and-report-inter-rater-agreement",
        },
        "budget": {"currency": "CNY", "maximum_cost": 50.0, "failure_treatment": "report-without-exclusion"},
        "source_access": {
            "mode": "live-capture-proxy",
            "replay_mode": "after-live-only",
            "direct_runner_egress": False,
        },
        "synthetic_user": {
            "enabled": True,
            "evidence_kind": "synthetic-user-proxy",
            "human_experience_status": "unavailable",
            "persona_set_digest": digest("4"),
            "prompt_family_digest": digest("5"),
            "heldout_task_set_digest": digest("6"),
            "assignment_digest": digest("7"),
            "persona_prompt_location": "evaluator-owned",
            "persona_prompt_task_binding": "task-agnostic",
            "holdout_policy": "tasks-held-out-from-harness-development",
            "assignment_visibility": "evaluator-only-until-unblind",
            "simulator_service": "separate-network-service",
            "simulator_model": "deepseek-v4-flash",
            "review_blinding": "arm-and-host-hidden",
            "scoring_separation": "synthetic-user-cannot-score",
            "turn_limit": 8,
        },
        "human_evidence_status": "unavailable",
    }


def records(manifest: dict[str, object]) -> dict[str, object]:
    quality_by_condition = {"baseline": 0.4, "alpha1": 0.5, "alpha2": 0.7}
    return {
        "schema_version": 1,
        "records": [
            {
                "episode_id": entry["episode_id"],
                "status": "completed",
                "quality_score": quality_by_condition[entry["condition"]],
                "source_capture_digest": digest("5"),
                "transcript_digest": digest("6"),
                "token_usage": {
                    "cache_hit_input_tokens": 700,
                    "cache_miss_input_tokens": 300,
                    "output_tokens": 100,
                },
                "integrity": {
                    "completion_forgery": False,
                    "correction_regression": False,
                    "unresolved_evidence": False,
                    "source_capture_missing": False,
                },
                "synthetic_user": {
                    "evidence_kind": "synthetic-user-proxy",
                    "human_experience_status": "unavailable",
                    "turn_count": 2,
                    "canary_status": "clear",
                    "assignment_digest": entry["synthetic_user_assignment_digest"],
                    "session_receipt_digest": digest("8"),
                },
                "quality_assessment": {
                    "protocol": "blinded-independent-review-v1",
                    "review_bundle_digest": digest("9"),
                    "reviewer_assignment_digest": digest("a"),
                    "arm_and_host_hidden": True,
                    "synthetic_user_scored": False,
                    "review_attestation": review_score_attestation(
                        REVIEW_KEY,
                        episode_id=entry["episode_id"],
                        quality_score=quality_by_condition[entry["condition"]],
                        review_bundle_digest=digest("9"),
                        reviewer_assignment_digest=digest("a"),
                    ),
                },
            }
            for entry in manifest["episode_plan"]
        ],
    }


def test_analyze_benchmark_keeps_hosts_separate_and_reports_measured_usage() -> None:
    manifest = sealed_manifest()

    result = analyze_benchmark(
        manifest,
        records(manifest),
        review_attestation_key=REVIEW_KEY,
        bootstrap_samples=100,
        permutations=100,
    )

    assert result["status"] == "analyzed"
    assert result["evidence_kind"] == "synthetic-user-proxy"
    assert result["human_evidence_status"] == "unavailable"
    assert {entry["host"] for entry in result["contrasts"]} == {"claude_code", "hermes_agent"}
    assert {entry["comparison"] for entry in result["contrasts"]} == {"alpha1", "alpha2"}
    assert result["token_usage"]["measurement_status"] == "measured-from-provider-usage"
    assert result["token_usage"]["estimated_cost_cny"] > 0


def test_manifest_rejects_private_prompts_and_unpaired_cells() -> None:
    leaking = sealed_manifest()
    leaking["private_prompt"] = "do not track this"
    with pytest.raises(PairedBenchmarkError, match="private"):
        validate_sealed_manifest(leaking)

    unpaired = sealed_manifest()
    unpaired["episode_plan"] = unpaired["episode_plan"][:-1]
    with pytest.raises(PairedBenchmarkError, match="paired"):
        validate_sealed_manifest(unpaired)

    mismatched_input = sealed_manifest()
    mismatched_input["episode_plan"][0]["runner_input_digest"] = digest("b")
    with pytest.raises(PairedBenchmarkError, match="identical runner input"):
        validate_sealed_manifest(mismatched_input)

    mismatched_persona = sealed_manifest()
    mismatched_persona["episode_plan"][0]["synthetic_user_assignment_digest"] = digest("c")
    with pytest.raises(PairedBenchmarkError, match="same synthetic-user assignment"):
        validate_sealed_manifest(mismatched_persona)

    mismatched_intervention = sealed_manifest()
    mismatched_intervention["cells"][0]["intervention_digest"] = digest("c")
    with pytest.raises(PairedBenchmarkError, match="same frozen intervention"):
        validate_sealed_manifest(mismatched_intervention)

    mismatched_runtime = sealed_manifest()
    mismatched_runtime["cells"][0]["runtime_digest"] = digest("d")
    with pytest.raises(PairedBenchmarkError, match="frozen runtime"):
        validate_sealed_manifest(mismatched_runtime)

    tampered_command = sealed_manifest()
    tampered_command["cells"][0]["host_command"] = "tampered {episode_input_path} {episode_output_path}"
    with pytest.raises(PairedBenchmarkError, match="command digest"):
        validate_sealed_manifest(tampered_command)

    direct_egress = sealed_manifest()
    direct_egress["execution_envelope"]["raw_artifact_root"] = "evaluation/results"
    with pytest.raises(PairedBenchmarkError, match="disposable evaluation runs"):
        validate_sealed_manifest(direct_egress)


def test_results_reject_runner_supplied_arm_identity_and_integrity_failure() -> None:
    manifest = sealed_manifest()
    identity_leak = records(manifest)
    identity_leak["records"][0]["condition"] = "alpha2"
    with pytest.raises(PairedBenchmarkError, match="arm identity"):
        analyze_benchmark(
            manifest,
            identity_leak,
            review_attestation_key=REVIEW_KEY,
            bootstrap_samples=20,
            permutations=20,
        )

    failed = records(manifest)
    failed["records"][0]["integrity"]["completion_forgery"] = True
    result = analyze_benchmark(
        manifest,
        failed,
        review_attestation_key=REVIEW_KEY,
        bootstrap_samples=20,
        permutations=20,
    )
    assert result["status"] == "failed-integrity"
    assert result["integrity_failures"] == ["completion_forgery"]

    simulated_scoring = records(manifest)
    simulated_scoring["records"][0]["quality_assessment"]["synthetic_user_scored"] = True
    with pytest.raises(PairedBenchmarkError, match="cannot score"):
        analyze_benchmark(
            manifest,
            simulated_scoring,
            review_attestation_key=REVIEW_KEY,
            bootstrap_samples=20,
            permutations=20,
        )


def test_results_reject_a_score_or_review_digest_changed_after_attestation() -> None:
    manifest = sealed_manifest()
    tampered_score = records(manifest)
    tampered_score["records"][0]["quality_score"] = 0.9
    with pytest.raises(PairedBenchmarkError, match="attestation"):
        analyze_benchmark(
            manifest,
            tampered_score,
            review_attestation_key=REVIEW_KEY,
            bootstrap_samples=20,
            permutations=20,
        )

    tampered_review = records(manifest)
    tampered_review["records"][0]["quality_assessment"]["review_bundle_digest"] = digest("b")
    with pytest.raises(PairedBenchmarkError, match="attestation"):
        analyze_benchmark(
            manifest,
            tampered_review,
            review_attestation_key=REVIEW_KEY,
            bootstrap_samples=20,
            permutations=20,
        )


def test_sealed_final_requires_the_predeclared_sample_and_reliability_panel() -> None:
    final_manifest = sealed_manifest(phase="sealed-final")
    final_manifest["task_budget"] = {
        "primary_unique_tasks": 80,
        "reliability_unique_tasks": 20,
        "reliability_repeats": 5,
        "integrity_unique_tasks": 12,
        "integrity_repeats": 5,
    }

    with pytest.raises(PairedBenchmarkError, match="sealed-final"):
        validate_sealed_manifest(final_manifest)


def test_unavailable_report_makes_no_quality_or_human_claim() -> None:
    report = benchmark_unavailable("sealed inputs have not been supplied")

    assert report == {
        "status": "unavailable",
        "evidence_kind": "synthetic-user-proxy",
        "human_evidence_status": "unavailable",
        "reason": "sealed inputs have not been supplied",
    }
