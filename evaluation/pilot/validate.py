"""Stdlib whitelist validation for paired-pilot-v1.json (issue #335).

Runtime src stays stdlib-only per ADR-007; the pilot manifest is an
evaluation asset, validated here with the repo's whitelist style.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

REQUIRED_TOP = ("schema_version", "pilot_id", "arms", "model", "host", "rubric_version", "seed", "cases", "created_at")
REQUIRED_CASE = ("id", "domain", "non_holdout", "difficulty", "task_prompt")
REQUIRED_ARM = ("label", "tag", "commit")


class PilotManifestError(ValueError):
    """Raised when the paired-pilot manifest violates its contract."""


def validate_manifest(value: Mapping[str, Any]) -> None:
    missing = [key for key in REQUIRED_TOP if key not in value]
    if missing:
        raise PilotManifestError(f"manifest missing required fields: {missing}")
    extra = set(value) - set(REQUIRED_TOP) - {"purpose", "case_count", "holdout_policy"}
    if extra:
        raise PilotManifestError(f"manifest has unknown fields: {sorted(extra)}")
    arms = value["arms"]
    if not isinstance(arms, Mapping) or set(arms) != {"A1", "A2"}:
        raise PilotManifestError("manifest must define exactly arms A1 and A2")
    for arm_id, arm in arms.items():
        if not isinstance(arm, Mapping) or any(key not in arm for key in REQUIRED_ARM):
            raise PilotManifestError(f"arm {arm_id} missing required fields")
    model = value["model"]
    if not isinstance(model, Mapping) or model.get("same_revision_both_arms") is not True:
        raise PilotManifestError("both arms must pin the same model revision (same_revision_both_arms)")
    cases = value["cases"]
    if not isinstance(cases, list) or not 8 <= len(cases) <= 12:
        raise PilotManifestError(
            f"case count must be within 8-12, got {len(cases) if isinstance(cases, list) else type(cases).__name__}"
        )
    domains: dict[str, int] = {}
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise PilotManifestError("case must be an object")
        missing_case = [key for key in REQUIRED_CASE if key not in case]
        if missing_case:
            raise PilotManifestError(f"case missing required fields: {missing_case}")
        if case["id"] in seen:
            raise PilotManifestError(f"duplicate case id: {case['id']}")
        seen.add(case["id"])
        if case.get("non_holdout") is not True:
            raise PilotManifestError(f"case {case['id']} must be marked non_holdout: pilot excludes holdout material")
        domains[case["domain"]] = domains.get(case["domain"], 0) + 1
    sparse = {name for name, count in domains.items() if count < 2}
    if sparse:
        raise PilotManifestError(f"every domain needs >=2 cases, sparse: {sorted(sparse)}")


def validate_manifest_file(path: str | Path) -> None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PilotManifestError("manifest must be a JSON object")
    validate_manifest(payload)


def main() -> int:
    validate_manifest_file(Path(__file__).with_name("paired-pilot-v1.json"))
    print("paired-pilot-v1.json: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
