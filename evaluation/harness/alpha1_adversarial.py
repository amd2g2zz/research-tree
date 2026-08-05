"""Evaluator-owned semantic baselines for the tagged alpha1 release.

Public case manifests contain only replay inputs and oracle identifiers. The
unsafe outcomes live here so a worker cannot turn the expected failure into an
answer key. This harness does not claim that a current implementation still
has every defect; it only classifies a recorded observation against the
registered alpha1 oracle.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


ORACLE_OUTCOMES: dict[str, str] = {
    "alpha1-forged-validation": "forged passed status was accepted without an OracleRun",
    "alpha1-missing-evidence": "missing evidence reference did not block closure",
    "alpha1-filler-report": "filler report satisfied delivery without semantic claims",
    "alpha1-empty-frontier": "empty frontier was treated as completion",
    "alpha1-active-contradiction": "selected closure ignored an active contradiction",
    "alpha1-repeated-reconnaissance": "reconnaissance repeated without consuming an attempt",
    "alpha1-adapter-only-completion": "adapter completion bypassed core closure obligations",
    "alpha1-provider-failure": "provider failure stopped the run without a recovery successor",
    "alpha1-crash-recovery": "crash recovery lost an obligation or committed only a partial event",
}


class BaselineFixtureError(ValueError):
    """Raised when the public baseline manifest is not replayable."""


def load_manifest(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_manifest(value)
    return value


def validate_manifest(value: Mapping[str, Any]) -> None:
    if value.get("schema") != 1 or not isinstance(value.get("id"), str):
        raise BaselineFixtureError("alpha1 manifest must declare schema 1 and an id")
    baseline = value.get("baseline")
    if not isinstance(baseline, Mapping):
        raise BaselineFixtureError("alpha1 baseline metadata is required")
    commit = baseline.get("commit")
    if not isinstance(commit, str) or len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise BaselineFixtureError("alpha1 baseline must pin a full commit")
    if baseline.get("tag") != "0.0.1-a1":
        raise BaselineFixtureError("alpha1 baseline must pin tag 0.0.1-a1")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BaselineFixtureError("alpha1 manifest requires cases")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise BaselineFixtureError("alpha1 case must be an object")
        case_id = case.get("id")
        oracle_id = case.get("oracle_id")
        if not isinstance(case_id, str) or case_id in ids:
            raise BaselineFixtureError("alpha1 case ids must be unique")
        if not isinstance(oracle_id, str) or oracle_id not in ORACLE_OUTCOMES:
            raise BaselineFixtureError(f"unknown hidden oracle: {oracle_id!r}")
        if not isinstance(case.get("command"), str) or not case["command"].strip():
            raise BaselineFixtureError(f"case {case_id} requires a replay command")
        ids.add(case_id)


def evaluate_case(case: Mapping[str, Any], *, observed_unsafe: bool, fix_evidence: Sequence[str] = ()) -> dict[str, Any]:
    oracle_id = case.get("oracle_id")
    if oracle_id not in ORACLE_OUTCOMES:
        raise BaselineFixtureError(f"unknown hidden oracle: {oracle_id!r}")
    if observed_unsafe:
        return {
            "case_id": case.get("id"),
            "status": "vulnerability_reproduced",
            "oracle_id": oracle_id,
            "unsafe_outcome": ORACLE_OUTCOMES[oracle_id],
            "evidence": list(fix_evidence),
        }
    if not fix_evidence:
        return {
            "case_id": case.get("id"),
            "status": "inconclusive",
            "oracle_id": oracle_id,
            "reason": "safe behavior was observed without candidate evidence",
        }
    return {
        "case_id": case.get("id"),
        "status": "fix_confirmed",
        "oracle_id": oracle_id,
        "evidence": list(fix_evidence),
    }


def evaluate_manifest(manifest: Mapping[str, Any], observations: Mapping[str, bool]) -> dict[str, Any]:
    validate_manifest(manifest)
    results = [
        evaluate_case(case, observed_unsafe=bool(observations.get(case["id"], False)))
        for case in manifest["cases"]
    ]
    return {
        "schema": 1,
        "baseline": manifest["baseline"],
        "results": results,
        "vulnerabilities_reproduced": sum(item["status"] == "vulnerability_reproduced" for item in results),
        "inconclusive": sum(item["status"] == "inconclusive" for item in results),
    }
