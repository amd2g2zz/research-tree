"""Deterministic, host-stratified paired analysis for benchmark measurements."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from math import ceil, floor, isclose, isfinite
from numbers import Real
from random import Random
from statistics import fmean
from typing import TypeAlias


__all__ = [
    "BootstrapConfidenceInterval",
    "HostPairedAnalysis",
    "PairedMeasurement",
    "PairedStatisticsError",
    "PairedTaskDifference",
    "analyze_paired_rows",
    "holm_adjust",
    "paired_task_differences",
    "sign_flip_permutation_p_values",
    "sign_flip_p_values",
    "stratified_paired_bootstrap",
    "validate_balanced_rows",
]


REQUIRED_ROW_FIELDS = frozenset({"host", "task", "condition", "repeat", "value"})
RepeatIdentifier: TypeAlias = str | int


class PairedStatisticsError(ValueError):
    """Raised when paired benchmark data or analysis parameters are invalid."""


@dataclass(frozen=True, slots=True)
class PairedMeasurement:
    """One repeat-level benchmark measurement with an explicit pairing key."""

    host: str
    task: str
    condition: str
    repeat: RepeatIdentifier
    value: float


RowInput: TypeAlias = PairedMeasurement | Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PairedTaskDifference:
    """The repeat-aggregated comparison for one task within one host."""

    host: str
    task: str
    baseline_mean: float
    comparison_mean: float
    difference: float
    repeat_count: int


@dataclass(frozen=True, slots=True)
class BootstrapConfidenceInterval:
    """A percentile confidence interval from a paired task bootstrap."""

    confidence_level: float
    lower: float
    upper: float


@dataclass(frozen=True, slots=True)
class HostPairedAnalysis:
    """All paired statistics for one host, without cross-host pooling."""

    host: str
    baseline_condition: str
    comparison_condition: str
    task_differences: tuple[PairedTaskDifference, ...]
    mean_difference: float
    bootstrap_ci: BootstrapConfidenceInterval
    raw_p_value: float
    holm_adjusted_p_value: float


def validate_balanced_rows(
    rows: Iterable[RowInput], *, conditions: Sequence[str] | None = None
) -> tuple[PairedMeasurement, ...]:
    """Validate a complete host/task/condition/repeat grid and return sorted rows.

    Balance is assessed independently for every host. Each selected condition must
    contain the same task identifiers, and each task must contain the same repeat
    identifiers in every selected condition. Supplying ``conditions`` permits a
    selected pair to be checked within a wider multi-condition data set.
    """

    selected_rows, _, _ = _balanced_grid(rows, conditions=conditions)
    return selected_rows


def paired_task_differences(
    rows: Iterable[RowInput], *, baseline_condition: str, comparison_condition: str
) -> tuple[PairedTaskDifference, ...]:
    """Aggregate repeats and calculate ``comparison - baseline`` for each task.

    The returned differences are ordered by host and task. A host is never used as
    another host's task stratum, so different hosts may have different valid task
    sets without being pooled.
    """

    baseline, comparison = _comparison_conditions(baseline_condition, comparison_condition)
    _, grid, _ = _balanced_grid(rows, conditions=(baseline, comparison))
    differences: list[PairedTaskDifference] = []
    for host in sorted(grid):
        baseline_tasks = grid[host][baseline]
        comparison_tasks = grid[host][comparison]
        for task in sorted(baseline_tasks):
            repeat_identifiers = sorted(baseline_tasks[task], key=_repeat_sort_key)
            baseline_mean = fmean([baseline_tasks[task][repeat_identifier] for repeat_identifier in repeat_identifiers])
            comparison_mean = fmean(
                [comparison_tasks[task][repeat_identifier] for repeat_identifier in repeat_identifiers]
            )
            differences.append(
                PairedTaskDifference(
                    host=host,
                    task=task,
                    baseline_mean=baseline_mean,
                    comparison_mean=comparison_mean,
                    difference=comparison_mean - baseline_mean,
                    repeat_count=len(repeat_identifiers),
                )
            )
    return tuple(differences)


def stratified_paired_bootstrap(
    task_differences: Iterable[PairedTaskDifference],
    *,
    bootstrap_samples: int = 10_000,
    confidence_level: float = 0.95,
    seed: int = 0,
) -> dict[str, BootstrapConfidenceInterval]:
    """Return one percentile paired-bootstrap interval per host.

    Each bootstrap replicate samples complete task differences with replacement
    within a host. The function intentionally returns no combined interval.
    """

    samples = _require_positive_int(bootstrap_samples, "bootstrap_samples")
    level = _require_confidence_level(confidence_level)
    base_seed = _require_seed(seed)
    grouped_differences = _group_task_differences(task_differences)
    lower_quantile = (1.0 - level) / 2.0
    upper_quantile = 1.0 - lower_quantile
    intervals: dict[str, BootstrapConfidenceInterval] = {}
    for host, host_differences in grouped_differences.items():
        difference_values = [task_difference.difference for task_difference in host_differences]
        task_count = len(difference_values)
        random_generator = Random(_derive_seed(base_seed, "bootstrap", host))
        bootstrap_means: list[float] = []
        for bootstrap_index in range(samples):
            bootstrap_means.append(
                fmean(difference_values[random_generator.randrange(task_count)] for draw_index in range(task_count))
            )
        bootstrap_means.sort()
        intervals[host] = BootstrapConfidenceInterval(
            confidence_level=level,
            lower=_percentile(bootstrap_means, lower_quantile),
            upper=_percentile(bootstrap_means, upper_quantile),
        )
    return intervals


def sign_flip_permutation_p_values(
    task_differences: Iterable[PairedTaskDifference], *, permutations: int = 10_000, seed: int = 0
) -> dict[str, float]:
    """Estimate two-sided sign-flip permutation p-values independently per host.

    The add-one correction keeps the estimate nonzero and well-defined for a
    finite seeded Monte Carlo sample.
    """

    permutation_count = _require_positive_int(permutations, "permutations")
    base_seed = _require_seed(seed)
    grouped_differences = _group_task_differences(task_differences)
    p_values: dict[str, float] = {}
    for host, host_differences in grouped_differences.items():
        difference_values = [task_difference.difference for task_difference in host_differences]
        observed_magnitude = abs(fmean(difference_values))
        random_generator = Random(_derive_seed(base_seed, "sign-flip", host))
        extreme_count = 0
        for permutation_index in range(permutation_count):
            permuted_mean = fmean(
                difference if random_generator.getrandbits(1) else -difference for difference in difference_values
            )
            permuted_magnitude = abs(permuted_mean)
            if permuted_magnitude > observed_magnitude or isclose(
                permuted_magnitude, observed_magnitude, rel_tol=1e-12, abs_tol=1e-15
            ):
                extreme_count += 1
        p_values[host] = (extreme_count + 1) / (permutation_count + 1)
    return p_values


def sign_flip_p_values(
    task_differences: Iterable[PairedTaskDifference], *, permutations: int = 10_000, seed: int = 0
) -> dict[str, float]:
    """Alias for :func:`sign_flip_permutation_p_values`."""

    return sign_flip_permutation_p_values(task_differences, permutations=permutations, seed=seed)


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """Apply the Holm step-down adjustment to named p-values deterministically."""

    if not isinstance(p_values, Mapping):
        raise PairedStatisticsError("p_values must be a mapping of hypothesis names to p-values")
    normalized_values = {
        _require_identifier(hypothesis, "hypothesis name"): _require_probability(value, "p-value")
        for hypothesis, value in p_values.items()
    }
    ranked_values = sorted(normalized_values.items(), key=lambda item: (item[1], item[0]))
    adjusted_values: dict[str, float] = {}
    previous_adjustment = 0.0
    hypothesis_count = len(ranked_values)
    for rank, (hypothesis, p_value) in enumerate(ranked_values):
        adjustment = min(1.0, (hypothesis_count - rank) * p_value)
        previous_adjustment = max(previous_adjustment, adjustment)
        adjusted_values[hypothesis] = previous_adjustment
    return {hypothesis: adjusted_values[hypothesis] for hypothesis in sorted(adjusted_values)}


def analyze_paired_rows(
    rows: Iterable[RowInput],
    *,
    baseline_condition: str,
    comparison_condition: str,
    bootstrap_samples: int = 10_000,
    confidence_level: float = 0.95,
    permutations: int = 10_000,
    seed: int = 0,
) -> tuple[HostPairedAnalysis, ...]:
    """Run the complete host-stratified paired analysis for one condition contrast.

    Holm adjustment is applied to the separate host-level p-values only. Raw
    observations, task differences, means, and confidence intervals remain
    strictly host-specific.
    """

    baseline, comparison = _comparison_conditions(baseline_condition, comparison_condition)
    task_differences = paired_task_differences(rows, baseline_condition=baseline, comparison_condition=comparison)
    grouped_differences = _group_task_differences(task_differences)
    bootstrap_intervals = stratified_paired_bootstrap(
        task_differences,
        bootstrap_samples=bootstrap_samples,
        confidence_level=confidence_level,
        seed=seed,
    )
    raw_p_values = sign_flip_permutation_p_values(task_differences, permutations=permutations, seed=seed)
    adjusted_p_values = holm_adjust(raw_p_values)
    return tuple(
        HostPairedAnalysis(
            host=host,
            baseline_condition=baseline,
            comparison_condition=comparison,
            task_differences=host_differences,
            mean_difference=fmean([task_difference.difference for task_difference in host_differences]),
            bootstrap_ci=bootstrap_intervals[host],
            raw_p_value=raw_p_values[host],
            holm_adjusted_p_value=adjusted_p_values[host],
        )
        for host, host_differences in grouped_differences.items()
    )


def _balanced_grid(
    rows: Iterable[RowInput], *, conditions: Sequence[str] | None
) -> tuple[
    tuple[PairedMeasurement, ...],
    dict[str, dict[str, dict[str, dict[RepeatIdentifier, float]]]],
    tuple[str, ...],
]:
    observations = _coerce_rows(rows)
    selected_conditions = _normalize_conditions(observations, conditions)
    selected_rows = tuple(
        sorted(
            (observation for observation in observations if observation.condition in selected_conditions),
            key=_measurement_sort_key,
        )
    )
    grid: dict[str, dict[str, dict[str, dict[RepeatIdentifier, float]]]] = {}
    for observation in selected_rows:
        host_grid = grid.setdefault(observation.host, {})
        condition_grid = host_grid.setdefault(observation.condition, {})
        task_grid = condition_grid.setdefault(observation.task, {})
        task_grid[observation.repeat] = observation.value
    for host in sorted({observation.host for observation in observations}):
        host_grid = grid.get(host, {})
        for condition in selected_conditions:
            if condition not in host_grid:
                raise PairedStatisticsError(f"host {host!r} is missing condition {condition!r}")
        reference_condition = selected_conditions[0]
        reference_tasks = set(host_grid[reference_condition])
        for condition in selected_conditions[1:]:
            if set(host_grid[condition]) != reference_tasks:
                raise PairedStatisticsError(
                    f"host {host!r} has imbalanced task rows between {reference_condition!r} and {condition!r}"
                )
        for task in sorted(reference_tasks):
            reference_repeats = set(host_grid[reference_condition][task])
            for condition in selected_conditions[1:]:
                if set(host_grid[condition][task]) != reference_repeats:
                    raise PairedStatisticsError(
                        f"host {host!r} task {task!r} has imbalanced repeat rows between "
                        f"{reference_condition!r} and {condition!r}"
                    )
    return selected_rows, grid, selected_conditions


def _coerce_rows(rows: Iterable[RowInput]) -> tuple[PairedMeasurement, ...]:
    try:
        raw_rows = tuple(rows)
    except TypeError as error:
        raise PairedStatisticsError("rows must be an iterable of measurements") from error
    if not raw_rows:
        raise PairedStatisticsError("rows must contain at least one measurement")
    observations: list[PairedMeasurement] = []
    seen_keys: set[tuple[str, str, str, RepeatIdentifier]] = set()
    for row_index, raw_row in enumerate(raw_rows):
        if isinstance(raw_row, PairedMeasurement):
            candidate = raw_row
        elif isinstance(raw_row, Mapping):
            missing_fields = sorted(REQUIRED_ROW_FIELDS.difference(raw_row))
            if missing_fields:
                raise PairedStatisticsError(f"row {row_index} is missing required fields: {', '.join(missing_fields)}")
            candidate = PairedMeasurement(
                host=raw_row["host"],
                task=raw_row["task"],
                condition=raw_row["condition"],
                repeat=raw_row["repeat"],
                value=raw_row["value"],
            )
        else:
            raise PairedStatisticsError(f"row {row_index} must be a PairedMeasurement or mapping")
        observation = _normalize_measurement(candidate, row_index)
        observation_key = (observation.host, observation.task, observation.condition, observation.repeat)
        if observation_key in seen_keys:
            raise PairedStatisticsError(
                "duplicate measurement for "
                f"host={observation.host!r}, task={observation.task!r}, "
                f"condition={observation.condition!r}, repeat={observation.repeat!r}"
            )
        seen_keys.add(observation_key)
        observations.append(observation)
    return tuple(observations)


def _normalize_measurement(measurement: PairedMeasurement, row_index: int) -> PairedMeasurement:
    return PairedMeasurement(
        host=_require_identifier(measurement.host, f"row {row_index} host"),
        task=_require_identifier(measurement.task, f"row {row_index} task"),
        condition=_require_identifier(measurement.condition, f"row {row_index} condition"),
        repeat=_require_repeat_identifier(measurement.repeat, f"row {row_index} repeat"),
        value=_require_finite_real(measurement.value, f"row {row_index} value"),
    )


def _normalize_conditions(
    observations: Sequence[PairedMeasurement], conditions: Sequence[str] | None
) -> tuple[str, ...]:
    if conditions is None:
        selected_conditions = tuple(sorted({observation.condition for observation in observations}))
    else:
        if isinstance(conditions, str) or not isinstance(conditions, Sequence):
            raise PairedStatisticsError("conditions must be a sequence of condition names")
        selected_conditions = tuple(_require_identifier(condition, "condition name") for condition in conditions)
    if len(selected_conditions) < 2:
        raise PairedStatisticsError("at least two conditions are required for paired analysis")
    if len(set(selected_conditions)) != len(selected_conditions):
        raise PairedStatisticsError("conditions must not contain duplicates")
    available_conditions = {observation.condition for observation in observations}
    missing_conditions = sorted(set(selected_conditions).difference(available_conditions))
    if missing_conditions:
        raise PairedStatisticsError(
            f"requested conditions are absent: {', '.join(repr(item) for item in missing_conditions)}"
        )
    return selected_conditions


def _comparison_conditions(baseline_condition: str, comparison_condition: str) -> tuple[str, str]:
    baseline = _require_identifier(baseline_condition, "baseline_condition")
    comparison = _require_identifier(comparison_condition, "comparison_condition")
    if baseline == comparison:
        raise PairedStatisticsError("baseline_condition and comparison_condition must differ")
    return baseline, comparison


def _measurement_sort_key(measurement: PairedMeasurement) -> tuple[str, str, str, tuple[int, str | int]]:
    return measurement.host, measurement.task, measurement.condition, _repeat_sort_key(measurement.repeat)


def _repeat_sort_key(repeat: RepeatIdentifier) -> tuple[int, str | int]:
    if isinstance(repeat, int):
        return 0, repeat
    return 1, repeat


def _group_task_differences(
    task_differences: Iterable[PairedTaskDifference],
) -> dict[str, tuple[PairedTaskDifference, ...]]:
    try:
        raw_differences = tuple(task_differences)
    except TypeError as error:
        raise PairedStatisticsError("task_differences must be an iterable of PairedTaskDifference values") from error
    if not raw_differences:
        raise PairedStatisticsError("task_differences must contain at least one task")
    grouped_lists: dict[str, list[PairedTaskDifference]] = {}
    seen_keys: set[tuple[str, str]] = set()
    for difference_index, raw_difference in enumerate(raw_differences):
        if not isinstance(raw_difference, PairedTaskDifference):
            raise PairedStatisticsError(f"task difference {difference_index} must be a PairedTaskDifference")
        normalized_difference = PairedTaskDifference(
            host=_require_identifier(raw_difference.host, f"task difference {difference_index} host"),
            task=_require_identifier(raw_difference.task, f"task difference {difference_index} task"),
            baseline_mean=_require_finite_real(
                raw_difference.baseline_mean, f"task difference {difference_index} baseline_mean"
            ),
            comparison_mean=_require_finite_real(
                raw_difference.comparison_mean, f"task difference {difference_index} comparison_mean"
            ),
            difference=_require_finite_real(
                raw_difference.difference, f"task difference {difference_index} difference"
            ),
            repeat_count=_require_positive_int(
                raw_difference.repeat_count, f"task difference {difference_index} repeat_count"
            ),
        )
        difference_key = (normalized_difference.host, normalized_difference.task)
        if difference_key in seen_keys:
            raise PairedStatisticsError(
                f"duplicate task difference for host={normalized_difference.host!r}, task={normalized_difference.task!r}"
            )
        seen_keys.add(difference_key)
        grouped_lists.setdefault(normalized_difference.host, []).append(normalized_difference)
    return {
        host: tuple(sorted(host_differences, key=lambda task_difference: task_difference.task))
        for host, host_differences in sorted(grouped_lists.items())
    }


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if not sorted_values:
        raise PairedStatisticsError("cannot calculate a percentile of an empty sample")
    position = (len(sorted_values) - 1) * quantile
    lower_index = floor(position)
    upper_index = ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    proportion = position - lower_index
    return sorted_values[lower_index] + proportion * (sorted_values[upper_index] - sorted_values[lower_index])


def _derive_seed(seed: int, purpose: str, host: str) -> int:
    payload = f"{seed}\x1f{purpose}\x1f{host}".encode("utf-8")
    return int.from_bytes(sha256(payload).digest()[:16], "big")


def _require_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PairedStatisticsError(f"{label} must be a non-empty string")
    return value


def _require_repeat_identifier(value: object, label: str) -> RepeatIdentifier:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise PairedStatisticsError(f"{label} must be a non-boolean string or integer")
    if isinstance(value, str) and not value.strip():
        raise PairedStatisticsError(f"{label} must be a non-empty string")
    return value


def _require_finite_real(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise PairedStatisticsError(f"{label} must be a finite real number")
    numeric_value = float(value)
    if not isfinite(numeric_value):
        raise PairedStatisticsError(f"{label} must be a finite real number")
    return numeric_value


def _require_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PairedStatisticsError(f"{label} must be a positive integer")
    return value


def _require_confidence_level(value: object) -> float:
    confidence_level = _require_finite_real(value, "confidence_level")
    if not 0.0 < confidence_level < 1.0:
        raise PairedStatisticsError("confidence_level must be strictly between zero and one")
    return confidence_level


def _require_seed(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PairedStatisticsError("seed must be an integer")
    return value


def _require_probability(value: object, label: str) -> float:
    probability = _require_finite_real(value, label)
    if not 0.0 <= probability <= 1.0:
        raise PairedStatisticsError(f"{label} must be between zero and one")
    return probability
