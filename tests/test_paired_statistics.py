from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def statistics_module():
    spec = importlib.util.spec_from_file_location("paired_statistics", ROOT / "evaluation/harness/paired_statistics.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


STATISTICS = statistics_module()
PairedStatisticsError = STATISTICS.PairedStatisticsError
analyze_paired_rows = STATISTICS.analyze_paired_rows
holm_adjust = STATISTICS.holm_adjust
paired_task_differences = STATISTICS.paired_task_differences
sign_flip_permutation_p_values = STATISTICS.sign_flip_permutation_p_values
stratified_paired_bootstrap = STATISTICS.stratified_paired_bootstrap
validate_balanced_rows = STATISTICS.validate_balanced_rows


def measurement(host: str, task: str, condition: str, repeat: int, value: float) -> dict[str, object]:
    return {
        "host": host,
        "task": task,
        "condition": condition,
        "repeat": repeat,
        "value": value,
    }


def balanced_rows() -> list[dict[str, object]]:
    return [
        measurement("alpha", "task-1", "baseline", 1, 1.0),
        measurement("alpha", "task-1", "baseline", 2, 3.0),
        measurement("alpha", "task-1", "candidate", 1, 6.0),
        measurement("alpha", "task-1", "candidate", 2, 8.0),
        measurement("alpha", "task-2", "baseline", 1, 10.0),
        measurement("alpha", "task-2", "baseline", 2, 14.0),
        measurement("alpha", "task-2", "candidate", 1, 16.0),
        measurement("alpha", "task-2", "candidate", 2, 20.0),
        measurement("beta", "task-1", "baseline", 1, 20.0),
        measurement("beta", "task-1", "baseline", 2, 24.0),
        measurement("beta", "task-1", "candidate", 1, 14.0),
        measurement("beta", "task-1", "candidate", 2, 18.0),
        measurement("beta", "task-2", "baseline", 1, 4.0),
        measurement("beta", "task-2", "baseline", 2, 8.0),
        measurement("beta", "task-2", "candidate", 1, 7.0),
        measurement("beta", "task-2", "candidate", 2, 9.0),
    ]


def fixed_effect_rows() -> list[dict[str, object]]:
    return [
        measurement("alpha", "task-1", "baseline", 1, 1.0),
        measurement("alpha", "task-1", "candidate", 1, 11.0),
        measurement("alpha", "task-2", "baseline", 1, 4.0),
        measurement("alpha", "task-2", "candidate", 1, 14.0),
        measurement("beta", "task-1", "baseline", 1, 20.0),
        measurement("beta", "task-1", "candidate", 1, 10.0),
        measurement("beta", "task-2", "baseline", 1, 30.0),
        measurement("beta", "task-2", "candidate", 1, 20.0),
    ]


def test_repeat_aggregation_produces_sorted_per_task_differences() -> None:
    validated = validate_balanced_rows(balanced_rows(), conditions=("baseline", "candidate"))
    differences = paired_task_differences(validated, baseline_condition="baseline", comparison_condition="candidate")

    assert [(item.host, item.task, item.repeat_count) for item in differences] == [
        ("alpha", "task-1", 2),
        ("alpha", "task-2", 2),
        ("beta", "task-1", 2),
        ("beta", "task-2", 2),
    ]
    assert [item.baseline_mean for item in differences] == [2.0, 12.0, 22.0, 6.0]
    assert [item.comparison_mean for item in differences] == [7.0, 18.0, 16.0, 8.0]
    assert [item.difference for item in differences] == [5.0, 6.0, -6.0, 2.0]


def test_validation_rejects_missing_fields_duplicate_rows_and_imbalanced_pairs() -> None:
    missing_value = measurement("alpha", "task-1", "baseline", 1, 1.0)
    del missing_value["value"]
    with pytest.raises(PairedStatisticsError, match="missing required fields: value"):
        validate_balanced_rows([missing_value, measurement("alpha", "task-1", "candidate", 1, 2.0)])

    duplicate_rows = balanced_rows()
    duplicate_rows.append(measurement("alpha", "task-1", "baseline", 1, 1.0))
    with pytest.raises(PairedStatisticsError, match="duplicate measurement"):
        validate_balanced_rows(duplicate_rows, conditions=("baseline", "candidate"))

    missing_task_rows = [
        item
        for item in balanced_rows()
        if not (item["host"] == "alpha" and item["task"] == "task-2" and item["condition"] == "candidate")
    ]
    with pytest.raises(PairedStatisticsError, match="imbalanced task rows"):
        validate_balanced_rows(missing_task_rows, conditions=("baseline", "candidate"))

    mismatched_repeats = balanced_rows()
    for item in mismatched_repeats:
        if (
            item["host"] == "beta"
            and item["task"] == "task-1"
            and item["condition"] == "candidate"
            and item["repeat"] == 2
        ):
            item["repeat"] = 3
    with pytest.raises(PairedStatisticsError, match="imbalanced repeat rows"):
        validate_balanced_rows(mismatched_repeats, conditions=("baseline", "candidate"))


def test_analysis_keeps_bootstrap_intervals_and_means_within_each_host() -> None:
    analyses = analyze_paired_rows(
        fixed_effect_rows(),
        baseline_condition="baseline",
        comparison_condition="candidate",
        bootstrap_samples=128,
        permutations=128,
        seed=17,
    )

    assert [analysis.host for analysis in analyses] == ["alpha", "beta"]
    assert [analysis.mean_difference for analysis in analyses] == [10.0, -10.0]
    assert [(analysis.bootstrap_ci.lower, analysis.bootstrap_ci.upper) for analysis in analyses] == [
        (10.0, 10.0),
        (-10.0, -10.0),
    ]
    assert all(len(analysis.task_differences) == 2 for analysis in analyses)


def test_seeded_bootstrap_and_sign_flip_are_reproducible_per_host() -> None:
    differences = paired_task_differences(
        balanced_rows(), baseline_condition="baseline", comparison_condition="candidate"
    )

    first_intervals = stratified_paired_bootstrap(differences, bootstrap_samples=257, confidence_level=0.9, seed=42)
    second_intervals = stratified_paired_bootstrap(differences, bootstrap_samples=257, confidence_level=0.9, seed=42)
    first_p_values = sign_flip_permutation_p_values(differences, permutations=257, seed=42)
    second_p_values = sign_flip_permutation_p_values(differences, permutations=257, seed=42)

    assert first_intervals == second_intervals
    assert first_p_values == second_p_values
    assert set(first_intervals) == {"alpha", "beta"}
    assert all(0.0 < p_value <= 1.0 for p_value in first_p_values.values())


def test_holm_adjustment_is_monotonic_in_ranked_order() -> None:
    adjusted = holm_adjust({"second": 0.04, "first": 0.01, "third": 0.03})

    assert adjusted == {"first": 0.03, "second": 0.06, "third": 0.06}


def test_invalid_analysis_parameters_and_conditions_are_rejected() -> None:
    differences = paired_task_differences(
        balanced_rows(), baseline_condition="baseline", comparison_condition="candidate"
    )

    with pytest.raises(PairedStatisticsError, match="bootstrap_samples must be a positive integer"):
        stratified_paired_bootstrap(differences, bootstrap_samples=0)
    with pytest.raises(PairedStatisticsError, match="seed must be an integer"):
        sign_flip_permutation_p_values(differences, seed=True)
    with pytest.raises(PairedStatisticsError, match="must differ"):
        analyze_paired_rows(
            balanced_rows(),
            baseline_condition="baseline",
            comparison_condition="baseline",
            bootstrap_samples=4,
            permutations=4,
        )
