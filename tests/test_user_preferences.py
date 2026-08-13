from __future__ import annotations

from pathlib import Path

import pytest

from research_tree.preferences import (
    PreferenceObservation,
    PreferenceService,
    PreferenceValidationError,
)


def observation(
    observation_id: str,
    turn: int,
    value: str,
    *,
    key: str = "research.depth",
    basis: str = "inferred",
    supersedes: str | None = None,
) -> PreferenceObservation:
    return PreferenceObservation.create(
        observation_id=observation_id,
        project_id="project-one",
        turn_number=turn,
        key=key,
        value=value,
        basis=basis,
        source_ref=f"input-{turn}",
        privacy="project-local",
        reversal_condition="a current explicit request or repeated contrary evidence",
        supersedes_observation_id=supersedes,
    )


def test_observation_is_content_bound_and_rejects_sensitive_or_extra_fields() -> None:
    item = observation("obs-1", 1, "deep", basis="explicit")
    assert PreferenceObservation.from_dict(item.to_dict()) == item
    assert len(item.content_hash) == 64

    with pytest.raises(PreferenceValidationError, match="sensitive preference key"):
        observation("obs-secret", 2, "x", key="demographic.age")
    payload = item.to_dict()
    payload["raw_transcript"] = "private words"
    with pytest.raises(PreferenceValidationError, match="fields"):
        PreferenceObservation.from_dict(payload)


def test_explicit_preference_is_immediate_and_inferred_contradiction_is_shadowed(tmp_path: Path) -> None:
    service = PreferenceService(tmp_path)
    for turn in range(1, 6):
        service.observe(observation(f"obs-{turn}", turn, "bounded"))
    assert service.inspect("project-one").entry("research.depth").status == "candidate"

    profile = service.observe(observation("obs-explicit", 6, "deep", basis="explicit"))
    entry = profile.entry("research.depth")
    assert (entry.value, entry.status, entry.precedence) == ("deep", "active", "current-explicit")

    profile = service.observe(observation("obs-one-off", 10, "bounded"))
    entry = profile.entry("research.depth")
    assert (entry.value, entry.status, entry.shadow_value) == ("deep", "contested", "bounded")
    assert entry.lineage[-1]["before"] == {"status": "active", "value": "deep"}
    assert entry.lineage[-1]["after"] == {"status": "contested", "value": "deep"}


def test_repeated_evidence_advances_at_most_one_state_per_five_turn_refresh(tmp_path: Path) -> None:
    service = PreferenceService(tmp_path)
    for turn in range(1, 6):
        profile = service.observe(observation(f"obs-{turn}", turn, "concise"))
    assert (profile.last_refresh_turn, profile.entry("research.depth").status) == (5, "candidate")

    for turn in range(6, 11):
        profile = service.observe(observation(f"obs-{turn}", turn, "concise"))
    assert (profile.last_refresh_turn, profile.entry("research.depth").status) == (10, "active")

    for turn in range(11, 16):
        profile = service.observe(observation(f"obs-{turn}", turn, "detailed"))
    entry = profile.entry("research.depth")
    assert (entry.value, entry.status, entry.shadow_value, entry.shadow_refreshes) == (
        "concise",
        "contested",
        "detailed",
        1,
    )

    for turn in range(16, 21):
        profile = service.observe(observation(f"obs-{turn}", turn, "detailed"))
    entry = profile.entry("research.depth")
    assert (entry.value, entry.status, entry.shadow_value) == ("detailed", "active", None)
    assert entry.lineage[-1]["before"] == {"status": "contested", "value": "concise"}
    assert entry.lineage[-1]["after"] == {"status": "active", "value": "detailed"}


def test_turn_jump_processes_each_elapsed_refresh_boundary(tmp_path: Path) -> None:
    service = PreferenceService(tmp_path)
    profile = service.observe(observation("obs-12", 12, "deep"))
    assert (profile.last_refresh_turn, profile.next_refresh_turn) == (10, 15)
    assert profile.pending_observation_ids == ("obs-12",)

    explicit = service.observe(observation("explicit-12", 12, "recursive", basis="explicit"))
    assert (explicit.entry("research.depth").value, explicit.entry("research.depth").status) == ("recursive", "active")


def test_unreinforced_preference_ages_to_stale_without_reversal(tmp_path: Path) -> None:
    service = PreferenceService(tmp_path, stale_after_refreshes=2)
    service.observe(observation("depth-1", 1, "deep", basis="explicit"))
    for turn in range(2, 11):
        service.observe(observation(f"delivery-{turn}", turn, "technical", key="delivery.style"))
    entry = service.inspect("project-one").entry("research.depth")
    assert (entry.value, entry.status) == ("deep", "stale")


def test_reload_restores_exact_profile_and_pending_observations(tmp_path: Path) -> None:
    service = PreferenceService(tmp_path)
    for turn in range(1, 4):
        service.observe(observation(f"obs-{turn}", turn, "deep"))
    before = service.inspect("project-one")

    restored = PreferenceService(tmp_path).inspect("project-one")
    assert restored == before
    assert restored.revision == 3
    assert restored.pending_observation_ids == ("obs-1", "obs-2", "obs-3")
    assert restored.next_refresh_turn == 5


def test_correct_reset_and_delete_are_project_scoped(tmp_path: Path) -> None:
    service = PreferenceService(tmp_path)
    service.observe(observation("obs-1", 1, "deep", basis="explicit"))
    corrected = service.correct(
        project_id="project-one",
        key="research.depth",
        value="bounded",
        turn_number=2,
        source_ref="correction-2",
        reversal_condition="requester changes the depth again",
    )
    assert corrected.entry("research.depth").value == "bounded"
    assert corrected.entry("research.depth").source_observation_ids == (corrected.observation_ids[-1],)

    reset = service.reset("project-one")
    assert reset.entries == ()
    assert len(service.list_observations("project-one")) == 2

    service.observe(
        PreferenceObservation.create(
            **{
                **observation("other-1", 1, "deep", basis="explicit").to_dict(),
                "project_id": "project-two",
                "content_hash": None,
            }
        )
    )
    service.delete("project-one")
    assert service.list_observations("project-one") == ()
    assert service.inspect("project-one").revision == 0
    assert len(service.list_observations("project-two")) == 1


def test_strategy_influences_record_profile_or_current_explicit_precedence(tmp_path: Path) -> None:
    service = PreferenceService(tmp_path)
    profile = service.observe(observation("obs-1", 1, "deep", basis="explicit"))

    profile_effect = service.strategy_influences(profile)
    assert profile_effect == (
        {
            "profile_revision": 1,
            "observation_id": "obs-1",
            "key": "research.depth",
            "selected_value": "deep",
            "precedence": "profile",
            "reversal_condition": "a current explicit request or repeated contrary evidence",
        },
    )
    explicit_effect = service.strategy_influences(profile, current_explicit={"research.depth": "bounded"})
    assert explicit_effect[0]["selected_value"] == "bounded"
    assert explicit_effect[0]["precedence"] == "current-explicit"
