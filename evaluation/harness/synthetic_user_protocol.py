"""Boundary contracts for evaluator-owned synthetic user simulation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re


__all__ = [
    "SyntheticUserPolicy",
    "SyntheticUserProtocolError",
    "SyntheticUserTurn",
    "assert_no_private_material",
    "blinded_review_bundle",
    "build_simulator_request",
    "validate_runner_episode_input",
    "validate_simulator_turn",
    "validate_synthetic_user_policy",
]


_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PRIVATE_FIELD_NAMES = frozenset(
    {
        "answer_key",
        "evaluator_prompt",
        "expected_answer",
        "expected_patch",
        "hidden_oracle",
        "oracle_body",
        "persona_prompt",
        "private_prompt",
        "reference_answer",
        "reference_patch",
        "scoring_rubric",
        "system_prompt",
    }
)
_RUNNER_REQUIRED_FIELDS = frozenset({"episode_id", "initial_user_message", "model", "source_proxy_url"})
_RUNNER_IDENTITY_FIELDS = frozenset({"arm", "condition", "host", "persona_id", "run_label"})
_TURN_DISPOSITIONS = frozenset({"abandon", "clarify", "complete", "continue", "correct"})
_BLINDED_ID_PATTERN = re.compile(r"blind-[a-z0-9]{2,120}\Z")
_BLINDING_CUE_PATTERN = re.compile(
    r"\b(?:alpha[ _-]?[12]|baseline|claude(?:[ _-]?code)?|hermes(?:[ _-]?agent)?|host|condition|arm)\b",
    re.IGNORECASE,
)


class SyntheticUserProtocolError(ValueError):
    """Raised when a synthetic-user transport violates its isolation contract."""


@dataclass(frozen=True, slots=True)
class SyntheticUserPolicy:
    """Public commitment for a hidden synthetic-user proxy configuration."""

    evidence_kind: str
    human_experience_status: str
    persona_set_digest: str
    prompt_family_digest: str
    heldout_task_set_digest: str
    assignment_digest: str
    turn_limit: int


@dataclass(frozen=True, slots=True)
class SyntheticUserTurn:
    """A bounded simulator response that can be passed to the host adapter."""

    message: str
    disposition: str


def assert_no_private_material(value: object, *, known_private_markers: Sequence[str] = ()) -> None:
    """Reject public or runner-visible data carrying hidden prompts or answers."""

    marker_values = tuple(_text(marker, "private marker", maximum=512).casefold() for marker in known_private_markers)
    for key, child in _walk_values(value):
        if key.lower() in _PRIVATE_FIELD_NAMES:
            raise SyntheticUserProtocolError("private evaluator material is not permitted in this boundary")
        if isinstance(child, str) and any(marker in child.casefold() for marker in marker_values):
            raise SyntheticUserProtocolError("private evaluator material is not permitted in this boundary")


def validate_synthetic_user_policy(raw: Mapping[str, object]) -> SyntheticUserPolicy:
    """Validate the public policy without accepting the persona prompt itself."""

    policy = _mapping(raw, "synthetic user policy")
    assert_no_private_material(policy)
    required = {
        "enabled",
        "evidence_kind",
        "human_experience_status",
        "persona_set_digest",
        "prompt_family_digest",
        "heldout_task_set_digest",
        "assignment_digest",
        "persona_prompt_location",
        "persona_prompt_task_binding",
        "holdout_policy",
        "assignment_visibility",
        "simulator_service",
        "simulator_model",
        "review_blinding",
        "scoring_separation",
        "turn_limit",
    }
    _require_exact_fields(policy, required, "synthetic user policy")
    if policy["enabled"] is not True:
        raise SyntheticUserProtocolError("synthetic user policy must be enabled for this benchmark")
    if policy["evidence_kind"] != "synthetic-user-proxy":
        raise SyntheticUserProtocolError("synthetic user policy must use the synthetic-user-proxy evidence label")
    if policy["human_experience_status"] != "unavailable":
        raise SyntheticUserProtocolError("synthetic-user proxy cannot claim human evidence")
    if policy["persona_prompt_location"] != "evaluator-owned":
        raise SyntheticUserProtocolError("persona prompts must remain evaluator-owned")
    if policy["persona_prompt_task_binding"] != "task-agnostic":
        raise SyntheticUserProtocolError("persona prompts must remain task-agnostic")
    if policy["holdout_policy"] != "tasks-held-out-from-harness-development":
        raise SyntheticUserProtocolError("synthetic-user tasks must be held out from harness development")
    if policy["assignment_visibility"] != "evaluator-only-until-unblind":
        raise SyntheticUserProtocolError("persona assignment must remain evaluator-only until unblinding")
    if policy["simulator_service"] != "separate-network-service":
        raise SyntheticUserProtocolError("simulator must run behind a separate network service")
    if policy["simulator_model"] != "deepseek-v4-flash":
        raise SyntheticUserProtocolError("simulator must use the frozen base model")
    if policy["review_blinding"] != "arm-and-host-hidden":
        raise SyntheticUserProtocolError("reviews must hide host and arm identity")
    if policy["scoring_separation"] != "synthetic-user-cannot-score":
        raise SyntheticUserProtocolError("synthetic-user output cannot provide the quality score")
    return SyntheticUserPolicy(
        evidence_kind="synthetic-user-proxy",
        human_experience_status="unavailable",
        persona_set_digest=_digest(policy["persona_set_digest"], "persona_set_digest"),
        prompt_family_digest=_digest(policy["prompt_family_digest"], "prompt_family_digest"),
        heldout_task_set_digest=_digest(policy["heldout_task_set_digest"], "heldout_task_set_digest"),
        assignment_digest=_digest(policy["assignment_digest"], "assignment_digest"),
        turn_limit=_positive_int(policy["turn_limit"], "turn_limit", maximum=50),
    )


def validate_runner_episode_input(raw: Mapping[str, object]) -> dict[str, str]:
    """Accept only the minimal information that a tested runner may receive."""

    payload = _mapping(raw, "runner episode input")
    assert_no_private_material(payload)
    unknown = set(payload).difference(_RUNNER_REQUIRED_FIELDS)
    if unknown.intersection(_RUNNER_IDENTITY_FIELDS):
        raise SyntheticUserProtocolError("runner-visible arm identity is forbidden")
    if unknown:
        raise SyntheticUserProtocolError("runner episode input contains disallowed fields")
    missing = _RUNNER_REQUIRED_FIELDS.difference(payload)
    if missing:
        raise SyntheticUserProtocolError("runner episode input is missing required fields")
    result = {field: _text(payload[field], field, maximum=16_384) for field in _RUNNER_REQUIRED_FIELDS}
    if result["model"] != "deepseek-v4-flash":
        raise SyntheticUserProtocolError("runner must use the frozen base model")
    if not result["source_proxy_url"].startswith("http://source-broker:"):
        raise SyntheticUserProtocolError("runner must use the evaluator-controlled source proxy")
    return {field: result[field] for field in sorted(result)}


def build_simulator_request(*, conversation_id: str, turn_index: int, assistant_message: str) -> dict[str, str | int]:
    """Construct an anonymous request for the simulator service.

    The caller deliberately cannot attach host, arm, persona, task answer, or
    scorer metadata. The service maps the opaque conversation identifier to
    evaluator-owned state on its private volume.
    """

    return {
        "conversation_id": _text(conversation_id, "conversation_id", maximum=256),
        "turn_index": _positive_int(turn_index, "turn_index", maximum=50),
        "assistant_message": _text(assistant_message, "assistant_message", maximum=16_384),
    }


def validate_simulator_turn(
    raw: Mapping[str, object], *, known_private_markers: Sequence[str] = ()
) -> SyntheticUserTurn:
    """Validate a model-produced user turn before it reaches the tested host."""

    payload = _mapping(raw, "simulator turn")
    assert_no_private_material(payload, known_private_markers=known_private_markers)
    _require_exact_fields(payload, {"message", "disposition"}, "simulator turn")
    message = _text(payload["message"], "simulator message", maximum=16_384)
    disposition = _text(payload["disposition"], "simulator disposition", maximum=32)
    if disposition not in _TURN_DISPOSITIONS:
        raise SyntheticUserProtocolError("simulator disposition is not allowed")
    return SyntheticUserTurn(message=message, disposition=disposition)


def blinded_review_bundle(raw: Mapping[str, object], *, known_private_markers: Sequence[str] = ()) -> dict[str, object]:
    """Strip arm and host identity before a separate evaluator sees a transcript."""

    payload = _mapping(raw, "review bundle")
    assert_no_private_material(payload, known_private_markers=known_private_markers)
    blinded_episode_id = _text(payload.get("blinded_episode_id"), "blinded_episode_id", maximum=256)
    if not _BLINDED_ID_PATTERN.fullmatch(blinded_episode_id):
        raise SyntheticUserProtocolError("blinded episode id must be opaque")
    _assert_blinded_text(blinded_episode_id, "blinded episode id")
    transcript = payload.get("transcript")
    if not isinstance(transcript, list) or not transcript:
        raise SyntheticUserProtocolError("review transcript must be a non-empty list")
    blinded_transcript: list[dict[str, str]] = []
    for item in transcript:
        message = _mapping(item, "review transcript item")
        _require_exact_fields(message, {"role", "message"}, "review transcript item")
        role = _text(message["role"], "review role", maximum=32)
        if role not in {"assistant", "user"}:
            raise SyntheticUserProtocolError("review transcript role is not allowed")
        text = _text(message["message"], "review message", maximum=16_384)
        _assert_blinded_text(text, "review transcript")
        blinded_transcript.append({"role": role, "message": text})
    return {"blinded_episode_id": blinded_episode_id, "transcript": blinded_transcript}


def _assert_blinded_text(value: str, label: str) -> None:
    if _BLINDING_CUE_PATTERN.search(value):
        raise SyntheticUserProtocolError(f"{label} contains a host or arm cue")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SyntheticUserProtocolError(f"{label} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise SyntheticUserProtocolError(f"{label} keys must be strings")
    return value


def _walk_values(value: object):
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str):
                yield key, child
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def _require_exact_fields(payload: Mapping[str, object], required: set[str], label: str) -> None:
    unknown = set(payload).difference(required)
    if unknown:
        raise SyntheticUserProtocolError(f"{label} contains disallowed fields")
    missing = required.difference(payload)
    if missing:
        raise SyntheticUserProtocolError(f"{label} is missing required fields")


def _text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise SyntheticUserProtocolError(f"{label} must be a non-empty bounded string")
    return value


def _digest(value: object, label: str) -> str:
    digest = _text(value, label, maximum=80)
    if not _DIGEST_PATTERN.fullmatch(digest):
        raise SyntheticUserProtocolError(f"{label} must be a SHA-256 digest")
    return digest


def _positive_int(value: object, label: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise SyntheticUserProtocolError(f"{label} must be an integer between 1 and {maximum}")
    return value
