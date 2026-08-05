"""Registry-bounded lifecycle transition projection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LifecycleError(ValueError):
    pass


def _registry() -> dict[str, Any]:
    path = Path(__file__).parents[2] / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries" / "lifecycle-matrix-v1.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError("lifecycle registry is unavailable") from exc


def transition_table() -> tuple[dict[str, Any], ...]:
    transitions = _registry().get("transitions", [])
    if not isinstance(transitions, list):
        raise LifecycleError("lifecycle registry transitions are invalid")
    return tuple(dict(item) for item in transitions)


def allowed_transition(current: str, event: str) -> bool:
    states = set(_registry().get("state_vocabulary", {}).get("active", [])) | set(_registry().get("state_vocabulary", {}).get("resumable", [])) | set(_registry().get("state_vocabulary", {}).get("terminal", []))
    if current not in states:
        raise LifecycleError(f"unknown lifecycle state: {current}")
    return any(item.get("from") == current and item.get("event") == event for item in transition_table())
