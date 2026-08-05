"""Evaluator-owned oracle specifications and immutable runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any, Mapping, Sequence


class OracleError(ValueError):
    pass


_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


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
class OracleAttempt:
    oracle_attempt_id: str
    run_id: str
    action_attempt_id: str
    oracle_spec_id: str
    oracle_spec_version: int
    oracle_spec_digest: str
    method: str
    input_digests: tuple[str, ...]
    environment_digest: str
    toolchain_digest: str
    started_at: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OracleAttempt":
        required = {
            "oracle_attempt_id",
            "run_id",
            "action_attempt_id",
            "oracle_spec_id",
            "oracle_spec_version",
            "oracle_spec_digest",
            "method",
            "input_digests",
            "environment_digest",
            "toolchain_digest",
            "started_at",
        }
        if set(value) != required:
            raise OracleError("OracleAttempt contract fields mismatch")
        for field in ("oracle_attempt_id", "run_id", "action_attempt_id"):
            if not isinstance(value[field], str) or _ID_RE.fullmatch(value[field]) is None:
                raise OracleError(f"OracleAttempt {field} is invalid")
        if not isinstance(value["oracle_spec_id"], str) or not value["oracle_spec_id"].strip():
            raise OracleError("OracleAttempt oracle_spec_id is required")
        version = value["oracle_spec_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise OracleError("OracleAttempt oracle_spec_version must be positive")
        for field in ("oracle_spec_digest", "environment_digest", "toolchain_digest"):
            if not isinstance(value[field], str) or _DIGEST_RE.fullmatch(value[field]) is None:
                raise OracleError(f"OracleAttempt {field} must be lowercase SHA-256")
        if not isinstance(value["method"], str) or not value["method"].strip():
            raise OracleError("OracleAttempt method is required")
        inputs = value["input_digests"]
        if not isinstance(inputs, list) or any(
            not isinstance(item, str) or _DIGEST_RE.fullmatch(item) is None
            for item in inputs
        ):
            raise OracleError("OracleAttempt input_digests are invalid")
        try:
            started = datetime.fromisoformat(
                str(value["started_at"]).replace("Z", "+00:00")
            )
        except ValueError as error:
            raise OracleError("OracleAttempt started_at must be ISO-8601") from error
        if started.tzinfo is None or started.utcoffset() != timedelta(0):
            raise OracleError("OracleAttempt started_at must be UTC")
        return cls(
            oracle_attempt_id=value["oracle_attempt_id"],
            run_id=value["run_id"],
            action_attempt_id=value["action_attempt_id"],
            oracle_spec_id=value["oracle_spec_id"],
            oracle_spec_version=version,
            oracle_spec_digest=value["oracle_spec_digest"],
            method=value["method"],
            input_digests=tuple(inputs),
            environment_digest=value["environment_digest"],
            toolchain_digest=value["toolchain_digest"],
            started_at=started.astimezone(timezone.utc).isoformat(),
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "oracle_attempt_id": self.oracle_attempt_id,
            "run_id": self.run_id,
            "action_attempt_id": self.action_attempt_id,
            "oracle_spec_id": self.oracle_spec_id,
            "oracle_spec_version": self.oracle_spec_version,
            "oracle_spec_digest": self.oracle_spec_digest,
            "method": self.method,
            "input_digests": list(self.input_digests),
            "environment_digest": self.environment_digest,
            "toolchain_digest": self.toolchain_digest,
            "started_at": self.started_at,
        }


@dataclass(frozen=True, slots=True)
class OracleRun:
    oracle_run_id: str
    oracle_attempt_id: str
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
    result_artifact_refs: tuple[Mapping[str, Any], ...] = ()
    evaluator: str = "core-oracle"
    limitations: tuple[str, ...] = ()
    reproducibility_status: str = "reproducible"

    @classmethod
    def create(cls, oracle_run_id: str, spec: OracleSpec, *, attempt_id: str, input_refs: Sequence[Mapping[str, Any]], verdict: str, environment_digest: str, result: Mapping[str, Any], oracle_attempt_id: str | None = None, **contract: Any) -> "OracleRun":
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
        defaults["result_artifact_refs"] = _normalize_artifact_refs(
            defaults["result_artifact_refs"]
        )
        return cls(
            oracle_run_id=oracle_run_id,
            oracle_attempt_id=oracle_attempt_id or attempt_id,
            oracle_spec_id=spec.oracle_id,
            attempt_id=attempt_id,
            input_refs=input_values,
            verdict=verdict,
            environment_digest=environment_digest,
            result=dict(result),
            **defaults,
        )

    def to_dict(self) -> dict[str, Any]:
        return {"oracle_run_id": self.oracle_run_id, "oracle_attempt_id": self.oracle_attempt_id, "oracle_spec_id": self.oracle_spec_id, "attempt_id": self.attempt_id, "input_refs": [dict(ref) for ref in self.input_refs], "verdict": self.verdict, "environment_digest": self.environment_digest, "result": dict(self.result)}

    def to_contract_dict(self) -> dict[str, Any]:
        verdict = {"pass": "passed", "fail": "failed", "unavailable": "blocked"}.get(self.verdict, self.verdict)
        return {
            "oracle_run_id": self.oracle_run_id,
            "oracle_attempt_id": self.oracle_attempt_id,
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
            "result_artifact_refs": [dict(ref) for ref in self.result_artifact_refs],
            "evaluator": self.evaluator,
            "limitations": list(self.limitations),
            "reproducibility_status": self.reproducibility_status,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OracleRun":
        required = {"oracle_run_id", "oracle_attempt_id", "oracle_spec_id", "oracle_spec_version", "attempt_id", "method", "input_digests", "environment_digest", "toolchain_digest", "tool_event_refs", "verdict", "exit_code", "timed_out", "result_artifact_refs", "evaluator", "limitations", "reproducibility_status"}
        if set(value) != required:
            raise OracleError("OracleRun contract fields mismatch")
        if value["verdict"] not in {"passed", "failed", "inconclusive", "not_applicable", "blocked"}:
            raise OracleError("unsupported oracle contract verdict")
        if value["reproducibility_status"] not in {"reproducible", "flaky", "unavailable", "not_reproducible"}:
            raise OracleError("unsupported reproducibility status")
        if not isinstance(value["timed_out"], bool) or not isinstance(value["input_digests"], list) or not isinstance(value["result_artifact_refs"], list) or not isinstance(value["tool_event_refs"], list) or not isinstance(value["limitations"], list):
            raise OracleError("OracleRun collection fields are invalid")
        for field in ("oracle_run_id", "oracle_attempt_id", "attempt_id"):
            if not isinstance(value[field], str) or _ID_RE.fullmatch(value[field]) is None:
                raise OracleError(f"OracleRun {field} is invalid")
        if not isinstance(value["oracle_spec_id"], str) or not value["oracle_spec_id"].strip():
            raise OracleError("OracleRun oracle_spec_id is required")
        if isinstance(value["oracle_spec_version"], bool) or not isinstance(value["oracle_spec_version"], int) or value["oracle_spec_version"] < 1:
            raise OracleError("oracle_spec_version must be positive")
        if not isinstance(value["method"], str) or not value["method"].strip():
            raise OracleError("oracle method is required")
        for field in ("environment_digest", "toolchain_digest"):
            if not isinstance(value[field], str) or _DIGEST_RE.fullmatch(value[field]) is None:
                raise OracleError(f"OracleRun {field} must be lowercase SHA-256")
        if any(
            not isinstance(item, str) or _DIGEST_RE.fullmatch(item) is None
            for item in value["input_digests"]
        ):
            raise OracleError("OracleRun input_digests are invalid")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in value["tool_event_refs"]
        ):
            raise OracleError("OracleRun tool_event_refs are invalid")
        if any(not isinstance(item, str) for item in value["limitations"]):
            raise OracleError("OracleRun limitations are invalid")
        if not isinstance(value["evaluator"], str) or not value["evaluator"].strip():
            raise OracleError("OracleRun evaluator is required")
        if value["exit_code"] is not None and (
            isinstance(value["exit_code"], bool)
            or not isinstance(value["exit_code"], int)
        ):
            raise OracleError("OracleRun exit_code must be an integer or null")
        result_artifact_refs = _normalize_artifact_refs(value["result_artifact_refs"])
        return cls(
            oracle_run_id=str(value["oracle_run_id"]),
            oracle_attempt_id=str(value["oracle_attempt_id"]),
            oracle_spec_id=str(value["oracle_spec_id"]),
            attempt_id=str(value["attempt_id"]),
            input_refs=tuple({"digest": digest} for digest in value["input_digests"]),
            verdict={"passed": "pass", "failed": "fail", "blocked": "unavailable"}.get(value["verdict"], value["verdict"]),
            environment_digest=str(value["environment_digest"]),
            result={"status": value["verdict"]},
            oracle_spec_version=value["oracle_spec_version"],
            method=str(value["method"]),
            input_digests=tuple(value["input_digests"]),
            toolchain_digest=str(value["toolchain_digest"]),
            tool_event_refs=tuple(value["tool_event_refs"]),
            exit_code=value["exit_code"],
            timed_out=value["timed_out"],
            result_artifact_refs=result_artifact_refs,
            evaluator=str(value["evaluator"]),
            limitations=tuple(value["limitations"]),
            reproducibility_status=str(value["reproducibility_status"]),
        )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_artifact_refs(value: Any) -> tuple[dict[str, Any], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise OracleError("result_artifact_refs must be a sequence")
    required = {"run_id", "artifact_id", "revision", "content_hash"}
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, str]] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != required:
            raise OracleError(
                f"result_artifact_refs[{index}] contract fields mismatch"
            )
        run_id = item["run_id"]
        artifact_id = item["artifact_id"]
        revision = item["revision"]
        content_hash = item["content_hash"]
        if not isinstance(run_id, str) or not run_id.strip():
            raise OracleError(f"result_artifact_refs[{index}].run_id is required")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise OracleError(
                f"result_artifact_refs[{index}].artifact_id is required"
            )
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise OracleError(
                f"result_artifact_refs[{index}].revision must be positive"
            )
        if not isinstance(content_hash, str) or re.fullmatch(
            r"[0-9a-f]{64}", content_hash
        ) is None:
            raise OracleError(
                f"result_artifact_refs[{index}].content_hash must be lowercase SHA-256"
            )
        identity = (run_id, artifact_id, revision, content_hash)
        if identity in seen:
            raise OracleError("result_artifact_refs must not contain duplicates")
        seen.add(identity)
        normalized.append(
            {
                "run_id": run_id,
                "artifact_id": artifact_id,
                "revision": revision,
                "content_hash": content_hash,
            }
        )
    return tuple(normalized)


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
