"""Evaluator-owned oracle specifications and immutable runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class OracleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OracleSpec:
    oracle_id: str
    kind: str
    command: str
    expected: str

    @classmethod
    def create(cls, oracle_id: str, kind: str, command: str, *, expected: str) -> "OracleSpec":
        if not all(isinstance(value, str) and value.strip() for value in (oracle_id, kind, command, expected)):
            raise OracleError("OracleSpec fields must be nonempty")
        return cls(oracle_id, kind, command, expected)


@dataclass(frozen=True, slots=True)
class OracleRun:
    oracle_run_id: str
    oracle_spec_id: str
    attempt_id: str
    input_refs: tuple[Mapping[str, Any], ...]
    verdict: str
    environment_digest: str
    result: Mapping[str, Any]

    @classmethod
    def create(cls, oracle_run_id: str, spec: OracleSpec, *, attempt_id: str, input_refs: Sequence[Mapping[str, Any]], verdict: str, environment_digest: str, result: Mapping[str, Any]) -> "OracleRun":
        if verdict not in {"pass", "fail", "inconclusive", "unavailable"}:
            raise OracleError("unsupported oracle verdict")
        if not environment_digest:
            raise OracleError("environment_digest is required")
        return cls(oracle_run_id, spec.oracle_id, attempt_id, tuple(dict(ref) for ref in input_refs), verdict, environment_digest, dict(result))

    def to_dict(self) -> dict[str, Any]:
        return {"oracle_run_id": self.oracle_run_id, "oracle_spec_id": self.oracle_spec_id, "attempt_id": self.attempt_id, "input_refs": [dict(ref) for ref in self.input_refs], "verdict": self.verdict, "environment_digest": self.environment_digest, "result": dict(self.result)}
