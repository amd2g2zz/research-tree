"""Strict, dependency-free alpha2 wire and entity contracts.

The runtime deliberately keeps validation here instead of teaching each host
adapter a slightly different JSON dialect.  The canonical representation is
UTF-8 JSON without a BOM and the digest excludes only ``content_hash``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Mapping, Sequence


IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_CODE_RE = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
SAFE_LOG_REF_RE = re.compile(
    r"^(?:log:[A-Za-z0-9._:-]{1,192}|sha256:[0-9a-f]{64})$"
)
HOSTS = frozenset({"codex", "claude-code", "hermes", "source", "evaluator"})
ACTOR_KINDS = frozenset({"coordinator", "worker", "human", "oracle", "adapter", "migration"})
EVENT_TYPES = frozenset(
    {
        "dispatch_requested", "attempt_started", "finding_submitted", "review_completed",
        "provider_failed", "attempt_unknown", "retry_requested", "worker_finished",
        "completion_claimed", "acceptance_recorded", "reconciliation_detected",
    }
)
EVENT_PAYLOAD_FIELDS: dict[str, frozenset[str]] = {
    "dispatch_requested": frozenset({"work_item_id", "permission_profile", "dispatch_digest", "lease_policy"}),
    "attempt_started": frozenset({"worker_id", "lease_expires_at", "tool_capability_digest", "started_at"}),
    "finding_submitted": frozenset({"finding_pack_digest", "evidence_refs", "submission_status", "output_digest"}),
    "review_completed": frozenset({"reviewer_id", "accepted_refs", "field_diagnostics", "review_digest"}),
    "provider_failed": frozenset({"provider", "model", "retry_category", "opaque_code", "gateway_log_ref"}),
    "attempt_unknown": frozenset({"reconciliation_reason", "last_heartbeat", "observed_host_state"}),
    "retry_requested": frozenset({"predecessor_attempt", "method_provider_change", "retry_policy"}),
    "worker_finished": frozenset({"terminal_status", "artifact_refs"}),
    "completion_claimed": frozenset(
        {"claim_kind", "claimed_state", "source_ref", "local_status"}
    ),
    "acceptance_recorded": frozenset({"delivery_acceptance_ref", "displayed_digest"}),
    "reconciliation_detected": frozenset({"host_observation", "canonical_observation", "conflict_class", "next_action"}),
}
FEEDBACK_KINDS = frozenset(
    {"correction", "priority_change", "scope_change", "authority_change", "success_change",
     "depth_request", "rejection", "approval"}
)
FEEDBACK_IMPACT_CLASSES = frozenset(
    {"none", "alignment", "strategy", "attempt", "delivery", "terminal"}
)
TASK_IDENTITY_DISPOSITIONS = frozenset(
    {"unchanged", "rederived", "superseded", "unknown"}
)
ARTIFACT_REF_FIELDS = frozenset(
    {"run_id", "artifact_id", "revision", "content_hash"}
)
DECISION_SLOT_FIELDS = frozenset(
    {
        "slot_id",
        "priority",
        "question",
        "decision_consequence",
        "options",
        "required_evidence_classes",
        "required_oracles",
        "fallback",
        "reversal_condition",
        "status",
        "lineage_refs",
    }
)


class ContractError(ValueError):
    """Stable validation error at a canonical contract boundary."""

    def __init__(self, message: str, *, code: str = "invalid_contract") -> None:
        super().__init__(message)
        self.code = code


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(child) for key, child in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError("JSON numbers must be finite", code="invalid_payload")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            _normalize(value), ensure_ascii=False, allow_nan=False,
            separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("payload is not canonical JSON", code="invalid_payload") from exc


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ContractError(f"{label} is invalid", code="invalid_identifier")
    return value


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{label} must be an ISO-8601 timestamp", code="invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{label} must be an ISO-8601 timestamp", code="invalid_timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{label} must include a timezone", code="invalid_timestamp")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractError(f"{label} must be UTC", code="invalid_timestamp")
    return value


def _required_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object", code="invalid_contract")
    return dict(value)


def validate_host_event_payload(event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the required semantic fields for one host event type."""

    if event_type not in EVENT_PAYLOAD_FIELDS:
        raise ContractError("unsupported host event type", code="unsupported_event_type")
    normalized = _required_object(payload, "host event payload")
    missing = EVENT_PAYLOAD_FIELDS[event_type] - set(normalized)
    if missing:
        raise ContractError(
            f"{event_type} payload is incomplete; missing={sorted(missing)}",
            code="incomplete_event_payload",
        )
    if event_type == "provider_failed":
        forbidden = {
            "raw_error", "raw_details", "traceback", "stack_trace", "response_body",
            "provider_message", "exception", "secret", "token",
        } & set(normalized)
        if forbidden:
            raise ContractError(
                "provider_failed payload contains raw diagnostics",
                code="raw_provider_details",
            )
        if set(normalized) != EVENT_PAYLOAD_FIELDS[event_type]:
            raise ContractError(
                "provider_failed payload fields mismatch",
                code="raw_provider_details",
            )
        for field in ("provider", "model", "retry_category"):
            if not isinstance(normalized[field], str) or not normalized[field].strip():
                raise ContractError(
                    f"provider_failed {field} must be a non-empty string",
                    code="invalid_provider_metadata",
                )
        opaque_code = normalized["opaque_code"]
        if not isinstance(opaque_code, str) or not OPAQUE_CODE_RE.fullmatch(opaque_code):
            raise ContractError(
                "provider_failed opaque_code is invalid",
                code="invalid_provider_metadata",
            )
        gateway_ref = normalized["gateway_log_ref"]
        if gateway_ref is not None and (
            not isinstance(gateway_ref, str) or not SAFE_LOG_REF_RE.fullmatch(gateway_ref)
        ):
            raise ContractError(
                "provider_failed gateway_log_ref is invalid",
                code="invalid_provider_metadata",
            )
    if event_type == "completion_claimed":
        if normalized["claim_kind"] not in {
            "host_status",
            "worker_status",
            "hook_success",
            "report_file",
            "empty_frontier",
            "completed_wave",
        }:
            raise ContractError(
                "completion_claimed claim_kind is invalid",
                code="invalid_completion_claim",
            )
        if normalized["claimed_state"] != "completed":
            raise ContractError(
                "completion_claimed may only report completed",
                code="invalid_completion_claim",
            )
        for field in ("source_ref", "local_status"):
            if not isinstance(normalized[field], str) or not normalized[field].strip():
                raise ContractError(
                    f"completion_claimed {field} is invalid",
                    code="invalid_completion_claim",
                )
    return normalized


def _exact(data: Mapping[str, Any], required: set[str], label: str) -> None:
    missing = required - set(data)
    extra = set(data) - required
    if missing or extra:
        raise ContractError(
            f"{label} fields mismatch; missing={sorted(missing)}, extra={sorted(extra)}",
            code="invalid_contract",
        )


@dataclass(frozen=True, slots=True)
class EntityEnvelope:
    schema_version: int
    kind: str
    id: str
    run_id: str
    revision: int
    created_at: str
    actor: Mapping[str, str]
    status: str
    payload: Mapping[str, Any]
    parent_refs: tuple[Mapping[str, Any], ...]
    content_hash: str

    @classmethod
    def create(
        cls, *, kind: str, entity_id: str, run_id: str, actor: Mapping[str, str],
        status: str, payload: Mapping[str, Any], parent_refs: Sequence[Mapping[str, Any]] = (),
        revision: int = 1, created_at: str | None = None,
    ) -> "EntityEnvelope":
        stamp = created_at or datetime.now(timezone.utc).isoformat()
        data = {
            "schema_version": 1, "kind": _identifier(kind, "kind"),
            "id": _identifier(entity_id, "id"), "run_id": _identifier(run_id, "run_id"),
            "revision": revision, "created_at": _timestamp(stamp, "created_at"),
            "actor": dict(actor), "status": str(status), "payload": dict(payload),
            "parent_refs": [dict(ref) for ref in parent_refs],
        }
        content_hash = hashlib.sha256(canonical_json_bytes(data)).hexdigest()
        return cls(content_hash=content_hash, **data)

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "kind": self.kind, "id": self.id,
            "run_id": self.run_id, "revision": self.revision, "created_at": self.created_at,
            "actor": dict(self.actor), "status": self.status, "payload": dict(self.payload),
            "parent_refs": [dict(ref) for ref in self.parent_refs],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._body(), "content_hash": self.content_hash}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EntityEnvelope":
        data = _required_object(value, "entity envelope")
        required = {"schema_version", "kind", "id", "run_id", "revision", "created_at", "actor", "status", "payload", "parent_refs", "content_hash"}
        _exact(data, required, "entity envelope")
        if data["schema_version"] != 1:
            raise ContractError("unsupported schema_version", code="unsupported_schema_version")
        entity = cls.create(
            kind=data["kind"], entity_id=data["id"], run_id=data["run_id"], actor=data["actor"],
            status=data["status"], payload=data["payload"], parent_refs=data["parent_refs"],
            revision=data["revision"], created_at=data["created_at"],
        )
        if data["content_hash"] != entity.content_hash:
            raise ContractError("content_hash does not match canonical body", code="digest_mismatch")
        return entity


@dataclass(frozen=True, slots=True)
class HostEvent:
    protocol_version: int
    event_id: str
    event_type: str
    run_id: str
    round_id: str
    slot_id: str | None
    action_id: str | None
    attempt_id: str | None
    host: str
    causation_id: str | None
    correlation_id: str | None
    sequence: int
    expected_revision: int
    payload_digest: str
    emitted_at: str
    payload: Mapping[str, Any]

    @classmethod
    def create(
        cls, *, event_id: str, event_type: str, run_id: str, round_id: str, host: str,
        expected_revision: int, payload: Mapping[str, Any], slot_id: str | None = None,
        action_id: str | None = None, attempt_id: str | None = None,
        causation_id: str | None = None, correlation_id: str | None = None,
        sequence: int = 1, emitted_at: str | None = None,
    ) -> "HostEvent":
        if event_type not in EVENT_TYPES:
            raise ContractError("unsupported host event type", code="unsupported_event_type")
        if host not in {"codex", "claude-code", "hermes"}:
            raise ContractError("unsupported host", code="invalid_host")
        normalized_payload = validate_host_event_payload(event_type, payload)
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ContractError("host event sequence must be a positive integer", code="invalid_event_order")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise ContractError("host event expected_revision must be nonnegative", code="invalid_event_order")
        normalized_optional: dict[str, str | None] = {}
        for label, value in (
            ("slot_id", slot_id),
            ("action_id", action_id),
            ("attempt_id", attempt_id),
            ("causation_id", causation_id),
            ("correlation_id", correlation_id),
        ):
            normalized_optional[label] = None if value is None else _identifier(value, label)
        digest = hashlib.sha256(canonical_json_bytes(normalized_payload)).hexdigest()
        stamp = emitted_at or datetime.now(timezone.utc).isoformat()
        return cls(1, _identifier(event_id, "event_id"), event_type,
                   _identifier(run_id, "run_id"), _identifier(round_id, "round_id"),
                   normalized_optional["slot_id"], normalized_optional["action_id"],
                   normalized_optional["attempt_id"], host,
                   normalized_optional["causation_id"], normalized_optional["correlation_id"],
                   int(sequence), int(expected_revision), digest, _timestamp(stamp, "emitted_at"), normalized_payload)

    def to_dict(self) -> dict[str, Any]:
        return {"protocol_version": self.protocol_version, "event_id": self.event_id,
                "event_type": self.event_type, "run_id": self.run_id, "round_id": self.round_id,
                "slot_id": self.slot_id, "action_id": self.action_id, "attempt_id": self.attempt_id,
                "host": self.host, "causation_id": self.causation_id, "correlation_id": self.correlation_id,
                "sequence": self.sequence, "expected_revision": self.expected_revision,
                "payload_digest": self.payload_digest, "emitted_at": self.emitted_at,
                "payload": dict(self.payload)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HostEvent":
        data = _required_object(value, "host event")
        required = {"protocol_version", "event_id", "event_type", "run_id", "round_id", "slot_id", "action_id", "attempt_id", "host", "causation_id", "correlation_id", "sequence", "expected_revision", "payload_digest", "emitted_at", "payload"}
        _exact(data, required, "host event")
        if data["protocol_version"] != 1:
            raise ContractError("unsupported protocol_version", code="unsupported_protocol_version")
        event = cls.create(event_id=data["event_id"], event_type=data["event_type"], run_id=data["run_id"], round_id=data["round_id"], host=data["host"], expected_revision=data["expected_revision"], payload=data["payload"], slot_id=data["slot_id"], action_id=data["action_id"], attempt_id=data["attempt_id"], causation_id=data["causation_id"], correlation_id=data["correlation_id"], sequence=data["sequence"], emitted_at=data["emitted_at"])
        if event.payload_digest != data["payload_digest"]:
            raise ContractError("payload_digest does not match payload", code="digest_mismatch")
        return event


def validate_feedback_event(value: Mapping[str, Any]) -> dict[str, Any]:
    data = _required_object(value, "feedback event")
    required = {"feedback_id", "run_id", "actor", "kind", "message", "target_refs", "materiality", "created_at"}
    allowed_extra = {"successor_task_identity", "expected_revision", "contradicted_refs", "affected_fields", "invalidated_refs", "successor_refs", "impact_class", "task_identity_disposition"}
    missing = required - set(data)
    extra = set(data) - required - allowed_extra
    if missing or extra:
        raise ContractError(f"feedback fields mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    _identifier(data["feedback_id"], "feedback_id")
    _identifier(data["run_id"], "run_id")
    if data["kind"] not in FEEDBACK_KINDS or data["materiality"] not in {"informational", "material", "terminal"}:
        raise ContractError("unsupported feedback kind or materiality")
    if not isinstance(data["actor"], str) or not data["actor"].strip():
        raise ContractError("feedback actor must be nonempty")
    if not isinstance(data["message"], str) or not data["message"].strip():
        raise ContractError("feedback message must be nonempty")
    if not isinstance(data["target_refs"], list) or not all(isinstance(ref, str) for ref in data["target_refs"]):
        raise ContractError("feedback target_refs must be a string list")
    _timestamp(data["created_at"], "created_at")
    for field in (
        "contradicted_refs",
        "affected_fields",
        "invalidated_refs",
        "successor_refs",
    ):
        if field in data and (
            not isinstance(data[field], list)
            or not all(isinstance(item, str) and item.strip() for item in data[field])
        ):
            raise ContractError(f"feedback {field} must be a nonempty string list")
    if "impact_class" in data and data["impact_class"] not in FEEDBACK_IMPACT_CLASSES:
        raise ContractError("unsupported feedback impact_class")
    if (
        "task_identity_disposition" in data
        and data["task_identity_disposition"] not in TASK_IDENTITY_DISPOSITIONS
    ):
        raise ContractError("unsupported feedback task_identity_disposition")
    if "expected_revision" in data and (
        isinstance(data["expected_revision"], bool)
        or not isinstance(data["expected_revision"], int)
        or data["expected_revision"] < 0
    ):
        raise ContractError("feedback expected_revision must be a nonnegative integer")
    if "successor_task_identity" in data and not isinstance(
        data["successor_task_identity"], Mapping
    ):
        raise ContractError("feedback successor_task_identity must be an object")
    normalized = _normalize(data)
    normalized.setdefault("contradicted_refs", list(normalized.get("target_refs", [])))
    normalized.setdefault("affected_fields", [])
    normalized.setdefault("invalidated_refs", [])
    normalized.setdefault("successor_refs", [])
    normalized.setdefault(
        "impact_class",
        {
            "informational": "none",
            "material": "alignment",
            "terminal": "terminal",
        }[normalized["materiality"]],
    )
    normalized.setdefault("task_identity_disposition", "rederived" if "successor_task_identity" in normalized else "unchanged")
    if (
        normalized["task_identity_disposition"] == "rederived"
        and "successor_task_identity" not in normalized
    ):
        raise ContractError(
            "rederived task identity requires successor_task_identity"
        )
    return normalized


def validate_exact_artifact_ref(
    value: Mapping[str, Any],
    *,
    label: str = "artifact reference",
    run_id: str | None = None,
) -> dict[str, Any]:
    """Validate one immutable artifact revision reference."""

    data = _required_object(value, label)
    _exact(data, set(ARTIFACT_REF_FIELDS), label)
    _identifier(data["run_id"], f"{label} run_id")
    _identifier(data["artifact_id"], f"{label} artifact_id")
    if run_id is not None and data["run_id"] != run_id:
        raise ContractError(f"{label} belongs to another run", code="artifact_scope_mismatch")
    if (
        isinstance(data["revision"], bool)
        or not isinstance(data["revision"], int)
        or data["revision"] < 1
    ):
        raise ContractError(f"{label} revision is invalid", code="invalid_artifact_ref")
    if not isinstance(data["content_hash"], str) or not HASH_RE.fullmatch(
        data["content_hash"]
    ):
        raise ContractError(f"{label} content_hash is invalid", code="invalid_artifact_ref")
    return _normalize(data)


def validate_alignment_handoff(
    value: Mapping[str, Any], *, run_id: str | None = None
) -> dict[str, Any]:
    """Validate the semantic payload that grants autonomous handoff."""

    data = _required_object(value, "alignment handoff")
    required = {
        "run_id",
        "alignment_revision",
        "alignment_digest",
        "strategy_digest",
        "objective",
        "execution_context",
        "alignment_graph_ref",
        "working_brief_ref",
        "intent_model_ref",
        "confirmation",
    }
    _exact(data, required, "alignment handoff")
    _identifier(data["run_id"], "alignment handoff run_id")
    if run_id is not None and data["run_id"] != run_id:
        raise ContractError(
            "alignment handoff belongs to another run", code="artifact_scope_mismatch"
        )
    if (
        isinstance(data["alignment_revision"], bool)
        or not isinstance(data["alignment_revision"], int)
        or data["alignment_revision"] < 1
    ):
        raise ContractError(
            "alignment handoff revision is invalid", code="handoff_confirmation_invalid"
        )
    for field in ("alignment_digest", "strategy_digest"):
        if not isinstance(data[field], str) or not HASH_RE.fullmatch(data[field]):
            raise ContractError(
                f"alignment handoff {field} is invalid",
                code="handoff_confirmation_invalid",
            )
    if not isinstance(data["objective"], str) or not data["objective"].strip():
        raise ContractError(
            "alignment handoff objective is required", code="handoff_confirmation_invalid"
        )
    if not isinstance(data["execution_context"], Mapping):
        raise ContractError(
            "alignment handoff execution_context must be an object",
            code="handoff_confirmation_invalid",
        )
    for field in ("alignment_graph_ref", "working_brief_ref", "intent_model_ref"):
        data[field] = validate_exact_artifact_ref(
            data[field], label=f"alignment handoff {field}", run_id=data["run_id"]
        )
    confirmation = _required_object(data["confirmation"], "handoff confirmation")
    _exact(
        confirmation,
        {"actor_id", "response_digest", "displayed_strategy_digest", "confirmed_at"},
        "handoff confirmation",
    )
    if not isinstance(confirmation["actor_id"], str) or not confirmation["actor_id"].strip():
        raise ContractError(
            "handoff confirmation actor_id is required",
            code="handoff_confirmation_invalid",
        )
    for field in ("response_digest", "displayed_strategy_digest"):
        if not isinstance(confirmation[field], str) or not HASH_RE.fullmatch(
            confirmation[field]
        ):
            raise ContractError(
                f"handoff confirmation {field} is invalid",
                code="handoff_confirmation_invalid",
            )
    _timestamp(confirmation["confirmed_at"], "handoff confirmation confirmed_at")
    if confirmation["displayed_strategy_digest"] != data["strategy_digest"]:
        raise ContractError(
            "handoff confirmation does not bind the displayed strategy digest",
            code="handoff_confirmation_invalid",
        )
    data["confirmation"] = confirmation
    return _normalize(data)


def validate_blueprint_target(
    value: Mapping[str, Any], *, run_id: str | None = None
) -> dict[str, Any]:
    """Validate the initial alpha2 Blueprint Target payload."""

    data = _required_object(value, "blueprint target")
    required = {
        "target_id",
        "run_id",
        "working_brief_ref",
        "intent_model_ref",
        "alignment_handoff_ref",
        "slots",
        "change",
    }
    _exact(data, required, "blueprint target")
    _identifier(data["target_id"], "blueprint target_id")
    _identifier(data["run_id"], "blueprint run_id")
    if run_id is not None and data["run_id"] != run_id:
        raise ContractError(
            "blueprint target belongs to another run", code="artifact_scope_mismatch"
        )
    for field in ("working_brief_ref", "intent_model_ref", "alignment_handoff_ref"):
        data[field] = validate_exact_artifact_ref(
            data[field], label=f"blueprint target {field}", run_id=data["run_id"]
        )
    slots = data["slots"]
    if not isinstance(slots, list) or not slots:
        raise ContractError("blueprint target requires Decision Slots", code="blueprint_slots_invalid")
    seen: set[str] = set()
    normalized_slots: list[dict[str, Any]] = []
    for index, value_slot in enumerate(slots):
        slot = _required_object(value_slot, f"blueprint slot {index}")
        _exact(slot, set(DECISION_SLOT_FIELDS), f"blueprint slot {index}")
        slot_id = _identifier(slot["slot_id"], f"blueprint slot {index} id")
        if slot_id in seen:
            raise ContractError("blueprint Slot ids must be unique", code="blueprint_slots_invalid")
        seen.add(slot_id)
        if slot["priority"] not in {"P0", "P1", "P2"}:
            raise ContractError("blueprint Slot priority is invalid", code="blueprint_slots_invalid")
        if slot["status"] not in {
            "open", "researching", "contested", "conditionally_closed",
            "closed", "blocked", "superseded",
        }:
            raise ContractError("blueprint Slot status is invalid", code="blueprint_slots_invalid")
        for field in ("question", "decision_consequence", "fallback", "reversal_condition"):
            if not isinstance(slot[field], str) or not slot[field].strip():
                raise ContractError(
                    f"blueprint Slot {field} is required", code="blueprint_slots_invalid"
                )
        for field in (
            "options", "required_evidence_classes", "required_oracles", "lineage_refs"
        ):
            if (
                not isinstance(slot[field], list)
                or not all(isinstance(item, str) and item.strip() for item in slot[field])
            ):
                raise ContractError(
                    f"blueprint Slot {field} is invalid", code="blueprint_slots_invalid"
                )
        if not slot["options"] or not slot["required_oracles"] or not slot["lineage_refs"]:
            raise ContractError(
                "blueprint Slot options, required_oracles, and lineage_refs are required",
                code="blueprint_slots_invalid",
            )
        normalized_slots.append(_normalize(slot))
    change = _required_object(data["change"], "blueprint change")
    _exact(change, {"kind", "reason", "predecessor_ref"}, "blueprint change")
    if change["kind"] not in {"initial", "add", "split", "merge", "remove", "reprioritize"}:
        raise ContractError("blueprint change kind is invalid", code="blueprint_change_invalid")
    if not isinstance(change["reason"], str) or not change["reason"].strip():
        raise ContractError("blueprint change reason is required", code="blueprint_change_invalid")
    if change["predecessor_ref"] is not None:
        change["predecessor_ref"] = validate_exact_artifact_ref(
            change["predecessor_ref"], label="blueprint predecessor_ref", run_id=data["run_id"]
        )
    if change["kind"] == "initial" and change["predecessor_ref"] is not None:
        raise ContractError(
            "initial blueprint cannot have a predecessor", code="blueprint_change_invalid"
        )
    data["slots"] = normalized_slots
    data["change"] = change
    return _normalize(data)
