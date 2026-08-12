"""Deterministic, evaluator-owned Alpha2 release gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


HOSTS = frozenset({"codex", "claude-code", "hermes"})
DISPOSITIONS = frozenset({"passed", "failed", "unavailable"})
QUALITY_METRICS = (
    "intent_fidelity",
    "unsupported_claim_control",
    "contradiction_handling",
    "depth",
    "implementation_success",
    "rediscovery_control",
    "professional_usefulness",
)
_HIDDEN_KEYS = frozenset(
    {"hidden_oracle", "oracle_body", "reference_patch", "expected_patch", "private_prompt", "secret", "credential"}
)
_CASE_FIELDS = frozenset(
    {
        "case_id",
        "case_version",
        "host",
        "execution_disposition",
        "source_revision",
        "environment_digest",
        "package_digest",
        "command",
        "public_artifact_refs",
        "opaque_oracle_id",
        "oracle_verdict_digest",
        "evaluator_id",
        "producer_id",
        "false_completion_count",
        "p0_total",
        "p0_resolved",
        "evidence_refs_resolved",
        "closure_refs_resolved",
        "recovery_preserved",
        "semantic_delivery_consistent",
        "canonical_outcome_digest",
        "quality",
        "comparison",
        "review_refs",
        "limitations",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_id",
        "source_revision",
        "required_hosts",
        "cases",
        "quality_thresholds",
        "independent_implementation_refs",
        "blinded_review_refs",
        "limitations",
    }
)


class InvalidReleaseManifest(ValueError):
    """Raised when evaluator input is incomplete or leaks private material."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidReleaseManifest(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    if set(value) != fields:
        raise InvalidReleaseManifest(f"{label} fields do not match contract")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidReleaseManifest(f"{label} must be non-empty")
    return value.strip()


def _digest(value: Any, label: str, *, allow_none: bool = False) -> str | None:
    if allow_none and value is None:
        return None
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise InvalidReleaseManifest(f"{label} must be a lowercase sha256 digest")
    return text


def _strings(value: Any, label: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise InvalidReleaseManifest(f"{label} must be a list")
    result = tuple(_text(item, label) for item in value)
    if required and not result:
        raise InvalidReleaseManifest(f"{label} must not be empty")
    return result


def _score(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
        raise InvalidReleaseManifest(f"{label} must be between 0 and 1")
    return float(value)


def _reject_hidden(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _HIDDEN_KEYS:
                raise InvalidReleaseManifest(f"hidden material is forbidden: {key}")
            _reject_hidden(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_hidden(child)


@dataclass(frozen=True, slots=True)
class ReleaseCaseResult:
    case_id: str
    case_version: str
    host: str
    execution_disposition: str
    source_revision: str
    environment_digest: str
    package_digest: str
    command: str
    public_artifact_refs: tuple[str, ...]
    opaque_oracle_id: str
    oracle_verdict_digest: str | None
    evaluator_id: str
    producer_id: str
    false_completion_count: int
    p0_total: int
    p0_resolved: int
    evidence_refs_resolved: bool
    closure_refs_resolved: bool
    recovery_preserved: bool
    semantic_delivery_consistent: bool
    canonical_outcome_digest: str
    quality: Mapping[str, float]
    comparison: Mapping[str, float]
    review_refs: tuple[str, ...]
    limitations: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReleaseCaseResult":
        data = _mapping(value, "release case")
        _reject_hidden(data)
        _exact(data, _CASE_FIELDS, "release case")
        disposition = _text(data["execution_disposition"], "execution_disposition")
        if disposition not in DISPOSITIONS:
            raise InvalidReleaseManifest("execution_disposition must be passed, failed, or unavailable")
        host = _text(data["host"], "host")
        if host not in HOSTS:
            raise InvalidReleaseManifest("host is unsupported")
        evaluator = _text(data["evaluator_id"], "evaluator_id")
        producer = _text(data["producer_id"], "producer_id")
        if evaluator == producer:
            raise InvalidReleaseManifest("independent evaluator must differ from producer")
        source_revision = _text(data["source_revision"], "source_revision")
        if len(source_revision) < 7:
            raise InvalidReleaseManifest("source_revision must be source-bound")
        counts = {}
        for name in ("false_completion_count", "p0_total", "p0_resolved"):
            raw = data[name]
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise InvalidReleaseManifest(f"{name} must be a non-negative integer")
            counts[name] = raw
        if counts["p0_resolved"] > counts["p0_total"]:
            raise InvalidReleaseManifest("p0_resolved cannot exceed p0_total")
        quality = _mapping(data["quality"], "quality")
        if set(quality) != set(QUALITY_METRICS):
            raise InvalidReleaseManifest("quality fields do not match contract")
        comparison = _mapping(data["comparison"], "comparison")
        comparison_fields = {
            "alpha2_implementation_success",
            "alpha1_implementation_success",
            "simpler_prompt_implementation_success",
        }
        if set(comparison) != comparison_fields:
            raise InvalidReleaseManifest("comparison fields do not match contract")
        artifacts = _strings(data["public_artifact_refs"], "public_artifact_refs")
        verdict = _digest(data["oracle_verdict_digest"], "oracle_verdict_digest", allow_none=True)
        limitations = _strings(data["limitations"], "limitations", required=disposition == "unavailable")
        if disposition == "passed" and (not artifacts or verdict is None):
            raise InvalidReleaseManifest("passed execution requires public artifacts and oracle verdict")
        return cls(
            case_id=_text(data["case_id"], "case_id"),
            case_version=_text(data["case_version"], "case_version"),
            host=host,
            execution_disposition=disposition,
            source_revision=source_revision,
            environment_digest=_digest(data["environment_digest"], "environment_digest"),
            package_digest=_digest(data["package_digest"], "package_digest"),
            command=_text(data["command"], "command"),
            public_artifact_refs=artifacts,
            opaque_oracle_id=_text(data["opaque_oracle_id"], "opaque_oracle_id"),
            oracle_verdict_digest=verdict,
            evaluator_id=evaluator,
            producer_id=producer,
            false_completion_count=counts["false_completion_count"],
            p0_total=counts["p0_total"],
            p0_resolved=counts["p0_resolved"],
            evidence_refs_resolved=_boolean(data["evidence_refs_resolved"], "evidence_refs_resolved"),
            closure_refs_resolved=_boolean(data["closure_refs_resolved"], "closure_refs_resolved"),
            recovery_preserved=_boolean(data["recovery_preserved"], "recovery_preserved"),
            semantic_delivery_consistent=_boolean(data["semantic_delivery_consistent"], "semantic_delivery_consistent"),
            canonical_outcome_digest=_digest(data["canonical_outcome_digest"], "canonical_outcome_digest"),
            quality={name: _score(quality[name], name) for name in QUALITY_METRICS},
            comparison={name: _score(comparison[name], name) for name in sorted(comparison_fields)},
            review_refs=_strings(data["review_refs"], "review_refs"),
            limitations=limitations,
        )


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise InvalidReleaseManifest(f"{label} must be boolean")
    return value


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    schema_version: int
    manifest_id: str
    source_revision: str
    required_hosts: tuple[str, ...]
    cases: tuple[ReleaseCaseResult, ...]
    quality_thresholds: Mapping[str, float]
    independent_implementation_refs: tuple[str, ...]
    blinded_review_refs: tuple[str, ...]
    limitations: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReleaseManifest":
        raw = dict(_mapping(value, "release manifest"))
        _reject_hidden(raw)
        raw.pop("proxy_metrics", None)
        _exact(raw, _MANIFEST_FIELDS, "release manifest")
        if raw["schema_version"] != 1:
            raise InvalidReleaseManifest("schema_version must be 1")
        hosts = _strings(raw["required_hosts"], "required_hosts", required=True)
        if len(hosts) != len(set(hosts)) or not set(hosts) <= HOSTS:
            raise InvalidReleaseManifest("required_hosts must be unique supported hosts")
        cases_raw = raw["cases"]
        if not isinstance(cases_raw, list) or not cases_raw:
            raise InvalidReleaseManifest("cases must be a non-empty list")
        cases = tuple(ReleaseCaseResult.from_mapping(item) for item in cases_raw)
        thresholds = _mapping(raw["quality_thresholds"], "quality_thresholds")
        if set(thresholds) != set(QUALITY_METRICS):
            raise InvalidReleaseManifest("quality_thresholds fields do not match contract")
        revision = _text(raw["source_revision"], "source_revision")
        if len(revision) < 7:
            raise InvalidReleaseManifest("source_revision must be source-bound")
        return cls(
            schema_version=1,
            manifest_id=_text(raw["manifest_id"], "manifest_id"),
            source_revision=revision,
            required_hosts=hosts,
            cases=cases,
            quality_thresholds={name: _score(thresholds[name], name) for name in QUALITY_METRICS},
            independent_implementation_refs=_strings(
                raw["independent_implementation_refs"], "independent_implementation_refs", required=True
            ),
            blinded_review_refs=_strings(raw["blinded_review_refs"], "blinded_review_refs", required=True),
            limitations=_strings(raw["limitations"], "limitations", required=True),
        )


@dataclass(frozen=True, slots=True)
class IntegrityGate:
    name: str
    status: str
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "failures": list(self.failures)}


@dataclass(frozen=True, slots=True)
class ReleaseDecision:
    manifest_id: str
    source_revision: str
    status: str
    integrity_gates: tuple[IntegrityGate, ...]
    quality_diagnostics: Mapping[str, float]
    quality_thresholds: Mapping[str, float]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "source_revision": self.source_revision,
            "status": self.status,
            "integrity_gates": [gate.to_dict() for gate in self.integrity_gates],
            "quality_diagnostics": dict(self.quality_diagnostics),
            "quality_thresholds": dict(self.quality_thresholds),
            "limitations": list(self.limitations),
        }


def _gate(name: str, failures: list[str]) -> IntegrityGate:
    return IntegrityGate(name, "fail" if failures else "pass", tuple(failures))


def evaluate_release(manifest: ReleaseManifest) -> ReleaseDecision:
    """Evaluate hard integrity gates before reporting semantic diagnostics."""

    if not isinstance(manifest, ReleaseManifest):
        raise InvalidReleaseManifest("manifest must be a ReleaseManifest")
    cases = manifest.cases
    gates = [
        _gate("zero_false_completion", [item.case_id for item in cases if item.false_completion_count]),
        _gate("p0_resolution", [item.case_id for item in cases if item.p0_resolved != item.p0_total]),
        _gate(
            "evidence_and_closure",
            [item.case_id for item in cases if not (item.evidence_refs_resolved and item.closure_refs_resolved)],
        ),
        _gate("recovery", [item.case_id for item in cases if not item.recovery_preserved]),
        _gate("semantic_delivery", [item.case_id for item in cases if not item.semantic_delivery_consistent]),
    ]
    host_failures = []
    parity_digests = set()
    for host in manifest.required_hosts:
        host_cases = [item for item in cases if item.host == host]
        if not host_cases or any(item.execution_disposition != "passed" for item in host_cases):
            host_failures.append(host)
        parity_digests.update(
            item.canonical_outcome_digest for item in host_cases if item.execution_disposition == "passed"
        )
    if len(parity_digests) != 1:
        host_failures.append("canonical-outcome-drift")
    gates.append(_gate("required_host_parity", host_failures))
    diagnostics = {name: min(item.quality[name] for item in cases) for name in QUALITY_METRICS}
    gates.append(
        _gate(
            "quality_thresholds",
            [name for name, score in diagnostics.items() if score < manifest.quality_thresholds[name]],
        )
    )
    gates.append(
        _gate(
            "independent_implementation_improvement",
            [
                item.case_id
                for item in cases
                if item.execution_disposition == "passed"
                and not (
                    item.comparison["alpha2_implementation_success"] > item.comparison["alpha1_implementation_success"]
                    and item.comparison["alpha2_implementation_success"]
                    > item.comparison["simpler_prompt_implementation_success"]
                )
            ],
        )
    )
    gates.append(
        _gate(
            "independent_evidence",
            [] if manifest.independent_implementation_refs and manifest.blinded_review_refs else [manifest.manifest_id],
        )
    )
    return ReleaseDecision(
        manifest_id=manifest.manifest_id,
        source_revision=manifest.source_revision,
        status="pass" if all(gate.status == "pass" for gate in gates) else "fail",
        integrity_gates=tuple(gates),
        quality_diagnostics=diagnostics,
        quality_thresholds=manifest.quality_thresholds,
        limitations=manifest.limitations,
    )
