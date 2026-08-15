from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).parents[1]


def protocol_module():
    path = ROOT / "evaluation/harness/synthetic_user_protocol.py"
    spec = importlib.util.spec_from_file_location("synthetic_user_protocol", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROTOCOL = protocol_module()
SyntheticUserProtocolError = PROTOCOL.SyntheticUserProtocolError
blinded_review_bundle = PROTOCOL.blinded_review_bundle
build_simulator_request = PROTOCOL.build_simulator_request
validate_runner_episode_input = PROTOCOL.validate_runner_episode_input
validate_simulator_turn = PROTOCOL.validate_simulator_turn
validate_synthetic_user_policy = PROTOCOL.validate_synthetic_user_policy


DIGEST = "sha256:" + "a" * 64


def policy() -> dict[str, object]:
    return {
        "enabled": True,
        "evidence_kind": "synthetic-user-proxy",
        "human_experience_status": "unavailable",
        "persona_set_digest": DIGEST,
        "prompt_family_digest": "sha256:" + "b" * 64,
        "heldout_task_set_digest": "sha256:" + "c" * 64,
        "assignment_digest": "sha256:" + "d" * 64,
        "persona_prompt_location": "evaluator-owned",
        "persona_prompt_task_binding": "task-agnostic",
        "holdout_policy": "tasks-held-out-from-harness-development",
        "assignment_visibility": "evaluator-only-until-unblind",
        "simulator_service": "separate-network-service",
        "simulator_model": "deepseek-v4-flash",
        "review_blinding": "arm-and-host-hidden",
        "scoring_separation": "synthetic-user-cannot-score",
        "turn_limit": 8,
    }


def test_policy_requires_an_evaluator_owned_prompt_and_honest_evidence_label() -> None:
    validated = validate_synthetic_user_policy(policy())

    assert validated.evidence_kind == "synthetic-user-proxy"
    assert validated.human_experience_status == "unavailable"
    assert validated.prompt_family_digest.startswith("sha256:")

    invalid = {**policy(), "human_experience_status": "representative"}
    with pytest.raises(SyntheticUserProtocolError, match="human evidence"):
        validate_synthetic_user_policy(invalid)

    invalid = {**policy(), "scoring_separation": "synthetic-user-scores"}
    with pytest.raises(SyntheticUserProtocolError, match="cannot provide"):
        validate_synthetic_user_policy(invalid)


def test_runner_input_cannot_reveal_arm_or_persona_material() -> None:
    valid_input = {
        "episode_id": "episode-opaque-1",
        "initial_user_message": "Investigate the current claim and show sources.",
        "model": "deepseek-v4-flash",
        "source_proxy_url": "http://source-broker:8081",
    }

    assert validate_runner_episode_input(valid_input) == valid_input

    with pytest.raises(SyntheticUserProtocolError, match="runner-visible"):
        validate_runner_episode_input({**valid_input, "condition": "alpha2"})
    with pytest.raises(SyntheticUserProtocolError, match="private"):
        validate_runner_episode_input({**valid_input, "persona_prompt": "private instruction"})


def test_simulator_only_receives_an_anonymized_agent_turn() -> None:
    request = build_simulator_request(
        conversation_id="opaque-conversation-1",
        turn_index=2,
        assistant_message="I found two sources. Do you want a contradiction check?",
    )

    assert request == {
        "conversation_id": "opaque-conversation-1",
        "turn_index": 2,
        "assistant_message": "I found two sources. Do you want a contradiction check?",
    }
    assert "host" not in request
    assert "condition" not in request
    assert "persona" not in request


def test_simulator_turn_rejects_private_canaries_and_disallowed_fields() -> None:
    turn = validate_simulator_turn(
        {"message": "Please compare the two sources before deciding.", "disposition": "continue"},
        known_private_markers=("PRIVATE-CANARY-7",),
    )

    assert turn.disposition == "continue"
    with pytest.raises(SyntheticUserProtocolError, match="private"):
        validate_simulator_turn(
            {"message": "The private marker is PRIVATE-CANARY-7", "disposition": "continue"},
            known_private_markers=("PRIVATE-CANARY-7",),
        )
    with pytest.raises(SyntheticUserProtocolError, match="disallowed"):
        validate_simulator_turn(
            {"message": "Continue", "disposition": "continue", "unexpected": "metadata"},
        )

    with pytest.raises(SyntheticUserProtocolError, match="private"):
        validate_simulator_turn(
            {"message": "The evaluator note is hidden-rubric-marker.", "disposition": "continue"},
            known_private_markers=("hidden-rubric-marker",),
        )


def test_blinded_review_bundle_strips_host_and_condition_metadata() -> None:
    bundle = blinded_review_bundle(
        {
            "blinded_episode_id": "blind-12",
            "host": "claude_code",
            "condition": "alpha2",
            "transcript": [
                {"role": "user", "message": "Please research this."},
                {"role": "assistant", "message": "I will verify the sources."},
            ],
        }
    )

    assert bundle == {
        "blinded_episode_id": "blind-12",
        "transcript": [
            {"role": "user", "message": "Please research this."},
            {"role": "assistant", "message": "I will verify the sources."},
        ],
    }
    assert "claude" not in str(bundle)
    assert "alpha" not in str(bundle)


def test_blinded_review_bundle_rejects_identity_cues_and_private_markers() -> None:
    base = {
        "blinded_episode_id": "blind-9f2a",
        "transcript": [{"role": "assistant", "message": "I will verify the sources."}],
    }

    with pytest.raises(SyntheticUserProtocolError, match="host or arm cue"):
        blinded_review_bundle(
            {
                **base,
                "transcript": [{"role": "assistant", "message": "Claude Code found two sources."}],
            }
        )
    with pytest.raises(SyntheticUserProtocolError, match="opaque"):
        blinded_review_bundle({**base, "blinded_episode_id": "claude-alpha2"})
    with pytest.raises(SyntheticUserProtocolError, match="private"):
        blinded_review_bundle(
            {
                **base,
                "transcript": [{"role": "assistant", "message": "The secret marker is BLUE-CANARY."}],
            },
            known_private_markers=("blue-canary",),
        )
