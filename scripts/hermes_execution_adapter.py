#!/usr/bin/env python3
"""Stateless Hermes projection, HostEvent translation, and recovery planning.

The canonical coordinator owns all research state. This adapter accepts one
bounded JSON input and emits one deterministic JSON projection; it never writes
checkpoints, report manifests, evidence, readiness, or completion state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

from host_event_adapter import AdapterError as WireAdapterError
from host_event_adapter import _canonical_json_bytes
from host_event_adapter import translate as translate_wire_event


IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
PROJECTION_FIELDS = frozenset(
    {
        "run_id",
        "round_id",
        "slot_id",
        "action_id",
        "attempt_id",
        "expected_revision",
        "work_item_ref",
        "work_item",
        "lease",
    }
)
WORK_ITEM_FIELDS = frozenset(
    {
        "work_item_id",
        "objective",
        "method",
        "permission_profile",
        "expected_output",
        "success_oracle",
        "completion_evidence",
        "attempt_policy",
    }
)
LEASE_FIELDS = frozenset({"owner", "dispatch_digest", "lease_expires_at"})
ARTIFACT_REF_FIELDS = frozenset(
    {"run_id", "artifact_id", "revision", "content_hash"}
)
ATTEMPT_POLICY_FIELDS = frozenset(
    {
        "max_attempts",
        "method_switch_after",
        "backoff_seconds",
        "retryable_failures",
        "no_retry_failures",
    }
)
OBSERVATION_CONTEXT_FIELDS = frozenset(
    {
        "event_id",
        "run_id",
        "round_id",
        "slot_id",
        "action_id",
        "attempt_id",
        "causation_id",
        "correlation_id",
        "sequence",
        "expected_revision",
        "emitted_at",
    }
)
DIRECT_EVENT_KINDS = frozenset(
    {
        "delegation_dispatched",
        "kanban_run_started",
        "finding_submitted",
        "review_completed",
        "provider_failed",
        "attempt_unknown",
        "retry_selected",
        "worker_finished",
        "state_diverged",
    }
)
EVENT_TYPE_BY_KIND = {
    "delegation_dispatched": "dispatch_requested",
    "kanban_run_started": "attempt_started",
    "finding_submitted": "finding_submitted",
    "review_completed": "review_completed",
    "provider_failed": "provider_failed",
    "attempt_unknown": "attempt_unknown",
    "retry_selected": "retry_requested",
    "worker_finished": "worker_finished",
    "state_diverged": "reconciliation_detected",
}
COMPLETION_CLAIM_BY_KIND = {
    "goal_succeeded": "host_status",
    "kanban_completed": "worker_status",
    "hook_completed": "hook_success",
    "wave_completed": "completed_wave",
}
RECOVERY_FIELDS = frozenset(
    {
        "context",
        "canonical_attempt",
        "policy",
        "snapshot",
        "authority",
        "fallback_providers",
        "fallback_methods",
    }
)


class HermesAdapterError(ValueError):
    """A safe, bounded Hermes adapter failure."""


def _exact(value: Mapping[str, Any], fields: frozenset[str], label: str) -> dict[str, Any]:
    data = dict(value)
    missing = fields - set(data)
    extra = set(data) - fields
    if missing or extra:
        raise HermesAdapterError(
            f"{label} fields mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    return data


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise HermesAdapterError(f"{label} must be an object")
    return dict(value)


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise HermesAdapterError(f"{label} is invalid")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HermesAdapterError(f"{label} must be nonempty")
    return value.strip()


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HermesAdapterError(f"{label} must be an integer >= {minimum}")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise HermesAdapterError(f"{label} must be an array of nonempty strings")
    return list(value)


def _read_input(path: str) -> dict[str, Any]:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HermesAdapterError("cannot read adapter input") from exc
    return _object(value, "adapter input")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def project_task(value: Mapping[str, Any]) -> dict[str, Any]:
    data = _exact(value, PROJECTION_FIELDS, "task projection")
    canonical_refs = {
        "run_id": _identifier(data["run_id"], "run_id"),
        "round_id": _identifier(data["round_id"], "round_id"),
        "slot_id": _identifier(data["slot_id"], "slot_id"),
        "action_id": _identifier(data["action_id"], "action_id"),
        "attempt_id": _identifier(data["attempt_id"], "attempt_id"),
        "expected_revision": _integer(data["expected_revision"], "expected_revision"),
    }
    work_item_ref = _exact(
        _object(data["work_item_ref"], "work_item_ref"),
        ARTIFACT_REF_FIELDS,
        "work_item_ref",
    )
    if _identifier(work_item_ref["run_id"], "work_item_ref.run_id") != canonical_refs["run_id"]:
        raise HermesAdapterError("work_item_ref belongs to a different run")
    _identifier(work_item_ref["artifact_id"], "work_item_ref.artifact_id")
    _integer(work_item_ref["revision"], "work_item_ref.revision", minimum=1)
    if not isinstance(work_item_ref["content_hash"], str) or not DIGEST_RE.fullmatch(
        work_item_ref["content_hash"]
    ):
        raise HermesAdapterError("work_item_ref.content_hash must be lowercase SHA-256")
    work_item = _exact(_object(data["work_item"], "work_item"), WORK_ITEM_FIELDS, "work_item")
    lease = _exact(_object(data["lease"], "lease"), LEASE_FIELDS, "lease")
    work_item_id = _identifier(work_item["work_item_id"], "work_item_id")
    objective = _nonempty(work_item["objective"], "objective")
    method = _nonempty(work_item["method"], "method")
    permission_profile = _nonempty(work_item["permission_profile"], "permission_profile")
    expected_output = _nonempty(work_item["expected_output"], "expected_output")
    success_oracle = _nonempty(work_item["success_oracle"], "success_oracle")
    completion_evidence = _string_list(
        work_item["completion_evidence"], "completion_evidence"
    )
    policy = _exact(
        _object(work_item["attempt_policy"], "attempt_policy"),
        ATTEMPT_POLICY_FIELDS,
        "attempt_policy",
    )
    max_attempts = _integer(policy.get("max_attempts"), "max_attempts", minimum=1)
    if max_attempts > 3:
        raise HermesAdapterError("max_attempts must not exceed three")
    method_switch_after = _integer(
        policy.get("method_switch_after"), "method_switch_after"
    )
    if method_switch_after >= max_attempts:
        raise HermesAdapterError("method_switch_after must precede max_attempts")
    policy_backoff = policy.get("backoff_seconds")
    if not isinstance(policy_backoff, list) or len(policy_backoff) < max_attempts or not all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 0
        for item in policy_backoff
    ):
        raise HermesAdapterError("attempt_policy backoff_seconds must cover all attempts")
    _string_list(policy.get("retryable_failures"), "retryable_failures")
    _string_list(policy.get("no_retry_failures"), "no_retry_failures")
    _nonempty(lease["owner"], "lease owner")
    dispatch_digest = lease["dispatch_digest"]
    if not isinstance(dispatch_digest, str) or not DIGEST_RE.fullmatch(dispatch_digest):
        raise HermesAdapterError("dispatch_digest must be lowercase SHA-256")
    _nonempty(lease["lease_expires_at"], "lease_expires_at")

    acceptance_contract = {
        "canonical_refs": canonical_refs,
        "work_item_ref": work_item_ref,
        "work_item_id": work_item_id,
        "method": method,
        "permission_profile": permission_profile,
        "expected_output": expected_output,
        "success_oracle": success_oracle,
        "completion_evidence": completion_evidence,
        "attempt_policy": policy,
        "dispatch_digest": dispatch_digest,
        "lease_expires_at": lease["lease_expires_at"],
    }
    contract_digest = _digest(acceptance_contract)
    idempotency_key = (
        f"research-tree:{canonical_refs['run_id']}:{canonical_refs['attempt_id']}"
    )
    criteria = [
        f"Submit {expected_output} for work item {work_item_id}.",
        f"Cite required evidence: {', '.join(completion_evidence)}.",
        f"Satisfy closure oracle {success_oracle}; a worker verdict is not proof.",
        "Hermes completion is non-authoritative; canonical closure remains with the coordinator.",
    ]
    return {
        "schema_version": 1,
        "kind": "hermes-task-projection",
        "idempotency_key": idempotency_key,
        "canonical_refs": canonical_refs,
        "acceptance_contract": acceptance_contract,
        "acceptance_contract_digest": contract_digest,
        "acceptance_criteria": criteria,
        "goal": {
            "title": objective,
            "goal": True,
            "acceptance_contract_digest": contract_digest,
        },
        "kanban": {
            "title": objective,
            "body": f"Canonical work item {work_item_id}; method={method}",
            "idempotency_key": idempotency_key,
            "max_retries": max(0, max_attempts - 1),
            "goal": True,
            "acceptance_contract_digest": contract_digest,
        },
    }


def _wire_from_context(
    context: Mapping[str, Any], *, event_type: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    data = _exact(context, OBSERVATION_CONTEXT_FIELDS, "event context")
    event_input = {**data, "event_type": event_type, "payload": dict(payload)}
    try:
        return translate_wire_event("hermes", event_input)
    except WireAdapterError as exc:
        raise HermesAdapterError(str(exc)) from exc


def translate_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(value)
    kind = data.pop("kind", None)
    details = _object(data.pop("details", None), "observation details")
    if set(data) != OBSERVATION_CONTEXT_FIELDS:
        _exact(data, OBSERVATION_CONTEXT_FIELDS, "observation context")
    if kind in DIRECT_EVENT_KINDS:
        return _wire_from_context(
            data, event_type=EVENT_TYPE_BY_KIND[str(kind)], payload=details
        )
    claim_kind = COMPLETION_CLAIM_BY_KIND.get(str(kind))
    if claim_kind is None:
        raise HermesAdapterError("unsupported Hermes observation kind")
    source_ref = _nonempty(details.get("source_ref"), "source_ref")
    local_status = _nonempty(details.get("local_status"), "local_status")
    if set(details) != {"source_ref", "local_status"}:
        raise HermesAdapterError("completion observation contains unsupported fields")
    return _wire_from_context(
        data,
        event_type="completion_claimed",
        payload={
            "claim_kind": claim_kind,
            "claimed_state": "completed",
            "source_ref": source_ref,
            "local_status": local_status,
        },
    )


def _derived_event_context(
    base: Mapping[str, Any], *, suffix: str, revision_offset: int, sequence_offset: int
) -> dict[str, Any]:
    context = _exact(base, OBSERVATION_CONTEXT_FIELDS, "recovery context")
    event_id = _identifier(context["event_id"], "event_id")
    derived_id = event_id if not suffix else f"{event_id}-{suffix}"
    if len(derived_id) > 64 or not IDENTIFIER_RE.fullmatch(derived_id):
        derived_id = f"recovery-{_digest([event_id, suffix])[:48]}"
    return {
        **context,
        "event_id": derived_id,
        "expected_revision": _integer(
            context["expected_revision"], "expected_revision"
        )
        + revision_offset,
        "sequence": _integer(context["sequence"], "sequence", minimum=1)
        + sequence_offset,
    }


def _allowed_fallback_provider(
    values: Any, allowed: set[str], current: str
) -> dict[str, str] | None:
    if not isinstance(values, list):
        raise HermesAdapterError("fallback_providers must be an array")
    for raw in values:
        candidate = _object(raw, "fallback provider")
        if set(candidate) != {"provider", "model"}:
            raise HermesAdapterError("fallback provider fields mismatch")
        provider = _nonempty(candidate["provider"], "fallback provider")
        model = _nonempty(candidate["model"], "fallback model")
        if provider != current and provider in allowed:
            return {"provider": provider, "model": model}
    return None


def _allowed_fallback_method(values: Any, allowed: set[str], current: str) -> str | None:
    methods = _string_list(values, "fallback_methods")
    return next((method for method in methods if method != current and method in allowed), None)


def plan_recovery(value: Mapping[str, Any]) -> dict[str, Any]:
    data = _exact(value, RECOVERY_FIELDS, "recovery plan")
    context = _object(data["context"], "context")
    attempt = _object(data["canonical_attempt"], "canonical_attempt")
    policy = _object(data["policy"], "policy")
    snapshot = _object(data["snapshot"], "snapshot")
    authority = _object(data["authority"], "authority")

    attempt_id = _identifier(attempt.get("attempt_id"), "attempt_id")
    work_item_id = _identifier(attempt.get("work_item_id"), "work_item_id")
    if attempt_id != context.get("attempt_id"):
        raise HermesAdapterError("recovery context does not bind the canonical attempt")
    retry_ordinal = _integer(attempt.get("retry_ordinal"), "retry_ordinal")
    current_method = _nonempty(attempt.get("method"), "attempt method")
    current_provider = _nonempty(attempt.get("provider"), "attempt provider")
    current_model = _nonempty(attempt.get("model"), "attempt model")
    current_status = _nonempty(attempt.get("status"), "attempt status")
    if current_status not in {"retryable", "unknown"}:
        raise HermesAdapterError("only retryable or unknown canonical attempts can recover")
    snapshot_status = _nonempty(snapshot.get("status"), "snapshot status")
    failure_category = _nonempty(
        snapshot.get("failure_category", "unknown"), "failure_category"
    )
    max_attempts = _integer(policy.get("max_attempts"), "max_attempts", minimum=1)
    method_switch_after = _integer(
        policy.get("method_switch_after"), "method_switch_after"
    )
    retryable = set(_string_list(policy.get("retryable_failures"), "retryable_failures"))
    no_retry = set(_string_list(policy.get("no_retry_failures"), "no_retry_failures"))
    backoff = policy.get("backoff_seconds")
    if not isinstance(backoff, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 0
        for item in backoff
    ):
        raise HermesAdapterError("backoff_seconds must be nonnegative integers")
    allowed_providers = set(
        _string_list(authority.get("allowed_providers"), "allowed_providers")
    )
    allowed_methods = set(
        _string_list(authority.get("allowed_methods"), "allowed_methods")
    )

    events: list[dict[str, Any]] = []
    revision_offset = 0
    sequence_offset = 0
    if snapshot_status in {"running", "stale", "missing", "unknown"}:
        observed = {
            key: snapshot[key]
            for key in ("status", "task_id", "run_id")
            if key in snapshot
        }
        unknown_context = _derived_event_context(
            context,
            suffix="unknown",
            revision_offset=revision_offset,
            sequence_offset=sequence_offset,
        )
        events.append(
            _wire_from_context(
                unknown_context,
                event_type="attempt_unknown",
                payload={
                    "reconciliation_reason": f"hermes_restart_{snapshot_status}",
                    "last_heartbeat": snapshot.get("last_heartbeat"),
                    "observed_host_state": observed,
                },
            )
        )
        revision_offset += 1
        sequence_offset += 1

    if snapshot_status in {"completed", "submitted", "success"}:
        return {
            "schema_version": 1,
            "decision": "awaiting_evidence_review",
            "reason": "host_output_requires_finding_pack_and_independent_review",
            "events": events,
            "next_attempt": None,
        }

    next_ordinal = retry_ordinal + 1
    if failure_category in no_retry:
        return {
            "schema_version": 1,
            "decision": "terminal_failure",
            "reason": "failure_category_is_not_retryable",
            "events": events,
            "next_attempt": None,
        }
    if failure_category not in retryable or next_ordinal >= max_attempts:
        return {
            "schema_version": 1,
            "decision": "retry_exhausted",
            "reason": "retry_policy_exhausted_or_unclassified",
            "events": events,
            "next_attempt": None,
        }

    provider_target = _allowed_fallback_provider(
        data["fallback_providers"], allowed_providers, current_provider
    )
    method_target = _allowed_fallback_method(
        data["fallback_methods"], allowed_methods, current_method
    )
    decision: str
    target_provider = current_provider
    target_model = current_model
    target_method = current_method
    if provider_target is not None:
        decision = "alternate_provider"
        target_provider = provider_target["provider"]
        target_model = provider_target["model"]
    elif next_ordinal <= method_switch_after and current_provider in allowed_providers:
        decision = "retry_same_provider"
    elif method_target is not None:
        decision = "method_switch"
        target_method = method_target
    else:
        return {
            "schema_version": 1,
            "decision": "authority_blocked",
            "reason": "no_policy_candidate_is_inside_confirmed_authority",
            "events": events,
            "next_attempt": None,
        }

    next_attempt_id = _identifier(
        f"{work_item_id}-retry-{next_ordinal}", "next attempt_id"
    )
    dispatch_payload = {
        "predecessor_attempt": attempt_id,
        "attempt_id": next_attempt_id,
        "retry_ordinal": next_ordinal,
        "method": target_method,
        "provider": target_provider,
        "model": target_model,
    }
    dispatch_digest = _digest(dispatch_payload)
    retry_context = _derived_event_context(
        context,
        suffix="retry" if events else "",
        revision_offset=revision_offset,
        sequence_offset=sequence_offset,
    )
    events.append(
        _wire_from_context(
            retry_context,
            event_type="retry_requested",
            payload={
                "predecessor_attempt": attempt_id,
                "method_provider_change": {
                    "decision": decision,
                    "from": {
                        "method": current_method,
                        "provider": current_provider,
                        "model": current_model,
                    },
                    "to": {
                        "method": target_method,
                        "provider": target_provider,
                        "model": target_model,
                    },
                    "dispatch_digest": dispatch_digest,
                },
                "retry_policy": {
                    "max_attempts": max_attempts,
                    "method_switch_after": method_switch_after,
                    "retry_ordinal": next_ordinal,
                    "backoff_seconds": backoff[next_ordinal]
                    if next_ordinal < len(backoff)
                    else None,
                },
            },
        )
    )
    return {
        "schema_version": 1,
        "decision": decision,
        "reason": "policy_candidate_selected_within_confirmed_authority",
        "events": events,
        "next_attempt": {
            **dispatch_payload,
            "dispatch_digest": dispatch_digest,
            "predecessor_status": current_status,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("project-task", "translate-observation", "plan-recovery"):
        command = commands.add_parser(name)
        command.add_argument("--input", required=True, help="JSON path, or - for stdin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        value = _read_input(arguments.input)
        if arguments.command == "project-task":
            result = project_task(value)
        elif arguments.command == "translate-observation":
            result = translate_observation(value)
        else:
            result = plan_recovery(value)
    except (HermesAdapterError, WireAdapterError) as exc:
        print(
            json.dumps(
                {"code": "invalid_hermes_observation", "safe_message": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    sys.stdout.buffer.write(_canonical_json_bytes(result) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
