"""Typed, revision-bound OracleSpec, OracleAttempt, and OracleRun artifacts.

The module deliberately models the execution boundary only.  It does not run
commands or own lifecycle state; callers persist the canonical payloads through
``RunStore`` and use the lineage validators before treating a run as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Any, ClassVar, Mapping, Sequence

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    validate_identifier,
)


ORACLE_SPEC_KIND = "oracle-spec"
ORACLE_ATTEMPT_KIND = "oracle-attempt"
ORACLE_RUN_KIND = "oracle-run"
# Explicit artifact-name aliases keep call sites readable when several kinds
# of revisions are in scope.
ORACLE_SPEC_ARTIFACT_KIND = ORACLE_SPEC_KIND
ORACLE_ATTEMPT_ARTIFACT_KIND = ORACLE_ATTEMPT_KIND
ORACLE_RUN_ARTIFACT_KIND = ORACLE_RUN_KIND
ORACLE_SCHEMA_VERSION = 1

ORACLE_VERDICTS = frozenset(
    {"passed", "failed", "inconclusive", "not_applicable", "blocked"}
)
REPRODUCIBILITY_STATUSES = frozenset(
    {"reproducible", "flaky", "unavailable", "not_reproducible"}
)
NETWORK_POLICIES = frozenset({"none", "allowlist", "recorded", "unrestricted"})
FLAKY_POLICIES = frozenset(
    {"fail_closed", "repeat_once_then_inconclusive", "repeat_until_stable"}
)


class OracleError(RuntimeStoreError):
    """Base error for malformed or non-authoritative oracle artifacts."""


class InvalidOracleError(OracleError):
    """Raised when an oracle payload or exact lineage contract is invalid."""


# The more descriptive name is convenient for callers that treat these as
# pure validators, while retaining the project-wide ``Invalid*Error`` shape.
OracleValidationError = InvalidOracleError


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidOracleError(f"{label} must be a non-empty string")
    return value


def _identifier(value: object, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise InvalidOracleError(str(error)) from error


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidOracleError(f"{label} must be a positive integer")
    return value


def _nonnegative_number(value: object, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise InvalidOracleError(f"{label} must be a finite number")
    if value < 0:
        raise InvalidOracleError(f"{label} must be non-negative")
    return value


def _digest(value: object, label: str) -> str:
    result = _text(value, label)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise InvalidOracleError(f"{label} must be lowercase SHA-256 hex")
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidOracleError(f"{label} must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise InvalidOracleError(
            f"{label} has unexpected keys; missing={missing}, extra={extra}"
        )


def _string_sequence(
    value: object,
    label: str,
    *,
    allow_empty: bool = True,
    unique: bool = False,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidOracleError(f"{label} must be a sequence of strings")
    result = tuple(_text(item, f"{label}[{index}]") for index, item in enumerate(value))
    if not allow_empty and not result:
        raise InvalidOracleError(f"{label} must not be empty")
    if unique and len(set(result)) != len(result):
        raise InvalidOracleError(f"{label} must not contain duplicates")
    return result


def _ref(value: object, label: str) -> ArtifactRef:
    if isinstance(value, ArtifactRef):
        return value
    try:
        return ArtifactRef.from_dict(value)
    except (InvalidIdentifierError, TypeError, ValueError, RuntimeStoreError) as error:
        raise InvalidOracleError(f"{label} must be an exact ArtifactRef: {error}") from error


def _refs(
    value: object,
    label: str,
    *,
    allow_empty: bool = True,
    unique: bool = True,
) -> tuple[ArtifactRef, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidOracleError(f"{label} must be a sequence of ArtifactRef values")
    result = tuple(_ref(item, f"{label}[{index}]") for index, item in enumerate(value))
    if not allow_empty and not result:
        raise InvalidOracleError(f"{label} must not be empty")
    if unique and len(set(result)) != len(result):
        raise InvalidOracleError(f"{label} must not contain duplicate references")
    return result


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _ref_dict(reference: ArtifactRef) -> dict[str, Any]:
    return reference.to_dict()


def _artifact_ref(artifact: ArtifactRevision) -> ArtifactRef:
    return ArtifactRef(artifact.round_id, artifact.id, artifact.revision)


def _require_revision(
    value: object,
    expected_kind: str,
    label: str,
) -> ArtifactRevision:
    if not isinstance(value, ArtifactRevision):
        raise InvalidOracleError(f"{label} must be an ArtifactRevision")
    if value.kind != expected_kind:
        raise InvalidOracleError(f"{label} must be a {expected_kind} artifact")
    return value


def _require_parent(revision: ArtifactRevision, reference: ArtifactRef, label: str) -> None:
    if reference not in revision.parent_refs:
        raise InvalidOracleError(
            f"{label} is missing exact parent lineage for "
            f"{reference.round_id}/{reference.artifact_id}@{reference.revision}"
        )


def _require_same_round(revision: ArtifactRevision, reference: ArtifactRef, label: str) -> None:
    if reference.round_id != revision.round_id:
        raise InvalidOracleError(f"{label} must belong to the same round as the artifact")


@dataclass(frozen=True, slots=True)
class OracleSpec:
    """An immutable declaration of one allowed validation boundary."""

    oracle_spec_id: str
    version: int
    objective: str
    input_schema_digest: str
    invocation_adapter: str
    permissions: Mapping[str, Any]
    resource_limits: Mapping[str, Any]
    timeout_seconds: int
    expected_result_schema_digest: str
    retry_policy: Mapping[str, Any]
    flaky_policy: str
    isolation_profile: str
    human_only: bool

    KIND: ClassVar[str] = ORACLE_SPEC_KIND
    SCHEMA_VERSION: ClassVar[int] = ORACLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_spec_fields(
            self.oracle_spec_id,
            self.version,
            self.objective,
            self.input_schema_digest,
            self.invocation_adapter,
            self.permissions,
            self.resource_limits,
            self.timeout_seconds,
            self.expected_result_schema_digest,
            self.retry_policy,
            self.flaky_policy,
            self.isolation_profile,
            self.human_only,
        )
        object.__setattr__(self, "permissions", _freeze(_normalize_permissions(self.permissions)))
        object.__setattr__(self, "resource_limits", _freeze(_normalize_resource_limits(self.resource_limits)))
        object.__setattr__(self, "retry_policy", _freeze(_normalize_retry_policy(self.retry_policy)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle_spec_id": self.oracle_spec_id,
            "version": self.version,
            "objective": self.objective,
            "input_schema_digest": self.input_schema_digest,
            "invocation_adapter": self.invocation_adapter,
            "permissions": _thaw(self.permissions),
            "resource_limits": _thaw(self.resource_limits),
            "timeout_seconds": self.timeout_seconds,
            "expected_result_schema_digest": self.expected_result_schema_digest,
            "retry_policy": _thaw(self.retry_policy),
            "flaky_policy": self.flaky_policy,
            "isolation_profile": self.isolation_profile,
            "human_only": self.human_only,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OracleSpec":
        data = _mapping(value, "OracleSpec payload")
        _exact_keys(
            data,
            {
                "oracle_spec_id",
                "version",
                "objective",
                "input_schema_digest",
                "invocation_adapter",
                "permissions",
                "resource_limits",
                "timeout_seconds",
                "expected_result_schema_digest",
                "retry_policy",
                "flaky_policy",
                "isolation_profile",
                "human_only",
            },
            "OracleSpec payload",
        )
        return cls(**dict(data))

    @classmethod
    def from_revision(
        cls,
        reference: ArtifactRef,
        revision: ArtifactRevision,
    ) -> "OracleSpec":
        stored = _require_revision(revision, ORACLE_SPEC_KIND, "OracleSpec revision")
        exact = _ref(reference, "OracleSpec reference")
        if exact != _artifact_ref(stored):
            raise InvalidOracleError("OracleSpec reference does not match its persisted revision")
        model = cls.from_dict(stored.payload)
        if model.oracle_spec_id != stored.id:
            raise InvalidOracleError("OracleSpec id does not match its artifact id")
        return model


@dataclass(frozen=True, slots=True)
class OracleAttempt:
    """A spec-bound attempt with exact current inputs and environment."""

    attempt_id: str
    oracle_spec_ref: ArtifactRef
    input_refs: tuple[ArtifactRef, ...]
    method: str
    environment_digest: str
    toolchain_digest: str | None = None

    KIND: ClassVar[str] = ORACLE_ATTEMPT_KIND
    SCHEMA_VERSION: ClassVar[int] = ORACLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.attempt_id, "attempt_id")
        if not isinstance(self.oracle_spec_ref, ArtifactRef):
            raise InvalidOracleError("oracle_spec_ref must be an ArtifactRef")
        if not isinstance(self.input_refs, tuple):
            raise InvalidOracleError("input_refs must be a tuple of ArtifactRef values")
        _refs(self.input_refs, "input_refs")
        _text(self.method, "method")
        _digest(self.environment_digest, "environment_digest")
        if self.toolchain_digest is not None:
            _digest(self.toolchain_digest, "toolchain_digest")

    @property
    def spec_ref(self) -> ArtifactRef:
        """Alias used by callers that name the relationship generically."""

        return self.oracle_spec_ref

    @property
    def oracle_spec_id(self) -> str:
        return self.oracle_spec_ref.artifact_id

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "attempt_id": self.attempt_id,
            "oracle_spec_ref": _ref_dict(self.oracle_spec_ref),
            "input_refs": [_ref_dict(reference) for reference in self.input_refs],
            "method": self.method,
            "environment_digest": self.environment_digest,
            "toolchain_digest": self.toolchain_digest,
        }
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OracleAttempt":
        data = _mapping(value, "OracleAttempt payload")
        _exact_keys(
            data,
            {
                "attempt_id",
                "oracle_spec_ref",
                "input_refs",
                "method",
                "environment_digest",
                "toolchain_digest",
            },
            "OracleAttempt payload",
        )
        return cls(
            attempt_id=data["attempt_id"],
            oracle_spec_ref=_ref(data["oracle_spec_ref"], "oracle_spec_ref"),
            input_refs=_refs(data["input_refs"], "input_refs"),
            method=data["method"],
            environment_digest=data["environment_digest"],
            toolchain_digest=data["toolchain_digest"],
        )

    @classmethod
    def from_revision(
        cls,
        reference: ArtifactRef,
        revision: ArtifactRevision,
    ) -> "OracleAttempt":
        stored = _require_revision(revision, ORACLE_ATTEMPT_KIND, "OracleAttempt revision")
        exact = _ref(reference, "OracleAttempt reference")
        if exact != _artifact_ref(stored):
            raise InvalidOracleError("OracleAttempt reference does not match its persisted revision")
        model = cls.from_dict(stored.payload)
        if model.attempt_id != stored.id:
            raise InvalidOracleError("OracleAttempt id does not match its artifact id")
        return model


@dataclass(frozen=True, slots=True)
class OracleRun:
    """An immutable evaluator result bound to one exact attempt and spec."""

    oracle_run_id: str
    oracle_spec_ref: ArtifactRef
    attempt_ref: ArtifactRef
    input_refs: tuple[ArtifactRef, ...]
    method: str
    environment_digest: str
    toolchain_digest: str
    tool_event_refs: tuple[ArtifactRef, ...]
    result_artifact_refs: tuple[ArtifactRef, ...]
    verdict: str
    exit_code: int | None
    timed_out: bool
    evaluator: str
    limitations: tuple[str, ...]
    reproducibility_status: str

    KIND: ClassVar[str] = ORACLE_RUN_KIND
    SCHEMA_VERSION: ClassVar[int] = ORACLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.oracle_run_id, "oracle_run_id")
        if not isinstance(self.oracle_spec_ref, ArtifactRef):
            raise InvalidOracleError("oracle_spec_ref must be an ArtifactRef")
        if not isinstance(self.attempt_ref, ArtifactRef):
            raise InvalidOracleError("attempt_ref must be an ArtifactRef")
        if not isinstance(self.input_refs, tuple):
            raise InvalidOracleError("input_refs must be a tuple of ArtifactRef values")
        if not isinstance(self.tool_event_refs, tuple):
            raise InvalidOracleError("tool_event_refs must be a tuple of ArtifactRef values")
        if not isinstance(self.result_artifact_refs, tuple):
            raise InvalidOracleError("result_artifact_refs must be a tuple of ArtifactRef values")
        _refs(self.input_refs, "input_refs")
        _refs(self.tool_event_refs, "tool_event_refs")
        _refs(self.result_artifact_refs, "result_artifact_refs")
        _text(self.method, "method")
        _digest(self.environment_digest, "environment_digest")
        _digest(self.toolchain_digest, "toolchain_digest")
        if self.verdict not in ORACLE_VERDICTS:
            raise InvalidOracleError(f"verdict is unsupported: {self.verdict!r}")
        if self.exit_code is not None and (
            isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int)
        ):
            raise InvalidOracleError("exit_code must be an integer or null")
        if not isinstance(self.timed_out, bool):
            raise InvalidOracleError("timed_out must be a boolean")
        if self.timed_out:
            if self.verdict not in {"inconclusive", "blocked"}:
                raise InvalidOracleError("timed_out runs must be inconclusive or blocked")
            if self.exit_code is not None:
                raise InvalidOracleError("timed_out runs must not report an exit_code")
        if self.verdict == "passed" and (self.timed_out or self.exit_code != 0):
            raise InvalidOracleError("passed runs require timed_out=false and exit_code=0")
        _text(self.evaluator, "evaluator")
        if not isinstance(self.limitations, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.limitations
        ):
            raise InvalidOracleError("limitations must be a tuple of non-empty strings")
        if self.reproducibility_status not in REPRODUCIBILITY_STATUSES:
            raise InvalidOracleError(
                f"reproducibility_status is unsupported: {self.reproducibility_status!r}"
            )

    @property
    def spec_ref(self) -> ArtifactRef:
        return self.oracle_spec_ref

    @property
    def oracle_spec_id(self) -> str:
        return self.oracle_spec_ref.artifact_id

    @property
    def attempt_id(self) -> str:
        return self.attempt_ref.artifact_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle_run_id": self.oracle_run_id,
            "oracle_spec_ref": _ref_dict(self.oracle_spec_ref),
            "attempt_ref": _ref_dict(self.attempt_ref),
            "input_refs": [_ref_dict(reference) for reference in self.input_refs],
            "method": self.method,
            "environment_digest": self.environment_digest,
            "toolchain_digest": self.toolchain_digest,
            "tool_event_refs": [_ref_dict(reference) for reference in self.tool_event_refs],
            "result_artifact_refs": [
                _ref_dict(reference) for reference in self.result_artifact_refs
            ],
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "evaluator": self.evaluator,
            "limitations": list(self.limitations),
            "reproducibility_status": self.reproducibility_status,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OracleRun":
        data = _mapping(value, "OracleRun payload")
        _exact_keys(
            data,
            {
                "oracle_run_id",
                "oracle_spec_ref",
                "attempt_ref",
                "input_refs",
                "method",
                "environment_digest",
                "toolchain_digest",
                "tool_event_refs",
                "result_artifact_refs",
                "verdict",
                "exit_code",
                "timed_out",
                "evaluator",
                "limitations",
                "reproducibility_status",
            },
            "OracleRun payload",
        )
        return cls(
            oracle_run_id=data["oracle_run_id"],
            oracle_spec_ref=_ref(data["oracle_spec_ref"], "oracle_spec_ref"),
            attempt_ref=_ref(data["attempt_ref"], "attempt_ref"),
            input_refs=_refs(data["input_refs"], "input_refs"),
            method=data["method"],
            environment_digest=data["environment_digest"],
            toolchain_digest=data["toolchain_digest"],
            tool_event_refs=_refs(data["tool_event_refs"], "tool_event_refs"),
            result_artifact_refs=_refs(
                data["result_artifact_refs"], "result_artifact_refs"
            ),
            verdict=data["verdict"],
            exit_code=data["exit_code"],
            timed_out=data["timed_out"],
            evaluator=data["evaluator"],
            limitations=_string_sequence(data["limitations"], "limitations"),
            reproducibility_status=data["reproducibility_status"],
        )

    @classmethod
    def from_revision(
        cls,
        reference: ArtifactRef,
        revision: ArtifactRevision,
    ) -> "OracleRun":
        stored = _require_revision(revision, ORACLE_RUN_KIND, "OracleRun revision")
        exact = _ref(reference, "OracleRun reference")
        if exact != _artifact_ref(stored):
            raise InvalidOracleError("OracleRun reference does not match its persisted revision")
        model = cls.from_dict(stored.payload)
        if model.oracle_run_id != stored.id:
            raise InvalidOracleError("OracleRun id does not match its artifact id")
        return model


def _normalize_permissions(value: Mapping[str, Any]) -> dict[str, Any]:
    data = _mapping(value, "permissions")
    _exact_keys(data, {"read_roots", "write_roots", "network", "commands"}, "permissions")
    return {
        "read_roots": list(_string_sequence(data["read_roots"], "permissions.read_roots", unique=True)),
        "write_roots": list(_string_sequence(data["write_roots"], "permissions.write_roots", unique=True)),
        "network": _enum(data["network"], "permissions.network", NETWORK_POLICIES),
        "commands": list(_string_sequence(data["commands"], "permissions.commands", unique=True)),
    }


def _normalize_resource_limits(value: Mapping[str, Any]) -> dict[str, int]:
    data = _mapping(value, "resource_limits")
    _exact_keys(data, {"cpu_seconds", "memory_bytes", "output_bytes"}, "resource_limits")
    return {
        "cpu_seconds": _positive_int(data["cpu_seconds"], "resource_limits.cpu_seconds"),
        "memory_bytes": _positive_int(data["memory_bytes"], "resource_limits.memory_bytes"),
        "output_bytes": _positive_int(data["output_bytes"], "resource_limits.output_bytes"),
    }


def _normalize_retry_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    data = _mapping(value, "retry_policy")
    _exact_keys(data, {"max_attempts", "backoff_seconds", "switch_method_after"}, "retry_policy")
    backoff_value = data["backoff_seconds"]
    if isinstance(backoff_value, (str, bytes)) or not isinstance(backoff_value, Sequence):
        raise InvalidOracleError("retry_policy.backoff_seconds must be a sequence")
    backoff = tuple(
        _nonnegative_number(item, f"retry_policy.backoff_seconds[{index}]")
        for index, item in enumerate(backoff_value)
    )
    return {
        "max_attempts": _positive_int(data["max_attempts"], "retry_policy.max_attempts"),
        "backoff_seconds": list(backoff),
        "switch_method_after": _positive_int(
            data["switch_method_after"], "retry_policy.switch_method_after"
        ),
    }


def _enum(value: object, label: str, allowed: frozenset[str]) -> str:
    result = _text(value, label)
    if result not in allowed:
        raise InvalidOracleError(f"{label} is unsupported: {result!r}")
    return result


def _validate_spec_fields(
    oracle_spec_id: object,
    version: object,
    objective: object,
    input_schema_digest: object,
    invocation_adapter: object,
    permissions: object,
    resource_limits: object,
    timeout_seconds: object,
    expected_result_schema_digest: object,
    retry_policy: object,
    flaky_policy: object,
    isolation_profile: object,
    human_only: object,
) -> None:
    _identifier(oracle_spec_id, "oracle_spec_id")
    _positive_int(version, "version")
    _text(objective, "objective")
    _digest(input_schema_digest, "input_schema_digest")
    _text(invocation_adapter, "invocation_adapter")
    _normalize_permissions(_mapping(permissions, "permissions"))
    _normalize_resource_limits(_mapping(resource_limits, "resource_limits"))
    _positive_int(timeout_seconds, "timeout_seconds")
    _digest(expected_result_schema_digest, "expected_result_schema_digest")
    _normalize_retry_policy(_mapping(retry_policy, "retry_policy"))
    _enum(flaky_policy, "flaky_policy", FLAKY_POLICIES)
    _text(isolation_profile, "isolation_profile")
    if not isinstance(human_only, bool):
        raise InvalidOracleError("human_only must be a boolean")


def validate_oracle_spec_payload(value: Mapping[str, Any]) -> None:
    """Validate a canonical OracleSpec payload before persistence."""

    OracleSpec.from_dict(value)


def validate_oracle_attempt_payload(value: Mapping[str, Any]) -> None:
    """Validate a canonical OracleAttempt payload before persistence."""

    OracleAttempt.from_dict(value)


def validate_oracle_run_payload(value: Mapping[str, Any]) -> None:
    """Validate a canonical OracleRun payload before persistence."""

    OracleRun.from_dict(value)


def validate_oracle_spec_revision(
    reference: ArtifactRef,
    revision: ArtifactRevision,
) -> OracleSpec:
    """Parse and identity-check one persisted OracleSpec revision."""

    return OracleSpec.from_revision(reference, revision)


def validate_oracle_attempt_revision(
    reference: ArtifactRef,
    revision: ArtifactRevision,
) -> OracleAttempt:
    """Parse and identity-check one persisted OracleAttempt revision."""

    return OracleAttempt.from_revision(reference, revision)


def validate_oracle_run_revision(
    reference: ArtifactRef,
    revision: ArtifactRevision,
) -> OracleRun:
    """Parse and identity-check one persisted OracleRun revision."""

    return OracleRun.from_revision(reference, revision)


def validate_oracle_attempt_lineage(
    attempt_revision: ArtifactRevision,
    spec_revision: ArtifactRevision,
    *,
    input_revisions: Sequence[ArtifactRevision] = (),
) -> OracleAttempt:
    """Validate an attempt's exact spec/input references and parent lineage."""

    attempt_stored = _require_revision(
        attempt_revision, ORACLE_ATTEMPT_KIND, "OracleAttempt revision"
    )
    spec_stored = _require_revision(spec_revision, ORACLE_SPEC_KIND, "OracleSpec revision")
    attempt = OracleAttempt.from_revision(_artifact_ref(attempt_stored), attempt_stored)
    spec = OracleSpec.from_revision(_artifact_ref(spec_stored), spec_stored)
    spec_ref = _artifact_ref(spec_stored)
    _require_same_round(attempt_stored, spec_ref, "oracle_spec_ref")
    if attempt.oracle_spec_ref != spec_ref:
        raise InvalidOracleError("OracleAttempt does not bind the supplied OracleSpec revision")
    _require_parent(attempt_stored, spec_ref, "OracleAttempt")
    for input_ref in attempt.input_refs:
        _require_same_round(attempt_stored, input_ref, "input_ref")
        _require_parent(attempt_stored, input_ref, "OracleAttempt")
    if input_revisions:
        for item in input_revisions:
            if not isinstance(item, ArtifactRevision):
                raise InvalidOracleError("input_revisions must contain ArtifactRevision values")
        expected = tuple(_artifact_ref(item) for item in input_revisions)
        if expected != attempt.input_refs:
            raise InvalidOracleError("OracleAttempt input_refs do not match supplied revisions")
        for item in input_revisions:
            if item.round_id != attempt_stored.round_id:
                raise InvalidOracleError("OracleAttempt input revision belongs to another round")
    # Keep the local variable meaningful: parsing the spec is also the typed
    # check that its payload remains canonical before lineage is trusted.
    del spec
    return attempt


def validate_oracle_run_lineage(
    run_revision: ArtifactRevision,
    spec_revision: ArtifactRevision,
    attempt_revision: ArtifactRevision,
    *,
    input_revisions: Sequence[ArtifactRevision] = (),
    result_revisions: Sequence[ArtifactRevision] = (),
    tool_event_revisions: Sequence[ArtifactRevision] = (),
) -> OracleRun:
    """Validate exact spec/attempt/input/result/tool-event run lineage."""

    run_stored = _require_revision(run_revision, ORACLE_RUN_KIND, "OracleRun revision")
    spec_stored = _require_revision(spec_revision, ORACLE_SPEC_KIND, "OracleSpec revision")
    attempt_stored = _require_revision(
        attempt_revision, ORACLE_ATTEMPT_KIND, "OracleAttempt revision"
    )
    run = OracleRun.from_revision(_artifact_ref(run_stored), run_stored)
    spec = OracleSpec.from_revision(_artifact_ref(spec_stored), spec_stored)
    attempt = validate_oracle_attempt_lineage(
        attempt_stored,
        spec_stored,
        input_revisions=input_revisions,
    )
    spec_ref = _artifact_ref(spec_stored)
    attempt_ref = _artifact_ref(attempt_stored)
    _require_same_round(run_stored, spec_ref, "oracle_spec_ref")
    _require_same_round(run_stored, attempt_ref, "attempt_ref")
    if run.oracle_spec_ref != spec_ref:
        raise InvalidOracleError("OracleRun does not bind the supplied OracleSpec revision")
    if run.attempt_ref != attempt_ref:
        raise InvalidOracleError("OracleRun does not bind the supplied OracleAttempt revision")
    if attempt.oracle_spec_ref != spec_ref:
        raise InvalidOracleError("OracleAttempt is bound to a different OracleSpec revision")
    if run.input_refs != attempt.input_refs:
        raise InvalidOracleError("OracleRun input_refs do not match its OracleAttempt")
    if run.method != attempt.method:
        raise InvalidOracleError("OracleRun method does not match its OracleAttempt")
    if run.environment_digest != attempt.environment_digest:
        raise InvalidOracleError("OracleRun environment_digest does not match its OracleAttempt")
    if attempt.toolchain_digest is not None and run.toolchain_digest != attempt.toolchain_digest:
        raise InvalidOracleError("OracleRun toolchain_digest does not match its OracleAttempt")
    for reference in (
        spec_ref,
        attempt_ref,
        *run.input_refs,
        *run.tool_event_refs,
        *run.result_artifact_refs,
    ):
        _require_same_round(run_stored, reference, "OracleRun parent reference")
        _require_parent(run_stored, reference, "OracleRun")
    _validate_revisions_match(
        run.input_refs,
        input_revisions,
        "OracleRun input_refs",
    )
    _validate_revisions_match(
        run.result_artifact_refs,
        result_revisions,
        "OracleRun result_artifact_refs",
    )
    _validate_revisions_match(
        run.tool_event_refs,
        tool_event_revisions,
        "OracleRun tool_event_refs",
    )
    del spec
    return run


def _validate_revisions_match(
    references: tuple[ArtifactRef, ...],
    revisions: Sequence[ArtifactRevision],
    label: str,
) -> None:
    if not revisions:
        return
    for item in revisions:
        if not isinstance(item, ArtifactRevision):
            raise InvalidOracleError(f"{label} revisions must be ArtifactRevision values")
    expected = tuple(_artifact_ref(item) for item in revisions)
    if expected != references:
        raise InvalidOracleError(f"{label} do not match supplied revisions")


__all__ = [
    "ASSESSMENT_KIND",
    "FLAKY_POLICIES",
    "NETWORK_POLICIES",
    "ORACLE_ATTEMPT_KIND",
    "ORACLE_ATTEMPT_ARTIFACT_KIND",
    "ORACLE_RUN_KIND",
    "ORACLE_RUN_ARTIFACT_KIND",
    "ORACLE_SCHEMA_VERSION",
    "ORACLE_SPEC_KIND",
    "ORACLE_SPEC_ARTIFACT_KIND",
    "ORACLE_VERDICTS",
    "REPRODUCIBILITY_STATUSES",
    "InvalidOracleError",
    "OracleAttempt",
    "OracleError",
    "OracleRun",
    "OracleSpec",
    "OracleValidationError",
    "OracleService",
    "SlotClosureAssessor",
    "SlotClosureAssessment",
    "ClosureAssessmentError",
    "validate_oracle_attempt_lineage",
    "validate_oracle_attempt_payload",
    "validate_oracle_run_lineage",
    "validate_oracle_run_payload",
    "validate_oracle_run_revision",
    "validate_oracle_spec_payload",
    "validate_oracle_spec_revision",
    "validate_oracle_attempt_revision",
]


def __getattr__(name: str) -> Any:
    """Expose closure services lazily without creating an import cycle."""

    if name in {"ASSESSMENT_KIND", "ClosureAssessmentError", "OracleService", "SlotClosureAssessor", "SlotClosureAssessment"}:
        from . import closure

        return getattr(closure, name)
    raise AttributeError(name)
