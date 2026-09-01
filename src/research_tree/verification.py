"""Risk-proportionate execution evidence without host-side code execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    freeze_payload,
    thaw_json,
    validate_identifier,
)

EXECUTION_CHECKS = (
    "targeted_spike",
    "independent_implementation_run",
)
FAILURE_CATEGORIES = frozenset(
    {
        "intent",
        "repository_fit",
        "decision_evidence",
        "design_detail",
        "implementation_task",
        "oracle_quality",
    }
)
FAILURE_CATEGORY_GATES = {
    "intent": "intent_alignment",
    "repository_fit": "repository_fit",
    "decision_evidence": "traceability",
    "design_detail": "decision_closure",
    "implementation_task": "implementation_readiness",
    "oracle_quality": "implementation_readiness",
}
STRUCTURAL_GATES = (
    "intent_alignment",
    "decision_closure",
    "traceability",
    "repository_fit",
    "implementation_readiness",
    "operational_quality",
)
RISK_EXECUTION_CHECK = {
    "default": None,
    "medium": "targeted_spike",
    "high": "independent_implementation_run",
}
HIGH_RUN_STEPS = frozenset({"build", "hidden_acceptance", "regression"})


class VerificationError(RuntimeStoreError):
    """Base error for an isolated verification request or its evidence."""


class InvalidVerificationError(VerificationError):
    """Raised when an execution result cannot be safely persisted."""


@dataclass(frozen=True, slots=True)
class VerificationFailure:
    """A normalized cause and its current-round remediation target."""

    category: str
    summary: str
    decision_slot_id: str | None = None
    work_item_id: str | None = None


@dataclass(frozen=True, slots=True)
class IsolatedVerificationResult:
    """Evidence returned by a caller-provided isolated execution adapter."""

    check_kind: str
    status: str
    commands: Sequence[Mapping[str, Any]]
    results: Sequence[Mapping[str, Any]]
    isolation: Mapping[str, Any]
    failure: VerificationFailure | None = None


@dataclass(frozen=True, slots=True)
class IsolatedVerificationRequest:
    """The only data surface an isolated adapter is allowed to receive.

    ``baselines`` intentionally excludes live paths, origin locators, host
    environment data, and secret material. ``technical_package`` is an exact
    immutable package snapshot rather than a caller-owned object that an
    adapter could mutate.
    """

    round_id: str
    risk_tier: str
    check_kind: str
    baselines: tuple[Mapping[str, Any], ...]
    technical_package: Mapping[str, Any]
    isolation_requirements: Mapping[str, Any]


@runtime_checkable
class IsolatedVerificationAdapter(Protocol):
    """Run one check outside the research-tree host process."""

    def run(self, request: IsolatedVerificationRequest) -> IsolatedVerificationResult:
        """Return evidence from an adapter-managed isolated environment."""


@dataclass(frozen=True, slots=True)
class RiskVerificationAssessment:
    """Internal evidence and normalized failures returned to canonical readiness."""

    evidence: Mapping[str, Any]
    failures: tuple[VerificationFailure, ...]


def assess_risk_verification(
    *,
    round_id: str,
    risk_tier: str,
    technical_package: ArtifactRevision,
    repositories: Sequence[ArtifactRevision],
    adapter: IsolatedVerificationAdapter | None,
) -> RiskVerificationAssessment:
    """Build bounded execution evidence without running repository code here."""

    tier = _enum(risk_tier, "risk_tier", set(RISK_EXECUTION_CHECK))
    if not isinstance(technical_package, ArtifactRevision):
        raise InvalidVerificationError("technical_package must be an ArtifactRevision")
    if technical_package.round_id != round_id:
        raise InvalidVerificationError("technical_package must belong to verification round")
    baselines = _sanitized_baselines(repositories, round_id)
    package_ref = _artifact_ref_dict(technical_package)
    package_document = _mapping(technical_package.payload.get("document"), "technical_package document")
    package_snapshot = freeze_payload(
        {
            "ref": package_ref,
            "content_hash": technical_package.content_hash,
            "document": package_document,
        }
    )
    check = RISK_EXECUTION_CHECK[tier]
    policy = {
        "structural_checks": list(STRUCTURAL_GATES),
        "execution_check": check,
    }
    evidence: dict[str, Any] = {
        "risk_tier": tier,
        "policy": policy,
        "baselines": list(baselines),
        "technical_package": {
            "ref": package_ref,
            "content_hash": technical_package.content_hash,
        },
        "executed_checks": [],
        "skipped_checks": [],
        "failures": [],
        "same_round_follow_ups": [],
    }
    failures: list[VerificationFailure] = []

    if check is None:
        if adapter is not None:
            raise InvalidVerificationError("default risk policy does not accept an execution verification adapter")
        for skipped_check in EXECUTION_CHECKS:
            evidence["skipped_checks"].append(
                {
                    "check": skipped_check,
                    "reason": "The default risk policy selects structural verification only.",
                }
            )
    else:
        other_check = next(item for item in EXECUTION_CHECKS if item != check)
        evidence["skipped_checks"].append(
            {
                "check": other_check,
                "reason": "This execution check is not selected by the current risk policy.",
            }
        )
        if adapter is None:
            evidence["skipped_checks"].append(
                {
                    "check": check,
                    "reason": _missing_adapter_reason(tier),
                }
            )
            if tier == "high":
                failures.append(
                    VerificationFailure(
                        category="implementation_task",
                        summary=(
                            "High-risk readiness requires an independent implementation run, "
                            "but no isolated verification adapter was supplied."
                        ),
                    )
                )
        else:
            request = IsolatedVerificationRequest(
                round_id=round_id,
                risk_tier=tier,
                check_kind=check,
                baselines=tuple(freeze_payload(item) for item in baselines),
                technical_package=package_snapshot,
                isolation_requirements=freeze_payload(_isolation_requirements()),
            )
            normalized, result_failures = _run_adapter(adapter, request)
            evidence["executed_checks"].append(normalized)
            failures.extend(result_failures)

    evidence["failures"] = [_failure_dict(failure) for failure in failures]
    return RiskVerificationAssessment(
        evidence=freeze_payload(evidence),
        failures=tuple(failures),
    )


def validate_risk_verification_payload(payload: Mapping[str, Any]) -> None:
    """Validate the immutable RT-011 readiness extension recursively."""

    data = _mapping(payload, "risk_verification")
    _require_exact_keys(
        data,
        {
            "risk_tier",
            "policy",
            "baselines",
            "technical_package",
            "executed_checks",
            "skipped_checks",
            "failures",
            "same_round_follow_ups",
        },
        "risk_verification",
    )
    tier = _enum(data["risk_tier"], "risk_verification.risk_tier", set(RISK_EXECUTION_CHECK))
    policy = _mapping(data["policy"], "risk_verification.policy")
    _require_exact_keys(policy, {"structural_checks", "execution_check"}, "risk_verification.policy")
    if tuple(_strings(policy["structural_checks"], "risk_verification.policy.structural_checks")) != STRUCTURAL_GATES:
        raise InvalidVerificationError("risk_verification policy must retain the RT-008 structural gates")
    expected_check = RISK_EXECUTION_CHECK[tier]
    if policy["execution_check"] != expected_check:
        raise InvalidVerificationError("risk_verification policy does not match risk tier")

    for index, baseline in enumerate(_mappings(data["baselines"], "risk_verification.baselines")):
        label = f"risk_verification.baselines[{index}]"
        _require_exact_keys(baseline, {"input_ref", "revision", "anchors"}, label)
        _validate_ref(baseline["input_ref"], f"{label}.input_ref")
        _validate_revision(baseline["revision"], f"{label}.revision")
        for anchor_index, anchor in enumerate(_mappings(baseline["anchors"], f"{label}.anchors")):
            anchor_label = f"{label}.anchors[{anchor_index}]"
            _require_exact_keys(anchor, {"path", "symbol"}, anchor_label)
            _nonempty(anchor["path"], f"{anchor_label}.path")
            if anchor["symbol"] is not None:
                _nonempty(anchor["symbol"], f"{anchor_label}.symbol")

    package = _mapping(data["technical_package"], "risk_verification.technical_package")
    _require_exact_keys(package, {"ref", "content_hash"}, "risk_verification.technical_package")
    _validate_ref(package["ref"], "risk_verification.technical_package.ref")
    _sha256(package["content_hash"], "risk_verification.technical_package.content_hash")

    executed = _mappings(data["executed_checks"], "risk_verification.executed_checks")
    skipped = _mappings(data["skipped_checks"], "risk_verification.skipped_checks")
    seen_checks: set[str] = set()
    for index, check in enumerate(executed):
        label = f"risk_verification.executed_checks[{index}]"
        _require_exact_keys(
            check,
            {"check", "status", "commands", "results", "isolation", "failure"},
            label,
        )
        kind = _enum(check["check"], f"{label}.check", set(EXECUTION_CHECKS))
        if kind in seen_checks:
            raise InvalidVerificationError(f"risk_verification repeats check {kind}")
        seen_checks.add(kind)
        status = _enum(check["status"], f"{label}.status", {"pass", "fail"})
        command_names = _validate_commands(check["commands"], f"{label}.commands")
        result_names, result_statuses = _validate_results(check["results"], f"{label}.results")
        if command_names != result_names:
            raise InvalidVerificationError(f"{label} commands and results must have the same names")
        isolation_safe = _validate_isolation(check["isolation"], f"{label}.isolation")
        failure = check["failure"]
        if status == "pass":
            if failure is not None:
                raise InvalidVerificationError(f"{label}.failure must be null for a passing check")
            if not isolation_safe:
                raise InvalidVerificationError(f"{label} cannot pass with an unsafe isolation attestation")
            if any(item != "pass" for item in result_statuses.values()):
                raise InvalidVerificationError(f"{label} cannot pass while a named result is not pass")
        else:
            _validate_failure(failure, f"{label}.failure")
        if kind == "independent_implementation_run" and status == "pass":
            if not set(command_names) >= HIGH_RUN_STEPS:
                raise InvalidVerificationError(f"{label} must record build, hidden_acceptance, and regression commands")
            if not set(result_names) >= HIGH_RUN_STEPS:
                raise InvalidVerificationError(f"{label} must record build, hidden_acceptance, and regression results")
    for index, check in enumerate(skipped):
        label = f"risk_verification.skipped_checks[{index}]"
        _require_exact_keys(check, {"check", "reason"}, label)
        kind = _enum(check["check"], f"{label}.check", set(EXECUTION_CHECKS))
        if kind in seen_checks:
            raise InvalidVerificationError(f"risk_verification repeats check {kind}")
        seen_checks.add(kind)
        _nonempty(check["reason"], f"{label}.reason")
    if seen_checks != set(EXECUTION_CHECKS):
        raise InvalidVerificationError("risk_verification must account for every execution check")
    if expected_check is None and executed:
        raise InvalidVerificationError("default risk policy cannot execute an execution-level check")
    if expected_check is not None and any(item["check"] != expected_check for item in executed):
        raise InvalidVerificationError("executed check does not match the selected risk policy")

    failures = _mappings(data["failures"], "risk_verification.failures")
    for index, failure in enumerate(failures):
        _validate_failure(failure, f"risk_verification.failures[{index}]")
        if failure["decision_slot_id"] is None:
            raise InvalidVerificationError(
                f"risk_verification.failures[{index}] must be assigned to a current Decision Slot"
            )
    if tier == "high" and not executed and not any(item["category"] == "implementation_task" for item in failures):
        raise InvalidVerificationError("a skipped high-risk implementation run must fail implementation readiness")
    follow_ups = _mappings(data["same_round_follow_ups"], "risk_verification.same_round_follow_ups")
    if len(follow_ups) != len(failures):
        raise InvalidVerificationError("each execution failure must create exactly one same-round follow-up")
    for index, follow_up in enumerate(follow_ups):
        label = f"risk_verification.same_round_follow_ups[{index}]"
        _require_exact_keys(
            follow_up,
            {"category", "decision_slot_id", "work_item_id", "action", "summary"},
            label,
        )
        _enum(follow_up["category"], f"{label}.category", set(FAILURE_CATEGORIES))
        _identifier(follow_up["decision_slot_id"], f"{label}.decision_slot_id")
        if follow_up["work_item_id"] is not None:
            _identifier(follow_up["work_item_id"], f"{label}.work_item_id")
        if follow_up["action"] != "replan":
            raise InvalidVerificationError(f"{label}.action must be replan")
        _nonempty(follow_up["summary"], f"{label}.summary")
        failure = failures[index]
        if any(
            follow_up[field] != failure[field] for field in ("category", "decision_slot_id", "work_item_id", "summary")
        ):
            raise InvalidVerificationError(f"{label} must mirror its normalized execution failure")

    recorded_failures = {
        (item["category"], item["summary"], item["decision_slot_id"], item["work_item_id"]) for item in failures
    }
    for index, check in enumerate(executed):
        failure = check["failure"]
        if failure is None:
            continue
        key = (
            failure["category"],
            failure["summary"],
            failure["decision_slot_id"],
            failure["work_item_id"],
        )
        if key not in recorded_failures:
            raise InvalidVerificationError(
                f"risk_verification.executed_checks[{index}].failure is missing from failures"
            )


def _run_adapter(
    adapter: IsolatedVerificationAdapter,
    request: IsolatedVerificationRequest,
) -> tuple[dict[str, Any], tuple[VerificationFailure, ...]]:
    if not isinstance(adapter, IsolatedVerificationAdapter):
        raise InvalidVerificationError("verification_adapter must implement run(request)")
    try:
        raw = adapter.run(request)
    except Exception as error:  # Adapter failures become inspectable same-round evidence.
        failure = VerificationFailure(
            category="implementation_task",
            summary=f"The isolated verification adapter failed before returning evidence: {type(error).__name__}.",
        )
        return (
            {
                "check": request.check_kind,
                "status": "fail",
                "commands": [],
                "results": [],
                "isolation": {
                    "host_secrets_exposed": False,
                    "repository_mutated": False,
                    "isolated_working_copy": False,
                    "network_access": "disabled",
                },
                "failure": _failure_dict(failure),
            },
            (failure,),
        )
    return _normalize_result(raw, request)


def _normalize_result(
    value: IsolatedVerificationResult,
    request: IsolatedVerificationRequest,
) -> tuple[dict[str, Any], tuple[VerificationFailure, ...]]:
    if not isinstance(value, IsolatedVerificationResult):
        raise InvalidVerificationError("verification_adapter.run must return an IsolatedVerificationResult")
    check = _enum(value.check_kind, "verification result check_kind", set(EXECUTION_CHECKS))
    if check != request.check_kind:
        raise InvalidVerificationError("verification result check_kind must match the requested risk-policy check")
    status = _enum(value.status, "verification result status", {"pass", "fail"})
    commands = _normalize_commands(value.commands, "verification result commands")
    results = _normalize_results(value.results, "verification result results")
    if {item["name"] for item in commands} != {item["name"] for item in results}:
        raise InvalidVerificationError("verification result commands and results must have the same names")
    isolation = _normalize_isolation(value.isolation, "verification result isolation")
    failure = _normalize_failure(value.failure, "verification result failure")
    if status == "pass" and failure is not None:
        raise InvalidVerificationError("a passing verification result cannot contain a failure")
    if status == "fail" and failure is None:
        raise InvalidVerificationError("a failed verification result must identify one failure category")
    if status == "pass" and any(item["status"] != "pass" for item in results):
        raise InvalidVerificationError("a passing verification result must have only passing named results")
    if check == "independent_implementation_run" and status == "pass":
        names = {item["name"] for item in commands}
        if not names >= HIGH_RUN_STEPS:
            raise InvalidVerificationError(
                "a passing high-risk implementation run must include build, hidden_acceptance, and regression"
            )

    failures: list[VerificationFailure] = []
    safe, safety_failure = _isolation_failure(isolation)
    if not safe:
        status = "fail"
        failure = safety_failure
    if status == "fail":
        assert failure is not None
        failures.append(failure)
    return (
        {
            "check": check,
            "status": status,
            "commands": commands,
            "results": results,
            "isolation": isolation,
            "failure": None if failure is None else _failure_dict(failure),
        },
        tuple(failures),
    )


def _sanitized_baselines(repositories: Sequence[ArtifactRevision], round_id: str) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for repository in sorted(repositories, key=lambda item: (item.id, item.revision)):
        if not isinstance(repository, ArtifactRevision) or repository.round_id != round_id:
            raise InvalidVerificationError("repository baseline must be an exact artifact from verification round")
        payload = _mapping(repository.payload, f"repository input {repository.id}")
        if payload.get("kind") != "repository":
            raise InvalidVerificationError(f"artifact {repository.id} is not a repository input")
        baseline = _mapping(payload.get("repository_baseline"), f"repository baseline {repository.id}")
        anchors: list[dict[str, Any]] = []
        for index, anchor in enumerate(_mappings(baseline.get("anchors"), f"repository anchors {repository.id}")):
            label = f"repository anchors {repository.id}[{index}]"
            _require_exact_keys(anchor, {"path", "symbol"}, label)
            anchors.append(
                {
                    "path": _nonempty(anchor["path"], f"{label}.path"),
                    "symbol": None if anchor["symbol"] is None else _nonempty(anchor["symbol"], f"{label}.symbol"),
                }
            )
        result.append(
            {
                "input_ref": _artifact_ref_dict(repository),
                "revision": _normalized_revision(payload.get("revision"), f"repository revision {repository.id}"),
                "anchors": anchors,
            }
        )
    return tuple(result)


def _normalized_revision(value: Any, label: str) -> dict[str, Any]:
    revision = _mapping(value, label)
    _require_exact_keys(revision, {"branch", "commit", "sha256", "observed_at"}, label)
    for nullable in ("branch", "commit"):
        if revision[nullable] is not None:
            _nonempty(revision[nullable], f"{label}.{nullable}")
    return {
        "branch": revision["branch"],
        "commit": revision["commit"],
        "sha256": _sha256(revision["sha256"], f"{label}.sha256"),
        "observed_at": _nonempty(revision["observed_at"], f"{label}.observed_at"),
    }


def _normalize_commands(value: Any, label: str) -> list[dict[str, str]]:
    commands = _mappings(value, label)
    normalized: list[dict[str, str]] = []
    names: set[str] = set()
    for index, command in enumerate(commands):
        item_label = f"{label}[{index}]"
        _require_exact_keys(command, {"name", "command"}, item_label)
        name = _check_name(command["name"], f"{item_label}.name")
        if name in names:
            raise InvalidVerificationError(f"{label} repeats command {name}")
        names.add(name)
        normalized.append({"name": name, "command": _nonempty(command["command"], f"{item_label}.command")})
    return normalized


def _normalize_results(value: Any, label: str) -> list[dict[str, str]]:
    results = _mappings(value, label)
    normalized: list[dict[str, str]] = []
    names: set[str] = set()
    for index, result in enumerate(results):
        item_label = f"{label}[{index}]"
        _require_exact_keys(result, {"name", "status", "summary"}, item_label)
        name = _check_name(result["name"], f"{item_label}.name")
        if name in names:
            raise InvalidVerificationError(f"{label} repeats result {name}")
        names.add(name)
        normalized.append(
            {
                "name": name,
                "status": _enum(result["status"], f"{item_label}.status", {"pass", "fail", "skipped"}),
                "summary": _nonempty(result["summary"], f"{item_label}.summary"),
            }
        )
    return normalized


def _normalize_isolation(value: Any, label: str) -> dict[str, Any]:
    isolation = _mapping(value, label)
    _require_exact_keys(
        isolation,
        {
            "host_secrets_exposed",
            "repository_mutated",
            "isolated_working_copy",
            "network_access",
        },
        label,
    )
    for field in ("host_secrets_exposed", "repository_mutated", "isolated_working_copy"):
        if not isinstance(isolation[field], bool):
            raise InvalidVerificationError(f"{label}.{field} must be a boolean")
    return {
        "host_secrets_exposed": isolation["host_secrets_exposed"],
        "repository_mutated": isolation["repository_mutated"],
        "isolated_working_copy": isolation["isolated_working_copy"],
        "network_access": _enum(
            isolation["network_access"],
            f"{label}.network_access",
            {"disabled", "restricted", "enabled"},
        ),
    }


def _normalize_failure(value: Any, label: str) -> VerificationFailure | None:
    if value is None:
        return None
    if not isinstance(value, VerificationFailure):
        raise InvalidVerificationError(f"{label} must be a VerificationFailure or None")
    category = _enum(value.category, f"{label}.category", set(FAILURE_CATEGORIES))
    summary = _nonempty(value.summary, f"{label}.summary")
    slot_id = (
        None if value.decision_slot_id is None else _identifier(value.decision_slot_id, f"{label}.decision_slot_id")
    )
    work_id = None if value.work_item_id is None else _identifier(value.work_item_id, f"{label}.work_item_id")
    if slot_id is None and work_id is None:
        raise InvalidVerificationError(f"{label} must identify a Decision Slot or Work Item")
    return VerificationFailure(category, summary, slot_id, work_id)


def _isolation_failure(isolation: Mapping[str, Any]) -> tuple[bool, VerificationFailure | None]:
    unsafe: list[str] = []
    if isolation["repository_mutated"]:
        unsafe.append("the source repository was mutated")
    if isolation["host_secrets_exposed"]:
        unsafe.append("host secrets were exposed")
    if not isolation["isolated_working_copy"]:
        unsafe.append("no isolated working copy was attested")
    if isolation["network_access"] != "disabled":
        unsafe.append("network access was not disabled")
    if not unsafe:
        return True, None
    category = "repository_fit" if isolation["repository_mutated"] else "implementation_task"
    return (
        False,
        VerificationFailure(
            category=category,
            summary="Isolation attestation failed: " + "; ".join(unsafe) + ".",
        ),
    )


def _isolation_requirements() -> dict[str, Any]:
    return {
        "host_secrets_exposed": False,
        "repository_mutated": False,
        "isolated_working_copy": True,
        "network_access": "disabled",
    }


def _missing_adapter_reason(tier: str) -> str:
    if tier == "high":
        return "A high-risk independent implementation run is required but no isolated adapter was supplied."
    return "No isolated adapter was supplied for the optional medium-risk targeted spike."


def _failure_dict(failure: VerificationFailure) -> dict[str, Any]:
    return {
        "category": failure.category,
        "summary": failure.summary,
        "decision_slot_id": failure.decision_slot_id,
        "work_item_id": failure.work_item_id,
    }


def _validate_commands(value: Any, label: str) -> set[str]:
    return {item["name"] for item in _normalize_commands(value, label)}


def _validate_results(value: Any, label: str) -> tuple[set[str], dict[str, str]]:
    normalized = _normalize_results(value, label)
    return {item["name"] for item in normalized}, {item["name"]: item["status"] for item in normalized}


def _validate_isolation(value: Any, label: str) -> bool:
    isolation = _normalize_isolation(value, label)
    return _isolation_failure(isolation)[0]


def _validate_failure(value: Any, label: str) -> None:
    failure = _mapping(value, label)
    _require_exact_keys(failure, {"category", "summary", "decision_slot_id", "work_item_id"}, label)
    _enum(failure["category"], f"{label}.category", set(FAILURE_CATEGORIES))
    _nonempty(failure["summary"], f"{label}.summary")
    if failure["decision_slot_id"] is not None:
        _identifier(failure["decision_slot_id"], f"{label}.decision_slot_id")
    if failure["work_item_id"] is not None:
        _identifier(failure["work_item_id"], f"{label}.work_item_id")


def _validate_revision(value: Any, label: str) -> None:
    _normalized_revision(value, label)


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
        raise InvalidVerificationError(f"{label} must be a sequence of mappings")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(plain):
        if not isinstance(item, Mapping):
            raise InvalidVerificationError(f"{label}[{index}] must be a mapping")
        result.append(item)
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    plain = thaw_json(value)
    if not isinstance(plain, Mapping):
        raise InvalidVerificationError(f"{label} must be a mapping")
    return plain


def _strings(value: Any, label: str) -> tuple[str, ...]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidVerificationError(f"{label} must be a sequence of strings")
    return tuple(_nonempty(item, label) for item in plain)


def _identifier(value: Any, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise InvalidVerificationError(str(error)) from error


def _check_name(value: Any, label: str) -> str:
    result = _nonempty(value, label)
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    if (
        len(result) > 64
        or result[0] not in "abcdefghijklmnopqrstuvwxyz"
        or any(character not in allowed for character in result)
    ):
        raise InvalidVerificationError(
            f"{label} must be a lowercase check label using letters, digits, underscores, or hyphens"
        )
    return result


def _enum(value: Any, label: str, allowed: set[str]) -> str:
    result = _nonempty(value, label)
    if result not in allowed:
        raise InvalidVerificationError(f"{label} is unsupported: {result}")
    return result


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidVerificationError(f"{label} must be a nonempty string")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidVerificationError(f"{label} must be a positive integer")
    return value


def _sha256(value: Any, label: str) -> str:
    result = _nonempty(value, label)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise InvalidVerificationError(f"{label} must be a lowercase SHA-256 hex digest")
    return result


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise InvalidVerificationError(
            f"{label} has unexpected keys; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
