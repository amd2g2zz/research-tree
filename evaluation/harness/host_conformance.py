"""Deterministic host-conformance case loading, comparison, and replay checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


CASE_SCHEMA = Path("evaluation/schemas/host-conformance-v1.schema.json")
RESULT_SCHEMA = Path("evaluation/schemas/host-conformance-result-v1.schema.json")
FAULTS = (
    "provider_interruption",
    "cancellation",
    "hook_loss",
    "process_kill",
    "stale_child",
    "modified_artifact",
    "resume",
    "fork",
)


class ConformanceError(ValueError):
    """Raised when a case, result, or comparison violates the gate contract."""


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConformanceError(f"{path.name} must be a JSON object")
    return payload


def load_case(path: Path) -> dict[str, Any]:
    case = _load(path)
    if case.get("schema_version") != 1:
        raise ConformanceError("case schema_version must be 1")
    leaves = case.get("leaves")
    if not isinstance(leaves, list) or len(leaves) != 2:
        raise ConformanceError("case must declare exactly two leaves")
    if {leaf["phase"] for leaf in leaves} != {"landscape"}:
        raise ConformanceError("leaves must be landscape phase")
    faults = case.get("faults")
    if not isinstance(faults, list) or not faults or any(fault not in FAULTS for fault in faults):
        raise ConformanceError(f"faults must be a non-empty subset of {FAULTS}")
    oracles = case.get("negative_oracles")
    if not isinstance(oracles, list) or not any(o.get("expect") == "rejected" for o in oracles):
        raise ConformanceError("case must include at least one rejecting negative oracle")
    expected = case.get("expected_canonical_sequence")
    if not isinstance(expected, list) or "contradiction_detected" not in [e.split(":")[0] for e in expected]:
        raise ConformanceError("expected sequence must include contradiction detection")
    return case


def check_negative_oracle(case: Mapping[str, Any], submission: Mapping[str, Any]) -> str:
    """Evaluate one negative-oracle submission; return pass/fail with reason."""

    kind = str(submission.get("kind", ""))
    observed_identity = submission.get("identity")
    anchor = submission.get("anchor")
    executed = submission.get("executed") is True
    if kind == "projected-identity" and observed_identity is not None:
        return "failed: projected identity accepted"
    if kind == "projected-identity":
        return "passed"
    if kind == "synthetic-finding" and anchor is None:
        return "failed: synthetic Finding Pack admitted without anchor"
    if kind == "synthetic-finding":
        return "passed"
    if kind == "capability-string":
        return "passed" if not executed else "failed: capability string treated as execution"
    return f"failed: unknown oracle kind {kind!r}"


def canonical_projection(events: Sequence[Mapping[str, Any]]) -> list[str]:
    """Project events to their canonical kind:attempt equivalence classes."""

    return [f"{event['kind']}:{event.get('attempt_id', '')}" for event in events]


def compare_sequences(expected: Sequence[str], observed: Sequence[str]) -> list[str]:
    """Return divergences between expected and observed canonical sequences."""

    divergences: list[str] = []
    expected_kinds = [item.split(":")[0] for item in expected]
    observed_kinds = [item.split(":")[0] for item in observed]
    for kind in ("attempt_started", "contradiction_detected", "retry"):
        if expected_kinds.count(kind) > observed_kinds.count(kind):
            divergences.append(
                f"missing {kind} events (expected {expected_kinds.count(kind)}, observed {observed_kinds.count(kind)})"
            )
    completions = sum(1 for item in observed if item.startswith("worker_finished"))
    if completions == 0:
        divergences.append("no verified worker_finished events")
    if any(item.startswith("worker_finished") for item in observed) and "validation:accepted" not in observed:
        divergences.append("verified leaves present but validation not accepted")
    return divergences


def check_replay(recorded_state: Mapping[str, Any], replayed_state: Mapping[str, Any]) -> dict[str, Any]:
    """Compare persisted-state replay against the recorded run state."""

    divergences: list[str] = []
    for key in ("accepted_attempts", "unresolved_work", "event_sequence"):
        if recorded_state.get(key) != replayed_state.get(key):
            divergences.append(f"{key} diverged")
    recorded_ids = sorted(str(a) for a in recorded_state.get("attempt_ids", []))
    replayed_ids = sorted(str(a) for a in replayed_state.get("attempt_ids", []))
    if recorded_ids != replayed_ids:
        divergences.append("attempt id sets diverged")
    return {"status": "passed" if not divergences else "failed", "divergences": divergences}
