"""Evaluator-owned oracle specifications and immutable runs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence


class OracleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OracleSpec:
    oracle_id: str
    kind: str
    command: str
    expected: str
    version: int = 1
    input_schema_digest: str = ""
    invocation_adapter: str = ""
    permissions: Mapping[str, Any] | None = None
    resource_limits: Mapping[str, int] | None = None
    timeout_seconds: int = 60
    expected_result_schema_digest: str = ""
    retry_policy: Mapping[str, Any] | None = None
    flaky_policy: str = "fail_closed"
    isolation_profile: str = "default"
    human_only: bool = False

    @classmethod
    def create(cls, oracle_id: str, kind: str, command: str, *, expected: str, **contract: Any) -> "OracleSpec":
        if not all(isinstance(value, str) and value.strip() for value in (oracle_id, kind, command, expected)):
            raise OracleError("OracleSpec fields must be nonempty")
        defaults = {
            "version": 1,
            "input_schema_digest": _digest("{}"),
            "invocation_adapter": command,
            "permissions": {"read_roots": [], "write_roots": [], "network": "none", "commands": [command]},
            "resource_limits": {"cpu_seconds": 60, "memory_bytes": 268435456, "output_bytes": 1048576},
            "timeout_seconds": 60,
            "expected_result_schema_digest": _digest(expected),
            "retry_policy": {"max_attempts": 1, "backoff_seconds": [], "switch_method_after": 1},
            "flaky_policy": "fail_closed",
            "isolation_profile": "default",
            "human_only": False,
        }
        defaults.update(contract)
        _validate_spec_contract(defaults)
        return cls(oracle_id, kind, command, expected, **defaults)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OracleSpec":
        required = {"oracle_spec_id", "version", "objective", "input_schema_digest", "invocation_adapter", "permissions", "resource_limits", "timeout_seconds", "expected_result_schema_digest", "retry_policy", "flaky_policy", "isolation_profile", "human_only"}
        if set(value) != required:
            raise OracleError("OracleSpec contract fields mismatch")
        _validate_spec_contract(value)
        return cls.create(
            value["oracle_spec_id"],
            "contract",
            value["invocation_adapter"],
            expected=value["objective"],
            version=value["version"],
            input_schema_digest=value["input_schema_digest"],
            invocation_adapter=value["invocation_adapter"],
            permissions=dict(value["permissions"]),
            resource_limits=dict(value["resource_limits"]),
            timeout_seconds=value["timeout_seconds"],
            expected_result_schema_digest=value["expected_result_schema_digest"],
            retry_policy=dict(value["retry_policy"]),
            flaky_policy=value["flaky_policy"],
            isolation_profile=value["isolation_profile"],
            human_only=value["human_only"],
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "oracle_spec_id": self.oracle_id,
            "version": self.version,
            "objective": self.expected,
            "input_schema_digest": self.input_schema_digest,
            "invocation_adapter": self.invocation_adapter,
            "permissions": dict(self.permissions or {}),
            "resource_limits": dict(self.resource_limits or {}),
            "timeout_seconds": self.timeout_seconds,
            "expected_result_schema_digest": self.expected_result_schema_digest,
            "retry_policy": dict(self.retry_policy or {}),
            "flaky_policy": self.flaky_policy,
            "isolation_profile": self.isolation_profile,
            "human_only": self.human_only,
        }


@dataclass(frozen=True, slots=True)
class OracleRun:
    oracle_run_id: str
    oracle_spec_id: str
    attempt_id: str
    input_refs: tuple[Mapping[str, Any], ...]
    verdict: str
    environment_digest: str
    result: Mapping[str, Any]
    oracle_spec_version: int = 1
    method: str = "legacy"
    input_digests: tuple[str, ...] = ()
    toolchain_digest: str = ""
    tool_event_refs: tuple[str, ...] = ()
    exit_code: int | None = None
    timed_out: bool = False
    result_artifact_refs: tuple[str, ...] = ()
    evaluator: str = "core-oracle"
    limitations: tuple[str, ...] = ()
    reproducibility_status: str = "reproducible"

    @classmethod
    def create(cls, oracle_run_id: str, spec: OracleSpec, *, attempt_id: str, input_refs: Sequence[Mapping[str, Any]], verdict: str, environment_digest: str, result: Mapping[str, Any], **contract: Any) -> "OracleRun":
        if verdict not in {"pass", "fail", "inconclusive", "unavailable"}:
            raise OracleError("unsupported oracle verdict")
        if not environment_digest:
            raise OracleError("environment_digest is required")
        input_values = tuple(dict(ref) for ref in input_refs)
        defaults = {
            "oracle_spec_version": spec.version,
            "method": spec.kind,
            "input_digests": tuple(str(ref.get("digest", ref.get("artifact_digest"))) for ref in input_values if ref.get("digest", ref.get("artifact_digest"))),
            "toolchain_digest": environment_digest,
            "tool_event_refs": (),
            "exit_code": 0 if verdict == "pass" else None,
            "timed_out": False,
            "result_artifact_refs": (),
            "evaluator": "core-oracle",
            "limitations": (),
            "reproducibility_status": "reproducible" if verdict != "unavailable" else "unavailable",
        }
        defaults.update(contract)
        if not isinstance(defaults["timed_out"], bool) or defaults["reproducibility_status"] not in {"reproducible", "flaky", "unavailable", "not_reproducible"}:
            raise OracleError("invalid OracleRun contract metadata")
        return cls(oracle_run_id, spec.oracle_id, attempt_id, input_values, verdict, environment_digest, dict(result), **defaults)

    def to_dict(self) -> dict[str, Any]:
        return {"oracle_run_id": self.oracle_run_id, "oracle_spec_id": self.oracle_spec_id, "attempt_id": self.attempt_id, "input_refs": [dict(ref) for ref in self.input_refs], "verdict": self.verdict, "environment_digest": self.environment_digest, "result": dict(self.result)}

    def to_contract_dict(self) -> dict[str, Any]:
        verdict = {"pass": "passed", "fail": "failed", "unavailable": "blocked"}.get(self.verdict, self.verdict)
        return {
            "oracle_run_id": self.oracle_run_id,
            "oracle_spec_id": self.oracle_spec_id,
            "oracle_spec_version": self.oracle_spec_version,
            "attempt_id": self.attempt_id,
            "method": self.method,
            "input_digests": list(self.input_digests),
            "environment_digest": self.environment_digest,
            "toolchain_digest": self.toolchain_digest,
            "tool_event_refs": list(self.tool_event_refs),
            "verdict": verdict,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "result_artifact_refs": list(self.result_artifact_refs),
            "evaluator": self.evaluator,
            "limitations": list(self.limitations),
            "reproducibility_status": self.reproducibility_status,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OracleRun":
        required = {"oracle_run_id", "oracle_spec_id", "oracle_spec_version", "attempt_id", "method", "input_digests", "environment_digest", "toolchain_digest", "tool_event_refs", "verdict", "exit_code", "timed_out", "result_artifact_refs", "evaluator", "limitations", "reproducibility_status"}
        if set(value) != required:
            raise OracleError("OracleRun contract fields mismatch")
        if value["verdict"] not in {"passed", "failed", "inconclusive", "not_applicable", "blocked"}:
            raise OracleError("unsupported oracle contract verdict")
        if value["reproducibility_status"] not in {"reproducible", "flaky", "unavailable", "not_reproducible"}:
            raise OracleError("unsupported reproducibility status")
        if not isinstance(value["timed_out"], bool) or not isinstance(value["input_digests"], list) or not isinstance(value["result_artifact_refs"], list) or not isinstance(value["tool_event_refs"], list):
            raise OracleError("OracleRun collection fields are invalid")
        if isinstance(value["oracle_spec_version"], bool) or not isinstance(value["oracle_spec_version"], int) or value["oracle_spec_version"] < 1:
            raise OracleError("oracle_spec_version must be positive")
        if not isinstance(value["method"], str) or not value["method"].strip():
            raise OracleError("oracle method is required")
        return cls(
            str(value["oracle_run_id"]), str(value["oracle_spec_id"]), str(value["attempt_id"]), tuple({"digest": digest} for digest in value["input_digests"]),
            {"passed": "pass", "failed": "fail", "blocked": "unavailable"}.get(value["verdict"], value["verdict"]),
            str(value["environment_digest"]), {"status": value["verdict"]},
            value["oracle_spec_version"], str(value["method"]), tuple(value["input_digests"]), str(value["toolchain_digest"]), tuple(value["tool_event_refs"]), value["exit_code"], value["timed_out"], tuple(value["result_artifact_refs"]), str(value["evaluator"]), tuple(value["limitations"]), str(value["reproducibility_status"]),
        )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_spec_contract(value: Mapping[str, Any]) -> None:
    for field in ("input_schema_digest", "expected_result_schema_digest"):
        if not isinstance(value.get(field), str) or len(value[field]) != 64:
            raise OracleError(f"{field} must be a SHA-256 digest")
    if not isinstance(value.get("version"), int) or value["version"] < 1 or not isinstance(value.get("timeout_seconds"), int) or value["timeout_seconds"] < 1:
        raise OracleError("OracleSpec version and timeout must be positive integers")
    if value.get("flaky_policy") not in {"fail_closed", "repeat_once_then_inconclusive", "repeat_until_stable"}:
        raise OracleError("unsupported flaky policy")
    if not isinstance(value.get("human_only"), bool) or not isinstance(value.get("permissions"), Mapping) or not isinstance(value.get("resource_limits"), Mapping) or not isinstance(value.get("retry_policy"), Mapping):
        raise OracleError("OracleSpec contract mappings are required")
