"""Canonical worker assignment and typed submission contracts."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping, Sequence


class WorkerContractError(ValueError):
    pass


ACTION_KINDS = frozenset({"landscape", "deep_dive", "adversarial", "validation", "method_switch", "reconnaissance", "question", "disagreement"})
SUBMISSION_STATUSES = frozenset({"submitted", "empty_submission", "malformed_submission", "partial_submission", "provider_failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class AttemptPolicy:
    max_attempts: int = 3
    method_switch_after: int = 1
    backoff_seconds: tuple[int, ...] = (1, 2, 4)
    retryable_failures: tuple[str, ...] = ("provider_failed", "timeout", "empty_submission")
    no_retry_failures: tuple[str, ...] = ("permission_denied", "integrity_failure", "authority_blocked")

    @classmethod
    def create(cls, *, max_attempts: int = 3, method_switch_after: int = 1, backoff_seconds: Sequence[int] = (1, 2, 4), retryable_failures: Sequence[str] = ("provider_failed", "timeout", "empty_submission"), no_retry_failures: Sequence[str] = ("permission_denied", "integrity_failure", "authority_blocked")) -> "AttemptPolicy":
        if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 3:
            raise WorkerContractError("max_attempts must be between one and three")
        if not isinstance(method_switch_after, int) or not 0 <= method_switch_after < max_attempts:
            raise WorkerContractError("method_switch_after must precede max_attempts")
        delays = tuple(int(item) for item in backoff_seconds)
        if len(delays) < max_attempts or any(item < 0 for item in delays):
            raise WorkerContractError("backoff_seconds must cover every attempt")
        return cls(max_attempts, method_switch_after, delays, tuple(str(item) for item in retryable_failures), tuple(str(item) for item in no_retry_failures))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"backoff_seconds": list(self.backoff_seconds), "retryable_failures": list(self.retryable_failures), "no_retry_failures": list(self.no_retry_failures)}


@dataclass(frozen=True, slots=True)
class CanonicalWorkItem:
    work_item_id: str
    slot_id: str
    action_kind: str
    objective: str
    inputs: tuple[str, ...]
    method: str
    expected_output: str
    success_oracle: str
    dependencies: tuple[str, ...]
    permission_profile: str
    attempt_policy: AttemptPolicy
    completion_evidence: tuple[str, ...]

    @classmethod
    def create(cls, *, work_item_id: str, slot_id: str, action_kind: str, objective: str, inputs: Sequence[str], method: str, expected_output: str, success_oracle: str, dependencies: Sequence[str] = (), permission_profile: str, attempt_policy: AttemptPolicy | Mapping[str, Any] | None = None, completion_evidence: Sequence[str] = ()) -> "CanonicalWorkItem":
        values = (work_item_id, slot_id, objective, method, expected_output, success_oracle, permission_profile)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise WorkerContractError("work item identity and contracts must be nonempty")
        if action_kind not in ACTION_KINDS:
            raise WorkerContractError("unsupported action_kind")
        if not all(isinstance(value, str) and value.strip() for value in inputs):
            raise WorkerContractError("inputs must be nonempty strings")
        policy = attempt_policy if isinstance(attempt_policy, AttemptPolicy) else AttemptPolicy.create(**dict(attempt_policy or {}))
        if not all(isinstance(value, str) and value.strip() for value in completion_evidence):
            raise WorkerContractError("completion_evidence must be nonempty strings")
        return cls(work_item_id, slot_id, action_kind, objective, tuple(inputs), method, expected_output, success_oracle, tuple(dependencies), permission_profile, policy, tuple(completion_evidence))

    def to_dict(self) -> dict[str, Any]:
        return {"work_item_id": self.work_item_id, "slot_id": self.slot_id, "action_kind": self.action_kind, "objective": self.objective, "inputs": list(self.inputs), "method": self.method, "expected_output": self.expected_output, "success_oracle": self.success_oracle, "dependencies": list(self.dependencies), "permission_profile": self.permission_profile, "attempt_policy": self.attempt_policy.to_dict(), "completion_evidence": list(self.completion_evidence)}


@dataclass(frozen=True, slots=True)
class FindingSubmission:
    attempt_id: str
    status: str
    observations: tuple[Mapping[str, Any], ...]
    evidence_refs: tuple[str, ...]
    uncertainties: tuple[str, ...]
    next_action: str
    errors: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FindingSubmission":
        if not isinstance(value, Mapping) or not isinstance(value.get("attempt_id"), str) or not value.get("attempt_id", "").strip():
            raise WorkerContractError("attempt_id is required")
        errors: list[str] = []
        raw_observations = value.get("observations", [])
        if not isinstance(raw_observations, list):
            errors.append("observations must be an array")
            observations: tuple[Mapping[str, Any], ...] = ()
        else:
            valid = [item for item in raw_observations if isinstance(item, Mapping) and str(item.get("claim", "")).strip()]
            observations = tuple(dict(item) for item in valid)
            if len(valid) != len(raw_observations):
                errors.append("one or more observations are malformed")
        evidence = value.get("evidence_refs", [])
        if not isinstance(evidence, list) or not all(isinstance(item, str) and item.strip() for item in evidence):
            errors.append("evidence_refs must be a string array")
            evidence = []
        uncertainties = value.get("uncertainties", value.get("remaining_uncertainties", []))
        if not isinstance(uncertainties, list):
            errors.append("uncertainties must be an array")
            uncertainties = []
        explicit_status = value.get("status")
        if explicit_status is not None and explicit_status not in SUBMISSION_STATUSES:
            raise WorkerContractError("unsupported submission status")
        if errors and observations:
            status = "partial_submission"
        elif errors:
            status = "malformed_submission"
        elif explicit_status is not None:
            status = str(explicit_status)
        elif not observations and not uncertainties:
            status = "empty_submission"
        else:
            status = "submitted"
        next_action = str(value.get("next_action", "retry" if status in {"empty_submission", "malformed_submission", "partial_submission"} else "review"))
        return cls(str(value["attempt_id"]), status, observations, tuple(evidence), tuple(str(item) for item in uncertainties if str(item).strip()), next_action, tuple(errors))

    def to_dict(self) -> dict[str, Any]:
        return {"attempt_id": self.attempt_id, "status": self.status, "observations": [dict(item) for item in self.observations], "evidence_refs": list(self.evidence_refs), "uncertainties": list(self.uncertainties), "next_action": self.next_action, "errors": list(self.errors)}
