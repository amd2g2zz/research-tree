"""Admission cross-check for the senior-user-ux-v2 baseline (issue #472, gate 9).

The v2 run must be admitted against the *registered* baseline, not against a
prose record alone. ``evaluation/baselines/senior-user-ux-v2-baseline.json``
is the machine-readable registry of record for the baseline run name and the
three role scores; ``docs/evaluation/research/senior-user-ux-v2-baseline.md``
renders the same numbers for humans. The registry's ``baseline`` payload is
sealed by ``content_digest`` (canonical-JSON SHA-256, the registered-baseline
``immutable-by-digest`` rule), and every load re-verifies it.

The run's declared baseline (the values the run configuration claims to be
anchored to) is cross-checked against the registry at run start:

- mismatch, missing/unreadable/invalid registry, or digest mismatch raises
  :class:`BaselineAdmissionError` with a canonical reason -- fail closed;
- a match produces a cross-check record that the governed run persists as its
  ``context-admission-record`` artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "evaluation" / "baselines" / "senior-user-ux-v2-baseline.json"
)
BASELINE_RUN_NAME = "senior-user-ux-20260820"
ROLE_KEYS = ("research-architect", "platform-engineering-integrator", "governance-auditor")


class BaselineAdmissionError(RuntimeError):
    """Raised when a run cannot be admitted against the registered baseline."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(reason if not detail else f"{reason}: {detail}")


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def baseline_digest(baseline: Mapping[str, Any]) -> str:
    """Digest-seal the baseline payload (immutable-by-digest registration)."""

    return "sha256:" + hashlib.sha256(canonical_json_bytes(baseline)).hexdigest()


def _validate_baseline(baseline: Any) -> dict[str, Any]:
    if not isinstance(baseline, dict):
        raise BaselineAdmissionError("baseline-registry-invalid", "baseline payload must be an object")
    run_name = baseline.get("run_name")
    if not isinstance(run_name, str) or not run_name:
        raise BaselineAdmissionError("baseline-registry-invalid", "baseline run_name must be a non-empty string")
    scores = baseline.get("role_scores")
    if not isinstance(scores, dict):
        raise BaselineAdmissionError("baseline-registry-invalid", "baseline role_scores must be an object")
    for role in ROLE_KEYS:
        score = scores.get(role)
        if not isinstance(score, dict) or isinstance(score.get("value"), bool) or not isinstance(
            score.get("value"), (int, float)
        ):
            raise BaselineAdmissionError("baseline-registry-invalid", f"role {role} must carry a numeric score value")
    return baseline


def load_baseline_registry(path: Path | None = None) -> dict[str, Any]:
    """Load the baseline registry and re-verify its immutable digest."""

    registry_path = (Path(path) if path is not None else DEFAULT_REGISTRY_PATH).resolve()
    if not registry_path.is_file():
        raise BaselineAdmissionError("baseline-registry-missing", str(registry_path))
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BaselineAdmissionError("baseline-registry-unreadable", str(error)) from error
    if not isinstance(registry, dict) or not isinstance(registry.get("id"), str):
        raise BaselineAdmissionError("baseline-registry-invalid", str(registry_path))
    baseline = _validate_baseline(registry.get("baseline"))
    if registry.get("content_digest") != baseline_digest(baseline):
        raise BaselineAdmissionError(
            "baseline-registry-digest-mismatch",
            f"content_digest does not seal the baseline payload of {registry_path.name}",
        )
    return registry


def cross_check(declared: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    """Cross-check the run's declared baseline against the registered baseline.

    Returns the admitted cross-check record, or raises
    :class:`BaselineAdmissionError` with a canonical fail-closed reason.
    """

    baseline = registry["baseline"]
    if declared.get("run_name") != baseline.get("run_name"):
        raise BaselineAdmissionError(
            "baseline-run-name-mismatch",
            f"declared {declared.get('run_name')!r} != registered {baseline.get('run_name')!r}",
        )
    declared_scores = declared.get("role_scores")
    if not isinstance(declared_scores, Mapping):
        raise BaselineAdmissionError("baseline-registry-invalid", "declared role_scores must be an object")
    admitted_scores: dict[str, float] = {}
    for role in ROLE_KEYS:
        if role not in declared_scores:
            raise BaselineAdmissionError(f"baseline-role-missing:{role}", "declared baseline omits a registered role")
        registered = baseline["role_scores"][role]
        if declared_scores[role] != registered["value"]:
            raise BaselineAdmissionError(
                f"baseline-role-score-mismatch:{role}",
                f"declared {declared_scores[role]!r} != registered {registered['value']!r}",
            )
        admitted_scores[role] = registered["value"]
    return {
        "status": "admitted",
        "run_name": baseline["run_name"],
        "role_scores": admitted_scores,
        "registry_id": registry["id"],
        "content_digest": registry["content_digest"],
    }
