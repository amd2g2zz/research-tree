"""Frozen semantic evaluation metric definitions and manifest integrity."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
from typing import Any, Mapping, Sequence

from .contracts import canonical_json_bytes


class MetricError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    name: str
    numerator: str
    denominator: str
    unit: str
    aggregation: str
    unavailable: str
    evidence_path: str
    absolute_threshold: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FROZEN_METRICS = {
    name: MetricDefinition(name, terms[0], terms[1], "ratio", "sum_case_numerators/sum_case_denominators", "not_applicable excluded from denominator", "evaluation/results/{case_id}.json", 0.0 if name == "false_completion" else None)
    for name, terms in {
        "intent_fidelity": ("accepted material intent fields", "material intent fields"),
        "premature_handoff": ("handoffs before readiness", "eligible runs"),
        "unsupported_claim": ("claims without evidence/oracle", "consequential claims"),
        "false_completion": ("hard-gate violations on completed runs", "eligible runs"),
        "p0_closure": ("P0 slots with current closure token", "active P0 slots"),
        "recovery_loss": ("obligations absent after replay", "obligations before crash"),
        "host_parity": ("semantically equal canonical digests", "equivalent host traces"),
        "implementation_success": ("runners satisfying task oracle", "implementation cases"),
        "rediscovery_burden": ("repeated acquisition actions", "acquisition actions"),
        "human_acceptance": ("accepted exact delivery pairs", "submitted exact delivery pairs"),
    }.items()
}


def evaluate_metric(name: str, cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if name not in FROZEN_METRICS:
        raise MetricError(f"unknown frozen metric: {name}")
    numerator = denominator = 0.0
    unavailable: list[dict[str, str]] = []
    evidence_paths: list[str] = []
    for case in cases:
        case_id = str(case.get("case_id", "unknown"))
        if case.get("status") in {"not_applicable", "unavailable"}:
            unavailable.append({"case_id": case_id, "reason": str(case.get("reason", "not applicable"))})
            continue
        try:
            case_numerator = float(case["numerator"])
            case_denominator = float(case["denominator"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MetricError(f"case {case_id} lacks numeric numerator/denominator") from exc
        if case_numerator < 0 or case_denominator < 0 or case_numerator > case_denominator:
            raise MetricError(f"case {case_id} has invalid metric bounds")
        numerator += case_numerator
        denominator += case_denominator
        if case.get("evidence_path"):
            evidence_paths.append(str(case["evidence_path"]))
    value = None if denominator == 0 else numerator / denominator
    result = {"metric": name, "numerator": int(numerator) if numerator.is_integer() else numerator, "denominator": int(denominator) if denominator.is_integer() else denominator, "value": value, "unavailable": unavailable, "evidence_paths": sorted(set(evidence_paths))}
    definition = FROZEN_METRICS[name]
    result["gate"] = "fail" if definition.absolute_threshold is not None and value is not None and value > definition.absolute_threshold else ("not_applicable" if value is None else "pass")
    return result


@dataclass(frozen=True, slots=True)
class EvaluationManifest:
    schema_version: int
    corpus_cases: tuple[str, ...]
    alpha1_revision: str
    prompt_baseline_revision: str
    alpha2_revision: str
    host_matrix: tuple[Mapping[str, Any], ...]
    environment_digests: tuple[str, ...]
    commands: tuple[str, ...]
    random_seeds: tuple[int, ...]
    network_recording_policy: str
    oracle_interfaces: tuple[str, ...]
    metrics: tuple[str, ...]
    aggregation: str
    missing_data: str
    expert_rubric: str
    thresholds: Mapping[str, float]
    release_gates: tuple[str, ...]
    manifest_digest: str

    @classmethod
    def create(cls, *, corpus_cases: Sequence[str], alpha1_revision: str, prompt_baseline_revision: str, alpha2_revision: str, host_matrix: Sequence[Mapping[str, Any]], environment_digests: Sequence[str], commands: Sequence[str], random_seeds: Sequence[int], network_recording_policy: str, oracle_interfaces: Sequence[str], metrics: Sequence[str] = tuple(FROZEN_METRICS), aggregation: str = "case-level numerator/denominator", missing_data: str = "not_applicable excluded", expert_rubric: str = "versioned-blinded-rubric-v1", thresholds: Mapping[str, float] | None = None, release_gates: Sequence[str] = ("false_completion_zero", "p0_closure_resolvable", "host_parity")) -> "EvaluationManifest":
        unknown = set(metrics) - set(FROZEN_METRICS)
        if unknown:
            raise MetricError("unknown metrics: " + ", ".join(sorted(unknown)))
        body = {"schema_version": 1, "corpus_cases": list(corpus_cases), "alpha1_revision": alpha1_revision, "prompt_baseline_revision": prompt_baseline_revision, "alpha2_revision": alpha2_revision, "host_matrix": [dict(item) for item in host_matrix], "environment_digests": list(environment_digests), "commands": list(commands), "random_seeds": list(random_seeds), "network_recording_policy": network_recording_policy, "oracle_interfaces": list(oracle_interfaces), "metrics": list(metrics), "aggregation": aggregation, "missing_data": missing_data, "expert_rubric": expert_rubric, "thresholds": dict(thresholds or {name: 0.0 if name == "false_completion" else 1.0 for name in metrics}), "release_gates": list(release_gates)}
        digest = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        return cls(**body, manifest_digest=digest)

    def verify(self) -> bool:
        body = {key: getattr(self, key) for key in ("schema_version", "corpus_cases", "alpha1_revision", "prompt_baseline_revision", "alpha2_revision", "host_matrix", "environment_digests", "commands", "random_seeds", "network_recording_policy", "oracle_interfaces", "metrics", "aggregation", "missing_data", "expert_rubric", "thresholds", "release_gates")}
        body["corpus_cases"] = list(body["corpus_cases"]); body["host_matrix"] = [dict(item) for item in body["host_matrix"]]; body["environment_digests"] = list(body["environment_digests"]); body["commands"] = list(body["commands"]); body["random_seeds"] = list(body["random_seeds"]); body["oracle_interfaces"] = list(body["oracle_interfaces"]); body["metrics"] = list(body["metrics"]); body["thresholds"] = dict(body["thresholds"]); body["release_gates"] = list(body["release_gates"])
        return hashlib.sha256(canonical_json_bytes(body)).hexdigest() == self.manifest_digest
