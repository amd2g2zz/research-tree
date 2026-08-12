from __future__ import annotations

import hashlib
import json

import pytest

from research_tree.domain import ArtifactRef, canonical_json_bytes
from research_tree.strategy_projection import (
    STRATEGY_PROJECTION_KIND,
    StrategyProjection,
    StrategyProjectionError,
    macro_stage,
)


def _ref(artifact_id: str, revision: int = 1) -> ArtifactRef:
    return ArtifactRef("run-85", artifact_id, revision)


def projection(**overrides: object) -> StrategyProjection:
    values: dict[str, object] = {
        "projection_id": "projection-1",
        "run_id": "run-85",
        "decision_frame_ref": _ref("frame-1"),
        "alignment_handoff_ref": _ref("handoff-1"),
        "target_ref": _ref("target-1"),
        "current_understanding": "Validate the primary customer decision before implementation research.",
        "assumptions": ("The requester owns the success definition.",),
        "decision_targets": ("primary-decision",),
        "tracks": ({"id": "track-1", "question": "Which evidence resolves the target?"},),
        "method_hypotheses": ({"method": "repository", "reason": "inspect current contracts"},),
        "depth": "deep",
        "evidence_expectations": ("independent source",),
        "autonomy_envelope": {"allowed": ["research"], "forbidden": ["change-target"]},
        "replanning_policy": {"same_round": ["method", "depth"], "successor": ["target"]},
        "success_oracles": ("oracle-primary",),
        "delivery_contract": {"technical": "package", "human": "report"},
        "stop_rule": "stop after current oracles pass or authority is required",
        "revision": 1,
        "status": "displayed",
    }
    values.update(overrides)
    return StrategyProjection.create(**values)


def test_projection_requires_all_strategy_contract_fields_and_digest() -> None:
    item = projection()
    assert item.kind == STRATEGY_PROJECTION_KIND
    assert len(item.display_digest) == 64
    restored = StrategyProjection.from_dict(item.to_dict())
    assert restored == item
    payload = item.to_dict()
    assert hashlib.sha256(canonical_json_bytes(payload["display_payload"])).hexdigest() == item.display_digest

    with pytest.raises(StrategyProjectionError, match="stop_rule"):
        projection(stop_rule="")


def test_projection_rejects_wrong_parent_run_and_unknown_status() -> None:
    with pytest.raises(StrategyProjectionError, match="run_id"):
        projection(target_ref=ArtifactRef("other-run", "target-1", 1))
    with pytest.raises(StrategyProjectionError, match="status"):
        projection(status="ready")


def test_macro_stage_is_canonical_and_pause_resume_is_monotonic() -> None:
    assert macro_stage("alignment") == 1
    assert macro_stage("handoff_pending") == 2
    assert macro_stage("autonomous_research") == 3
    assert macro_stage("delivery_pending") == 3
    assert macro_stage("awaiting_acceptance") == 4
    assert macro_stage("paused", prior_stage=3) == 3
    with pytest.raises(StrategyProjectionError, match="prior_stage"):
        macro_stage("paused")


def test_schema_fixture_is_versioned() -> None:
    from pathlib import Path

    root = Path(__file__).parents[1]
    schema = json.loads(
        (root / "openspec/changes/unify-research-runtime-alpha2/schemas/strategy-projection-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["$id"].endswith("strategy-projection-v1.json")
    assert schema["properties"]["schema_version"]["const"] == 1


def test_projection_binds_preference_influence_lineage() -> None:
    item = projection(
        preference_influences=(
            {
                "profile_revision": 4,
                "observation_id": "obs-4",
                "key": "research.depth",
                "selected_value": "deep",
                "precedence": "profile",
                "reversal_condition": "current explicit input requests another depth",
            },
        )
    )
    restored = StrategyProjection.from_dict(item.to_dict())
    assert restored.preference_influences[0]["observation_id"] == "obs-4"
    assert item.display_payload["preference_influences"][0]["precedence"] == "profile"

    with pytest.raises(StrategyProjectionError, match="precedence"):
        projection(
            preference_influences=(
                {
                    "profile_revision": 4,
                    "observation_id": "obs-4",
                    "key": "research.depth",
                    "selected_value": "deep",
                    "precedence": "implicit",
                    "reversal_condition": "requester correction",
                },
            )
        )


def test_legacy_projection_without_preference_field_remains_readable() -> None:
    item = projection()
    payload = item.to_dict()
    payload.pop("preference_influences")
    payload["display_payload"].pop("preference_influences")
    payload["display_digest"] = hashlib.sha256(canonical_json_bytes(payload["display_payload"])).hexdigest()
    payload["content_hash"] = hashlib.sha256(
        canonical_json_bytes({**payload["display_payload"], "display_digest": payload["display_digest"]})
    ).hexdigest()

    restored = StrategyProjection.from_dict(payload)
    assert restored.preference_influences == ()
    assert restored.to_dict()["preference_influences"] == []
