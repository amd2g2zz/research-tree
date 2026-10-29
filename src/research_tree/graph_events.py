"""Graph event stream: typed vocabulary + payload validation (issue #546).

The event log is the sole write authority feeding the Kùzu object-graph
projection (docs/product/02-architecture.md 存储双层): SQLite keeps the
append-only hash chain, the graph is a replayable projection. This module is
the shared vocabulary used by both sides — it imports no storage engine.

Events are **state-carrying upserts** (plus additive edge facts), which makes
replay idempotent and rebuild-equality checkable by plain snapshot comparison.

verify_tier tokens map to docs/product/01-core-algorithms.md A2:
``rederive``=重推导, ``multi-source``=多源交叉, ``verbatim``=原文摘录,
``single-source``=单源未验, ``experiment``=experiment.
"""

from __future__ import annotations

from typing import Any, Mapping

GRAPH_EVENT_TYPES: tuple[str, ...] = (
    "claim.upsert",
    "claim.kill_edge",
    "stage.upsert",
    "stage.depends_on",
    "stage.contains",
    "evidence.upsert",
    "evidence.attach",
    "artifact.upsert",
    "artifact.link",
    "version.commit",
    "fork.edge",
)

CLAIM_SOURCES: tuple[str, ...] = ("user", "research")
CLAIM_WEIGHTS: tuple[str, ...] = ("make_or_break", "important", "minor")
VERIFY_TIERS: tuple[str, ...] = ("rederive", "multi-source", "verbatim", "single-source", "experiment")
VERDICTS: tuple[str, ...] = ("GO", "NO-GO", "PARK", "REFRAMED")

GENESIS_HASH = "0" * 64


class GraphEventError(ValueError):
    """Invalid graph event type or payload."""


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphEventError(f"payload must be a mapping: {label}")
    return dict(value)


def _check_keys(entry: Mapping[str, Any], required: set[str], optional: set[str], label: str) -> None:
    missing = required - set(entry)
    if missing:
        raise GraphEventError(f"{label} missing required keys: {sorted(missing)}")
    unexpected = set(entry) - required - optional
    if unexpected:
        raise GraphEventError(f"{label} has unexpected keys: {sorted(unexpected)}")


def _text(entry: Mapping[str, Any], key: str) -> str:
    value = entry[key]
    if not isinstance(value, str) or not value:
        raise GraphEventError(f'field "{key}" must be a non-empty string')
    return value


def _field(entry: Mapping[str, Any], key: str) -> str:
    value = entry[key]
    if not isinstance(value, str):
        raise GraphEventError(f'field "{key}" must be a string')
    return value


def _enum(entry: Mapping[str, Any], key: str, allowed: tuple[str, ...]) -> str:
    value = entry[key]
    if value not in allowed:
        raise GraphEventError(f'field "{key}" must be one of {list(allowed)}')
    return value


def _probability(entry: Mapping[str, Any], key: str) -> float:
    value = entry[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GraphEventError(f'field "{key}" must be a number')
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise GraphEventError(f'field "{key}" must lie in [0, 1]')
    return number


def _integer(entry: Mapping[str, Any], key: str, minimum: int) -> int:
    value = entry[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise GraphEventError(f'field "{key}" must be an integer')
    if value < minimum:
        raise GraphEventError(f'field "{key}" must be >= {minimum}')
    return value


def _boolean(entry: Mapping[str, Any], key: str, default: bool) -> bool:
    if key not in entry:
        return default
    value = entry[key]
    if not isinstance(value, bool):
        raise GraphEventError(f'field "{key}" must be a boolean')
    return value


def _distinct(first: str, second: str) -> None:
    if first == second:
        raise GraphEventError(f'ids must be distinct: "{first}" == "{second}"')


def _claim_upsert(payload: Mapping[str, Any]) -> dict[str, Any]:
    claim = _mapping(payload.get("claim"), "claim")
    _check_keys(claim, {"id", "text", "source", "weight", "posterior", "verify_tier"}, {"stale"}, "claim")
    return {
        "claim": {
            "id": _text(claim, "id"),
            "text": _field(claim, "text"),
            "source": _enum(claim, "source", CLAIM_SOURCES),
            "weight": _enum(claim, "weight", CLAIM_WEIGHTS),
            "posterior": _probability(claim, "posterior"),
            "verify_tier": _enum(claim, "verify_tier", VERIFY_TIERS),
            "stale": _boolean(claim, "stale", False),
        }
    }


def _pair(payload: Mapping[str, Any], first: str, second: str) -> dict[str, Any]:
    _check_keys(payload, {first, second}, set(), "payload")
    left = _text(payload, first)
    right = _text(payload, second)
    _distinct(left, right)
    return {first: left, second: right}


def _stage_upsert(payload: Mapping[str, Any]) -> dict[str, Any]:
    stage = _mapping(payload.get("stage"), "stage")
    _check_keys(stage, {"id", "title", "status"}, set(), "stage")
    return {
        "stage": {
            "id": _text(stage, "id"),
            "title": _field(stage, "title"),
            "status": _field(stage, "status"),
        }
    }


def _evidence_upsert(payload: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _mapping(payload.get("evidence"), "evidence")
    _check_keys(evidence, {"id", "digest", "origin"}, set(), "evidence")
    return {
        "evidence": {
            "id": _text(evidence, "id"),
            "digest": _text(evidence, "digest"),
            "origin": _field(evidence, "origin"),
        }
    }


def _artifact_upsert(payload: Mapping[str, Any]) -> dict[str, Any]:
    artifact = _mapping(payload.get("artifact"), "artifact")
    _check_keys(artifact, {"id", "kind", "digest"}, {"deleted"}, "artifact")
    return {
        "artifact": {
            "id": _text(artifact, "id"),
            "kind": _field(artifact, "kind"),
            "digest": _text(artifact, "digest"),
            "deleted": _boolean(artifact, "deleted", False),
        }
    }


def _version_commit(payload: Mapping[str, Any]) -> dict[str, Any]:
    version = _mapping(payload.get("version"), "version")
    _check_keys(version, {"id", "task_id", "v", "commit_hash", "verdict", "summary"}, set(), "version")
    return {
        "version": {
            "id": _text(version, "id"),
            "task_id": _text(version, "task_id"),
            "v": _integer(version, "v", 0),
            "commit_hash": _text(version, "commit_hash"),
            "verdict": _enum(version, "verdict", VERDICTS),
            "summary": _field(version, "summary"),
        }
    }


_VALIDATORS = {
    "claim.upsert": _claim_upsert,
    "claim.kill_edge": lambda payload: _pair(payload, "claim_id", "kill_target_id"),
    "stage.upsert": _stage_upsert,
    "stage.depends_on": lambda payload: _pair(payload, "stage_id", "depends_on_id"),
    "stage.contains": lambda payload: _pair(payload, "stage_id", "claim_id"),
    "evidence.upsert": _evidence_upsert,
    "evidence.attach": lambda payload: _pair(payload, "evidence_id", "claim_id"),
    "artifact.upsert": _artifact_upsert,
    "artifact.link": lambda payload: _pair(payload, "artifact_id", "claim_id"),
    "version.commit": _version_commit,
    "fork.edge": lambda payload: _pair(payload, "child_version_id", "parent_version_id"),
}


def validate_graph_event(event_type: Any, payload: Any) -> dict[str, Any]:
    """Validate one graph event and return its normalized payload.

    Raises :class:`GraphEventError` on unknown types or schema violations.
    """
    if not isinstance(event_type, str) or event_type not in GRAPH_EVENT_TYPES:
        raise GraphEventError(f"unknown graph event type: {event_type!r}")
    if not isinstance(payload, Mapping):
        raise GraphEventError("payload must be a mapping")
    return _VALIDATORS[event_type](payload)
