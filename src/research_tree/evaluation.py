"""Evaluate implementation-ready packages against time-split cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .delivery import TECHNICAL_RESEARCH_PACKAGE_KIND
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    freeze_payload,
    thaw_json,
    validate_identifier,
)
from .readiness import READINESS_RECORD_KIND, validate_readiness_record_payload
from .storage import RunStore


BLUEPRINT_EVALUATION_KIND = "blueprint-evaluation"
EVALUATION_CHECK_NAMES = ("build", "fail_to_pass", "pass_to_pass")
EVALUATION_CHECK_STATUSES = frozenset({"pass", "fail", "not_applicable"})
DIAGNOSIS_COMPONENTS = frozenset(
    {
        "intent",
        "intake",
        "decision_map",
        "work_items",
        "decision_ledger",
        "technical_package",
        "readiness",
        "risk_verification",
        "implementation",
    }
)
_CASE_KEYS = {
    "id",
    "corpus_version",
    "source",
    "baseline",
    "environment",
    "public_materials",
    "hidden_oracle_id",
    "limitations",
}
_FORBIDDEN_CASE_KEYS = {
    "eventual_patch",
    "patch",
    "discussion",
    "acceptance_tests",
    "hidden_acceptance_tests",
    "hidden_oracle",
}


class EvaluationError(RuntimeStoreError):
    """Base error for malformed time-split evaluation inputs."""


class InvalidEvaluationError(EvaluationError):
    """Raised before an invalid evaluation record can be appended."""


@dataclass(frozen=True, slots=True)
class TimeSplitCase:
    """Public case material plus an opaque evaluator-owned oracle identifier."""

    id: str
    corpus_version: str
    source: Mapping[str, str]
    baseline: Mapping[str, str]
    environment: Mapping[str, str]
    public_materials: tuple[Mapping[str, str], ...]
    hidden_oracle_id: str
    limitations: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TimeSplitCase":
        data = _mapping(value, "time-split case")
        hidden = sorted(_FORBIDDEN_CASE_KEYS & set(data))
        if hidden:
            raise InvalidEvaluationError(
                "time-split case must not include hidden eventual material: "
                + ", ".join(hidden)
            )
        _require_exact_keys(data, _CASE_KEYS, "time-split case")
        source = _normalize_source(data["source"])
        baseline = _normalize_baseline(data["baseline"])
        environment = _normalize_environment(data["environment"])
        public_materials = _normalize_public_materials(data["public_materials"])
        return cls(
            id=_identifier(data["id"], "time-split case id"),
            corpus_version=_nonempty(data["corpus_version"], "time-split case corpus_version"),
            source=freeze_payload(source),
            baseline=freeze_payload(baseline),
            environment=freeze_payload(environment),
            public_materials=tuple(freeze_payload(item) for item in public_materials),
            hidden_oracle_id=_identifier(
                data["hidden_oracle_id"], "time-split case hidden_oracle_id"
            ),
            limitations=tuple(_strings(data["limitations"], "time-split case limitations")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "corpus_version": self.corpus_version,
            "source": thaw_json(self.source),
            "baseline": thaw_json(self.baseline),
            "environment": thaw_json(self.environment),
            "public_materials": [thaw_json(item) for item in self.public_materials],
            "hidden_oracle_id": self.hidden_oracle_id,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class EvaluationCheck:
    """One independently executed build, acceptance, or regression check."""

    name: str
    status: str
    command: str
    summary: str


@dataclass(frozen=True, slots=True)
class EvaluationDiagnosis:
    """Maps an implementation outcome back to one product component."""

    component: str
    summary: str
    decision_slot_id: str | None = None
    work_item_id: str | None = None


@dataclass(frozen=True, slots=True)
class IndependentEvaluationResult:
    """Evaluator-owned outcome returned by an independent implementation runner."""

    checks: Sequence[EvaluationCheck]
    diagnoses: Sequence[EvaluationDiagnosis] = ()
    limitations: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class SimplerBaselineResult:
    """Outcome from an explicit, lower-information comparator."""

    name: str
    checks: Sequence[EvaluationCheck]
    limitations: Sequence[str]


@dataclass(frozen=True, slots=True)
class IndependentEvaluationRequest:
    """The only public inputs delivered to an implementation runner.

    Hidden oracle material is configured by the evaluator outside this request.
    The request deliberately has no host path, reference patch, discussion, or
    hidden-oracle field.
    """

    case_id: str
    corpus_version: str
    baseline: Mapping[str, str]
    environment: Mapping[str, str]
    public_materials: tuple[Mapping[str, str], ...]
    technical_package: Mapping[str, Any]
    readiness: Mapping[str, Any]


@runtime_checkable
class IndependentImplementationRunner(Protocol):
    """Run an implementation attempt in evaluator-owned isolation."""

    def run(self, request: IndependentEvaluationRequest) -> IndependentEvaluationResult:
        """Return separately named build, FAIL_TO_PASS, and PASS_TO_PASS outcomes."""


class BlueprintEvaluationSuite:
    """Persist versioned, diagnosable blueprint-evaluation artifacts."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def evaluate(
        self,
        *,
        round_id: str,
        evaluation_id: str,
        case: TimeSplitCase,
        technical_package: ArtifactRevision,
        readiness_record: ArtifactRevision,
        cost: Mapping[str, Any],
        clarification_burden: Mapping[str, Any],
        implementation_runner: IndependentImplementationRunner,
        baseline_result: SimplerBaselineResult,
    ) -> ArtifactRevision:
        """Evaluate one exact package without exposing evaluator-owned material."""

        try:
            snapshot = self._store.load_round(round_id)
            evaluation_identifier = _identifier(evaluation_id, "evaluation_id")
            _ensure_id_compatibility(snapshot.artifacts, evaluation_identifier)
            if not isinstance(case, TimeSplitCase):
                raise InvalidEvaluationError("case must be a TimeSplitCase")
            package = _resolve_exact(
                snapshot.artifacts,
                technical_package,
                TECHNICAL_RESEARCH_PACKAGE_KIND,
                "technical_package",
            )
            readiness = _resolve_exact(
                snapshot.artifacts,
                readiness_record,
                READINESS_RECORD_KIND,
                "readiness_record",
            )
            if package.round_id != round_id or readiness.round_id != round_id:
                raise InvalidEvaluationError("package and readiness record must belong to evaluation round")
            validate_readiness_record_payload(readiness.payload)
            _ensure_readiness_matches_package(readiness, package)
            normalized_cost = _normalize_count_mapping(cost, "cost")
            normalized_burden = _normalize_count_mapping(
                clarification_burden, "clarification_burden"
            )
            request = _request_for(case, package, readiness)
            outcome = _run_implementation_runner(implementation_runner, request)
            comparison = _normalize_baseline_result(baseline_result)
            structural_quality = _structural_quality(readiness)
            payload = {
                "case": case.to_dict(),
                "technical_package_ref": _artifact_ref_dict(package),
                "readiness_record_ref": _artifact_ref_dict(readiness),
                "structural_quality": structural_quality,
                "implementation_outcome": outcome,
                "diagnoses": outcome["diagnoses"],
                "comparison": {"baseline": comparison},
                "cost": normalized_cost,
                "clarification_burden": normalized_burden,
            }
            validate_blueprint_evaluation_payload(payload)
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidEvaluationError(str(error)) from error

        return self._store.append_artifact(
            round_id,
            evaluation_identifier,
            BLUEPRINT_EVALUATION_KIND,
            payload,
            parent_refs=(
                ArtifactRef(round_id, package.id, package.revision),
                ArtifactRef(round_id, readiness.id, readiness.revision),
            ),
        )


def validate_blueprint_evaluation_payload(payload: Mapping[str, Any]) -> None:
    """Validate a persisted evaluation record without invoking a runner."""

    data = _mapping(payload, "blueprint evaluation payload")
    _require_exact_keys(
        data,
        {
            "case",
            "technical_package_ref",
            "readiness_record_ref",
            "structural_quality",
            "implementation_outcome",
            "diagnoses",
            "comparison",
            "cost",
            "clarification_burden",
        },
        "blueprint evaluation payload",
    )
    TimeSplitCase.from_mapping(_mapping(data["case"], "blueprint evaluation case"))
    _validate_ref(data["technical_package_ref"], "technical_package_ref")
    _validate_ref(data["readiness_record_ref"], "readiness_record_ref")
    _validate_structural_quality(data["structural_quality"])
    normalized_outcome = _validate_outcome(data["implementation_outcome"])
    diagnoses = _normalize_diagnoses(data["diagnoses"])
    if tuple(diagnoses) != tuple(normalized_outcome["diagnoses"]):
        raise InvalidEvaluationError("diagnoses must exactly match implementation_outcome diagnoses")
    comparison = _mapping(data["comparison"], "comparison")
    _require_exact_keys(comparison, {"baseline"}, "comparison")
    _validate_baseline_payload(comparison["baseline"])
    _normalize_count_mapping(data["cost"], "cost")
    _normalize_count_mapping(data["clarification_burden"], "clarification_burden")


def _request_for(
    case: TimeSplitCase,
    package: ArtifactRevision,
    readiness: ArtifactRevision,
) -> IndependentEvaluationRequest:
    return IndependentEvaluationRequest(
        case_id=case.id,
        corpus_version=case.corpus_version,
        baseline=freeze_payload(thaw_json(case.baseline)),
        environment=freeze_payload(thaw_json(case.environment)),
        public_materials=tuple(freeze_payload(thaw_json(item)) for item in case.public_materials),
        technical_package=freeze_payload(
            {
                "ref": _artifact_ref_dict(package),
                "content_hash": package.content_hash,
                "document": thaw_json(package.payload.get("document")),
            }
        ),
        readiness=freeze_payload(
            {
                "ref": _artifact_ref_dict(readiness),
                "delivery_readiness": thaw_json(readiness.payload.get("delivery_readiness")),
                "risk_verification": thaw_json(readiness.payload.get("risk_verification")),
            }
        ),
    )


def _run_implementation_runner(
    runner: IndependentImplementationRunner,
    request: IndependentEvaluationRequest,
) -> dict[str, Any]:
    if not isinstance(runner, IndependentImplementationRunner):
        raise InvalidEvaluationError("implementation_runner must implement run(request)")
    try:
        result = runner.run(request)
    except Exception as error:
        raise InvalidEvaluationError(
            f"implementation runner failed before returning an outcome: {type(error).__name__}"
        ) from error
    if not isinstance(result, IndependentEvaluationResult):
        raise InvalidEvaluationError(
            "implementation_runner.run must return an IndependentEvaluationResult"
        )
    checks = _normalize_checks(result.checks, "implementation outcome checks")
    diagnoses = _normalize_diagnoses(result.diagnoses)
    limitations = _strings(result.limitations, "implementation outcome limitations")
    return {
        "checks": checks,
        "diagnoses": diagnoses,
        "limitations": list(limitations),
    }


def _normalize_baseline_result(value: SimplerBaselineResult) -> dict[str, Any]:
    if not isinstance(value, SimplerBaselineResult):
        raise InvalidEvaluationError("baseline_result must be a SimplerBaselineResult")
    return {
        "name": _nonempty(value.name, "baseline_result name"),
        "checks": _normalize_checks(value.checks, "baseline_result checks"),
        "limitations": list(_strings(value.limitations, "baseline_result limitations")),
    }


def _structural_quality(readiness: ArtifactRevision) -> dict[str, Any]:
    projection = _mapping(readiness.payload.get("delivery_readiness"), "readiness delivery_readiness")
    gates = _mapping(projection.get("gates"), "readiness delivery gates")
    checks = _mappings(readiness.payload.get("repository_anchor_checks"), "repository_anchor_checks")
    if not checks:
        anchor_accuracy: dict[str, Any] = {
            "status": "not_applicable",
            "resolved": 0,
            "total": 0,
        }
    else:
        resolved = sum(1 for check in checks if check.get("resolved") is True)
        anchor_accuracy = {
            "status": "pass" if resolved == len(checks) else "fail",
            "resolved": resolved,
            "total": len(checks),
        }
    return {
        "decision_closure": _enum(
            gates.get("decision_closure"),
            "readiness decision_closure",
            {"pass", "fail", "deferred"},
        ),
        "traceability": _enum(
            gates.get("traceability"), "readiness traceability", {"pass", "fail"}
        ),
        "repository_anchor_accuracy": anchor_accuracy,
    }


def _ensure_readiness_matches_package(
    readiness: ArtifactRevision, package: ArtifactRevision
) -> None:
    ref = _mapping(readiness.payload.get("technical_package_ref"), "readiness technical_package_ref")
    expected = _artifact_ref_dict(package)
    if thaw_json(ref) != expected:
        raise InvalidEvaluationError("readiness_record does not belong to the exact technical_package")
    if ArtifactRef(package.round_id, package.id, package.revision) not in readiness.parent_refs:
        raise InvalidEvaluationError("readiness_record lacks exact technical_package parent lineage")


def _resolve_exact(
    artifacts: Sequence[ArtifactRevision],
    artifact: ArtifactRevision,
    expected_kind: str,
    label: str,
) -> ArtifactRevision:
    if not isinstance(artifact, ArtifactRevision) or artifact.kind != expected_kind:
        raise InvalidEvaluationError(f"{label} must be a {expected_kind} ArtifactRevision")
    exact = next(
        (
            item
            for item in artifacts
            if item.id == artifact.id
            and item.revision == artifact.revision
            and item.kind == expected_kind
        ),
        None,
    )
    if exact is None or exact.round_id != artifact.round_id:
        raise InvalidEvaluationError(f"{label} must resolve to an exact stored {expected_kind}")
    return exact


def _ensure_id_compatibility(artifacts: Sequence[ArtifactRevision], artifact_id: str) -> None:
    foreign = {item.kind for item in artifacts if item.id == artifact_id and item.kind != BLUEPRINT_EVALUATION_KIND}
    if foreign:
        raise InvalidEvaluationError(
            f"evaluation_id {artifact_id!r} is already used by artifact kinds: {sorted(foreign)}"
        )


def _normalize_source(value: Any) -> dict[str, str]:
    source = _mapping(value, "time-split case source")
    _require_exact_keys(source, {"locator", "permission"}, "time-split case source")
    return {
        "locator": _nonempty(source["locator"], "time-split case source locator"),
        "permission": _nonempty(source["permission"], "time-split case source permission"),
    }


def _normalize_baseline(value: Any) -> dict[str, str]:
    baseline = _mapping(value, "time-split case baseline")
    _require_exact_keys(baseline, {"revision", "sha256"}, "time-split case baseline")
    return {
        "revision": _nonempty(baseline["revision"], "time-split case baseline revision"),
        "sha256": _sha256(baseline["sha256"], "time-split case baseline sha256"),
    }


def _normalize_environment(value: Any) -> dict[str, str]:
    environment = _mapping(value, "time-split case environment")
    _require_exact_keys(environment, {"image", "digest", "recipe"}, "time-split case environment")
    digest = _nonempty(environment["digest"], "time-split case environment digest")
    if not digest.startswith("sha256:"):
        raise InvalidEvaluationError("time-split case environment digest must use sha256:")
    _sha256(digest.removeprefix("sha256:"), "time-split case environment digest")
    return {
        "image": _nonempty(environment["image"], "time-split case environment image"),
        "digest": digest,
        "recipe": _nonempty(environment["recipe"], "time-split case environment recipe"),
    }


def _normalize_public_materials(value: Any) -> list[dict[str, str]]:
    materials = _mappings(value, "time-split case public_materials")
    if not materials:
        raise InvalidEvaluationError("time-split case public_materials must not be empty")
    normalized: list[dict[str, str]] = []
    for index, material in enumerate(materials):
        label = f"time-split case public_materials[{index}]"
        _require_exact_keys(material, {"kind", "locator"}, label)
        normalized.append(
            {
                "kind": _nonempty(material["kind"], f"{label}.kind"),
                "locator": _nonempty(material["locator"], f"{label}.locator"),
            }
        )
    return normalized


def _normalize_checks(value: Any, label: str) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidEvaluationError(f"{label} must be a sequence of EvaluationCheck values")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, EvaluationCheck):
            raise InvalidEvaluationError(f"{label}[{index}] must be an EvaluationCheck")
        name = _enum(item.name, f"{label}[{index}].name", set(EVALUATION_CHECK_NAMES))
        if name in seen:
            raise InvalidEvaluationError(f"{label} repeats check {name}")
        seen.add(name)
        normalized.append(
            {
                "name": name,
                "status": _enum(
                    item.status,
                    f"{label}[{index}].status",
                    set(EVALUATION_CHECK_STATUSES),
                ),
                "command": _nonempty(item.command, f"{label}[{index}].command"),
                "summary": _nonempty(item.summary, f"{label}[{index}].summary"),
            }
        )
    if set(seen) != set(EVALUATION_CHECK_NAMES):
        raise InvalidEvaluationError(
            f"{label} must include exactly: {', '.join(EVALUATION_CHECK_NAMES)}"
        )
    return normalized


def _normalize_diagnoses(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidEvaluationError("diagnoses must be a sequence of EvaluationDiagnosis values")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            data = _mapping(item, f"diagnoses[{index}]")
            _require_exact_keys(
                data,
                {"component", "summary", "decision_slot_id", "work_item_id"},
                f"diagnoses[{index}]",
            )
            component = data["component"]
            summary = data["summary"]
            slot_id = data["decision_slot_id"]
            work_item_id = data["work_item_id"]
        elif isinstance(item, EvaluationDiagnosis):
            component = item.component
            summary = item.summary
            slot_id = item.decision_slot_id
            work_item_id = item.work_item_id
        else:
            raise InvalidEvaluationError(
                f"diagnoses[{index}] must be an EvaluationDiagnosis or mapping"
            )
        normalized.append(
            {
                "component": _enum(component, f"diagnoses[{index}].component", set(DIAGNOSIS_COMPONENTS)),
                "summary": _nonempty(summary, f"diagnoses[{index}].summary"),
                "decision_slot_id": None
                if slot_id is None
                else _identifier(slot_id, f"diagnoses[{index}].decision_slot_id"),
                "work_item_id": None
                if work_item_id is None
                else _identifier(work_item_id, f"diagnoses[{index}].work_item_id"),
            }
        )
    return normalized


def _validate_outcome(value: Any) -> dict[str, Any]:
    outcome = _mapping(value, "implementation_outcome")
    _require_exact_keys(outcome, {"checks", "diagnoses", "limitations"}, "implementation_outcome")
    checks = _normalize_check_mappings(outcome["checks"], "implementation_outcome checks")
    diagnoses = _normalize_diagnoses(outcome["diagnoses"])
    limitations = _strings(outcome["limitations"], "implementation_outcome limitations")
    return {"checks": checks, "diagnoses": diagnoses, "limitations": list(limitations)}


def _normalize_check_mappings(value: Any, label: str) -> list[dict[str, str]]:
    checks = _mappings(value, label)
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(checks):
        item_label = f"{label}[{index}]"
        _require_exact_keys(item, {"name", "status", "command", "summary"}, item_label)
        name = _enum(item["name"], f"{item_label}.name", set(EVALUATION_CHECK_NAMES))
        if name in seen:
            raise InvalidEvaluationError(f"{label} repeats check {name}")
        seen.add(name)
        normalized.append(
            {
                "name": name,
                "status": _enum(item["status"], f"{item_label}.status", set(EVALUATION_CHECK_STATUSES)),
                "command": _nonempty(item["command"], f"{item_label}.command"),
                "summary": _nonempty(item["summary"], f"{item_label}.summary"),
            }
        )
    if seen != set(EVALUATION_CHECK_NAMES):
        raise InvalidEvaluationError(
            f"{label} must include exactly: {', '.join(EVALUATION_CHECK_NAMES)}"
        )
    return normalized


def _validate_baseline_payload(value: Any) -> None:
    baseline = _mapping(value, "comparison baseline")
    _require_exact_keys(baseline, {"name", "checks", "limitations"}, "comparison baseline")
    _nonempty(baseline["name"], "comparison baseline name")
    _normalize_check_mappings(baseline["checks"], "comparison baseline checks")
    _strings(baseline["limitations"], "comparison baseline limitations")


def _validate_structural_quality(value: Any) -> None:
    quality = _mapping(value, "structural_quality")
    _require_exact_keys(
        quality,
        {"decision_closure", "traceability", "repository_anchor_accuracy"},
        "structural_quality",
    )
    _enum(quality["decision_closure"], "structural_quality.decision_closure", {"pass", "fail", "deferred"})
    _enum(quality["traceability"], "structural_quality.traceability", {"pass", "fail"})
    anchor = _mapping(quality["repository_anchor_accuracy"], "repository_anchor_accuracy")
    _require_exact_keys(anchor, {"status", "resolved", "total"}, "repository_anchor_accuracy")
    _enum(anchor["status"], "repository_anchor_accuracy.status", {"pass", "fail", "not_applicable"})
    resolved = _nonnegative_int(anchor["resolved"], "repository_anchor_accuracy.resolved")
    total = _nonnegative_int(anchor["total"], "repository_anchor_accuracy.total")
    if resolved > total:
        raise InvalidEvaluationError("repository_anchor_accuracy.resolved cannot exceed total")
    if total == 0 and anchor["status"] != "not_applicable":
        raise InvalidEvaluationError("empty repository_anchor_accuracy must be not_applicable")
    if total and anchor["status"] == "not_applicable":
        raise InvalidEvaluationError("nonempty repository_anchor_accuracy cannot be not_applicable")


def _normalize_count_mapping(value: Any, label: str) -> dict[str, int]:
    data = _mapping(value, label)
    _require_exact_keys(data, {"tool_calls", "seconds"} if label == "cost" else {"asked", "unanswered"}, label)
    if label == "cost":
        return {
            "tool_calls": _nonnegative_int(data["tool_calls"], "cost.tool_calls"),
            "seconds": _nonnegative_int(data["seconds"], "cost.seconds"),
        }
    asked = _nonnegative_int(data["asked"], "clarification_burden.asked")
    unanswered = _nonnegative_int(data["unanswered"], "clarification_burden.unanswered")
    if unanswered > asked:
        raise InvalidEvaluationError("clarification_burden.unanswered cannot exceed asked")
    return {"asked": asked, "unanswered": unanswered}


def _validate_ref(value: Any, label: str) -> None:
    data = _mapping(value, label)
    _require_exact_keys(data, {"round_id", "artifact_id", "revision"}, label)
    ArtifactRef(
        _identifier(data["round_id"], f"{label}.round_id"),
        _identifier(data["artifact_id"], f"{label}.artifact_id"),
        _positive_int(data["revision"], f"{label}.revision"),
    )


def _artifact_ref_dict(artifact: ArtifactRevision) -> dict[str, Any]:
    return ArtifactRef(artifact.round_id, artifact.id, artifact.revision).to_dict()


def _mappings(value: Any, label: str) -> list[Mapping[str, Any]]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidEvaluationError(f"{label} must be a sequence of mappings")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(plain):
        if not isinstance(item, Mapping):
            raise InvalidEvaluationError(f"{label}[{index}] must be a mapping")
        result.append(item)
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    plain = thaw_json(value)
    if not isinstance(plain, Mapping):
        raise InvalidEvaluationError(f"{label} must be a mapping")
    return plain


def _strings(value: Any, label: str) -> tuple[str, ...]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidEvaluationError(f"{label} must be a sequence of strings")
    return tuple(_nonempty(item, f"{label}[{index}]") for index, item in enumerate(plain))


def _identifier(value: Any, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise InvalidEvaluationError(str(error)) from error


def _enum(value: Any, label: str, allowed: set[str]) -> str:
    result = _nonempty(value, label)
    if result not in allowed:
        raise InvalidEvaluationError(f"{label} is unsupported: {result}")
    return result


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidEvaluationError(f"{label} must be a nonempty string")
    return value


def _sha256(value: Any, label: str) -> str:
    result = _nonempty(value, label)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise InvalidEvaluationError(f"{label} must be a lowercase SHA-256 hex digest")
    return result


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidEvaluationError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidEvaluationError(f"{label} must be a nonnegative integer")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise InvalidEvaluationError(
            f"{label} has unexpected keys; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
