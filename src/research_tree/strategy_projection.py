"""Immutable, host-neutral strategy projection for the handoff boundary."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .domain import ArtifactRef, DataIntegrityError, canonical_json_bytes, thaw_json

STRATEGY_PROJECTION_KIND = "strategy-projection"
STRATEGY_PROJECTION_SCHEMA_VERSION = 1
_STATUSES = frozenset({"draft", "displayed", "confirmed", "superseded"})
_STAGE_BY_STATE = {
    "alignment": 1,
    "handoff_pending": 2,
    "autonomous_research": 3,
    "synthesis": 3,
    "readiness": 3,
    "delivery_pending": 3,
    "delivery_ready": 4,
    "awaiting_acceptance": 4,
    "completed": 4,
}


class StrategyProjectionError(DataIntegrityError):
    """Raised when a projection is incomplete, stale, or malformed."""


def macro_stage(state: str, *, prior_stage: int | None = None) -> int:
    """Map canonical lifecycle states to requester-visible macro stages."""

    if state in _STAGE_BY_STATE:
        return _STAGE_BY_STATE[state]
    if state in {"paused", "blocked"}:
        if prior_stage not in {1, 2, 3, 4}:
            raise StrategyProjectionError("prior_stage is required for paused or blocked state")
        return prior_stage
    if state in {"superseded", "authority_blocked", "failed"} and prior_stage in {1, 2, 3, 4}:
        return prior_stage
    raise StrategyProjectionError(f"unknown lifecycle state: {state}")


def _json_value(value: Any, label: str) -> Any:
    if isinstance(value, ArtifactRef):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _json_value(child, f"{label}.{key}") for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(child, label) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise StrategyProjectionError(f"{label} must be JSON-compatible")


@dataclass(frozen=True, slots=True)
class StrategyProjection:
    projection_id: str
    run_id: str
    decision_frame_ref: ArtifactRef
    alignment_handoff_ref: ArtifactRef
    target_ref: ArtifactRef
    current_understanding: str
    assumptions: tuple[Any, ...]
    decision_targets: tuple[Any, ...]
    tracks: tuple[Any, ...]
    method_hypotheses: tuple[Any, ...]
    depth: str
    evidence_expectations: tuple[Any, ...]
    autonomy_envelope: Mapping[str, Any]
    replanning_policy: Mapping[str, Any]
    success_oracles: tuple[Any, ...]
    delivery_contract: Mapping[str, Any]
    stop_rule: str
    revision: int
    status: str
    display_digest: str
    content_hash: str

    @classmethod
    def create(cls, **values: Any) -> "StrategyProjection":
        required = {
            "projection_id",
            "run_id",
            "decision_frame_ref",
            "alignment_handoff_ref",
            "target_ref",
            "current_understanding",
            "assumptions",
            "decision_targets",
            "tracks",
            "method_hypotheses",
            "depth",
            "evidence_expectations",
            "autonomy_envelope",
            "replanning_policy",
            "success_oracles",
            "delivery_contract",
            "stop_rule",
            "revision",
            "status",
        }
        missing = sorted(required - set(values))
        if missing:
            raise StrategyProjectionError("missing fields: " + ", ".join(missing))
        refs = (values["decision_frame_ref"], values["alignment_handoff_ref"], values["target_ref"])
        if not all(isinstance(ref, ArtifactRef) for ref in refs):
            raise StrategyProjectionError("parent refs must be ArtifactRef values")
        run_id = values["run_id"]
        if not isinstance(run_id, str) or not run_id:
            raise StrategyProjectionError("run_id must be non-empty")
        if any(ref.round_id != run_id for ref in refs):
            raise StrategyProjectionError("all parent refs must share run_id")
        if not isinstance(values["current_understanding"], str) or not values["current_understanding"].strip():
            raise StrategyProjectionError("current_understanding must be non-empty")
        if not isinstance(values["stop_rule"], str) or not values["stop_rule"].strip():
            raise StrategyProjectionError("stop_rule must be non-empty")
        revision = values["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise StrategyProjectionError("revision must be positive")
        status = values["status"]
        if status not in _STATUSES:
            raise StrategyProjectionError("status must be draft, displayed, confirmed, or superseded")
        if values["depth"] not in {"bounded", "deep", "recursive"}:
            raise StrategyProjectionError("depth must be bounded, deep, or recursive")
        for key in (
            "assumptions",
            "decision_targets",
            "tracks",
            "method_hypotheses",
            "evidence_expectations",
            "success_oracles",
        ):
            if not isinstance(values[key], Sequence) or isinstance(values[key], (str, bytes)) or not values[key]:
                raise StrategyProjectionError(f"{key} must contain at least one item")
        for key in ("autonomy_envelope", "replanning_policy", "delivery_contract"):
            if not isinstance(values[key], Mapping) or not values[key]:
                raise StrategyProjectionError(f"{key} must be a non-empty object")
        normalized: dict[str, Any] = {}
        for key in required:
            normalized[key] = _json_value(values[key], key)
        normalized["decision_frame_ref"] = refs[0]
        normalized["alignment_handoff_ref"] = refs[1]
        normalized["target_ref"] = refs[2]
        normalized["assumptions"] = tuple(normalized["assumptions"])
        normalized["decision_targets"] = tuple(normalized["decision_targets"])
        normalized["tracks"] = tuple(normalized["tracks"])
        normalized["method_hypotheses"] = tuple(normalized["method_hypotheses"])
        normalized["evidence_expectations"] = tuple(normalized["evidence_expectations"])
        normalized["success_oracles"] = tuple(normalized["success_oracles"])
        display_payload = cls._display_payload_from(normalized)
        display_digest = sha256(canonical_json_bytes(display_payload)).hexdigest()
        content_hash = sha256(canonical_json_bytes({**display_payload, "display_digest": display_digest})).hexdigest()
        return cls(**normalized, display_digest=display_digest, content_hash=content_hash)

    @staticmethod
    def _display_payload_from(values: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "schema_version": STRATEGY_PROJECTION_SCHEMA_VERSION,
            "kind": STRATEGY_PROJECTION_KIND,
            **{
                key: _json_value(values[key], key)
                for key in (
                    "projection_id",
                    "run_id",
                    "decision_frame_ref",
                    "alignment_handoff_ref",
                    "target_ref",
                    "current_understanding",
                    "assumptions",
                    "decision_targets",
                    "tracks",
                    "method_hypotheses",
                    "depth",
                    "evidence_expectations",
                    "autonomy_envelope",
                    "replanning_policy",
                    "success_oracles",
                    "delivery_contract",
                    "stop_rule",
                    "revision",
                    "status",
                )
            },
        }
        return payload

    @property
    def kind(self) -> str:
        return STRATEGY_PROJECTION_KIND

    @property
    def id(self) -> str:
        return self.projection_id

    @property
    def display_payload(self) -> dict[str, Any]:
        return self._display_payload_from(self._values())

    def _values(self) -> dict[str, Any]:
        return {
            key: _json_value(getattr(self, key), key)
            for key in self.__dataclass_fields__
            if key not in {"display_digest", "content_hash"}
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.display_payload,
            "display_payload": self.display_payload,
            "display_digest": self.display_digest,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StrategyProjection":
        if not isinstance(value, Mapping):
            raise StrategyProjectionError("projection must be an object")
        value = thaw_json(value)
        expected_keys = {
            "schema_version",
            "kind",
            "projection_id",
            "run_id",
            "decision_frame_ref",
            "alignment_handoff_ref",
            "target_ref",
            "current_understanding",
            "assumptions",
            "decision_targets",
            "tracks",
            "method_hypotheses",
            "depth",
            "evidence_expectations",
            "autonomy_envelope",
            "replanning_policy",
            "success_oracles",
            "delivery_contract",
            "stop_rule",
            "revision",
            "status",
            "display_payload",
            "display_digest",
            "content_hash",
        }
        if set(value) != expected_keys:
            raise StrategyProjectionError("projection fields do not match schema")
        if value.get("schema_version") != STRATEGY_PROJECTION_SCHEMA_VERSION:
            raise StrategyProjectionError("schema_version must be 1")
        try:
            refs = {
                name: ArtifactRef.from_dict(value[name])
                for name in ("decision_frame_ref", "alignment_handoff_ref", "target_ref")
            }
            item = cls.create(
                **{
                    key: thaw_json(value[key])
                    for key in (
                        "projection_id",
                        "run_id",
                        "current_understanding",
                        "assumptions",
                        "decision_targets",
                        "tracks",
                        "method_hypotheses",
                        "depth",
                        "evidence_expectations",
                        "autonomy_envelope",
                        "replanning_policy",
                        "success_oracles",
                        "delivery_contract",
                        "stop_rule",
                        "revision",
                        "status",
                    )
                },
                **refs,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StrategyProjectionError("invalid projection fields") from error
        if value.get("display_digest") != item.display_digest or value.get("content_hash") != item.content_hash:
            raise StrategyProjectionError("projection digest mismatch")
        if value.get("display_payload") != item.display_payload:
            raise StrategyProjectionError("display_payload mismatch")
        return item
