"""Goal-satisfaction completion gate (#429) named contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_goal_wiring import projection
from test_research_run_coordinator import (
    _initialize,
    _ready_frame,
    _register_canonical_completion_inputs,
)

from research_tree.completion_inputs import (
    GOAL_SATISFACTION_KIND,
    CompletionInputError,
    CompletionInputRegistrar,
)
from research_tree.coordinator import (
    COMPLETION_RECORD_KIND,
    CompletionBlockedError,
)
from research_tree.domain import ArtifactRef, thaw_json
from research_tree.strategy_projection import authority_fingerprint

RUN = "run-57"
ORACLE_1 = {"id": "oracle-1", "evidence_standard_ids": ("standard-1",)}
ORACLE_2 = {"id": "oracle-2", "evidence_standard_ids": ("standard-2",)}


def _confirm_projection(ledger, coordinator, success_oracles=(ORACLE_1,)):
    """Confirm a falsifiable projection for run-57 (mirrors _confirm_strategy)."""

    artifacts = ledger.load_run(RUN).artifacts
    handoff = next(item for item in artifacts if item.kind == "alignment-handoff")
    target = next(item for item in artifacts if item.kind == "blueprint-target")
    target_ref = ArtifactRef(RUN, target.id, target.revision)
    frame = coordinator.persist_decision_frame(
        _ready_frame(frame_id="strategy-frame", target_ref=target_ref),
        expected_revision=ledger.get_revision(RUN),
    )
    goal_projection = projection(
        RUN,
        frame_ref=ArtifactRef(RUN, frame.id, frame.revision),
        handoff_ref=ArtifactRef(RUN, handoff.id, handoff.revision),
        target_ref=target_ref,
        decision_targets=({"id": "decision-1", "oracle_ids": tuple(o["id"] for o in success_oracles)},),
        success_oracles=success_oracles,
        status="displayed",
    )
    coordinator.persist_strategy_projection(goal_projection, expected_revision=ledger.get_revision(RUN))
    coordinator.display_strategy(RUN, goal_projection, expected_revision=ledger.get_revision(RUN))
    coordinator.confirm_handoff(
        RUN,
        projection_ref=ArtifactRef(RUN, goal_projection.id, goal_projection.revision),
        confirmation=f"I accept {goal_projection.display_digest} authority-fingerprint {authority_fingerprint(goal_projection)} and authorize research.",
        expected_revision=ledger.get_revision(RUN),
    )


def _finding_pack(ledger, artifact_id="pack-goal-evidence"):
    return ledger.append_artifact(
        RUN,
        artifact_id,
        "finding-pack",
        {"id": artifact_id, "round_id": RUN},
        expected_revision=ledger.get_revision(RUN),
    )


def _satisfy(registrar, ledger, oracle_id, pack):
    registrar.write_goal_satisfaction(
        round_id=RUN,
        registration_id=f"goal-{oracle_id}",
        oracle_id=oracle_id,
        verdict="satisfied",
        evidence_refs=(ArtifactRef(RUN, pack.id, pack.revision),),
        expected_revision=ledger.get_revision(RUN),
    )


def _advance(ledger, coordinator):
    for event in ("batch_checkpoint", "all_slots_closed", "readiness_passed", "deliveries_compiled"):
        coordinator.transition(RUN, event, "coordinator", expected_revision=ledger.get_revision(RUN))


def _target(ledger):
    artifacts = ledger.load_run(RUN).artifacts
    return next(item for item in artifacts if item.kind == "blueprint-target")


def _prepare(
    ledger,
    coordinator,
    *,
    register=True,
    satisfy=(),
    oracles=(ORACLE_1,),
):
    """Drive run-57 to awaiting_acceptance with optional goal-gate pieces."""

    _confirm_projection(ledger, coordinator, success_oracles=oracles)
    if register:
        _register_canonical_completion_inputs(ledger, RUN, _target(ledger))
    for oracle_id in satisfy:
        _satisfy(
            CompletionInputRegistrar(ledger),
            ledger,
            oracle_id,
            _finding_pack(ledger),
        )
    _advance(ledger, coordinator)


# ---------------------------------------------------------------------------
# Named contract tests
# ---------------------------------------------------------------------------


def test_goal_satisfaction_all_satisfied_passes(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare(ledger, coordinator, satisfy=("oracle-1",))

    completed = coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))

    assert completed.payload["state"] == "completed"
    record = next(item for item in ledger.load_run(RUN).artifacts if item.kind == COMPLETION_RECORD_KIND)
    refs = record.payload["manifold"]["goal_satisfaction_refs"]
    assert [ArtifactRef.from_dict(dict(ref)) for ref in refs] == [ArtifactRef(RUN, "goal-oracle-1", 1)]
    assert coordinator.why_not_complete(RUN)["unmet_obligations"] == ()


def test_unmet_oracle_blocks_complete(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare(ledger, coordinator)
    CompletionInputRegistrar(ledger).write_goal_satisfaction(
        round_id=RUN,
        registration_id="goal-oracle-1",
        oracle_id="oracle-1",
        verdict="unmet",
        expected_revision=ledger.get_revision(RUN),
    )

    why = coordinator.why_not_complete(RUN)
    assert why["field_diagnostics"]["goal_satisfaction"] == {
        "status": "fail",
        "reason": "oracle_uncovered",
        "oracles": ["oracle-1"],
    }
    assert "goal_satisfaction" in why["unmet_obligations"]
    assert "resolve:goal_satisfaction:oracle-1" in why["next_actions"]

    with pytest.raises(CompletionBlockedError, match="goal_satisfaction"):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


def test_missing_oracle_registration_blocks(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare(ledger, coordinator)

    why = coordinator.why_not_complete(RUN)
    detail = why["field_diagnostics"]["goal_satisfaction"]
    assert detail["reason"] == "oracle_uncovered"
    assert detail["oracles"] == ["oracle-1"]
    assert "goal_satisfaction" in why["unmet_obligations"]

    with pytest.raises(CompletionBlockedError):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


def test_waived_requires_reason(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    registrar = CompletionInputRegistrar(ledger)
    before = len(ledger.load_run(RUN).artifacts)

    with pytest.raises(CompletionInputError, match="waiver_reason"):
        registrar.write_goal_satisfaction(
            round_id=RUN,
            registration_id="goal-oracle-1",
            oracle_id="oracle-1",
            verdict="waived",
            expected_revision=ledger.get_revision(RUN),
        )

    assert len(ledger.load_run(RUN).artifacts) == before
    assert GOAL_SATISFACTION_KIND == "goal-satisfaction"


def test_duplicate_oracle_registration_fails(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare(ledger, coordinator)
    registrar = CompletionInputRegistrar(ledger)
    for registration_id, pack_id in (("goal-oracle-1", "pack-dup-1"), ("goal-oracle-1-again", "pack-dup-2")):
        pack = _finding_pack(ledger, pack_id)
        registrar.write_goal_satisfaction(
            round_id=RUN,
            registration_id=registration_id,
            oracle_id="oracle-1",
            verdict="satisfied",
            evidence_refs=(ArtifactRef(RUN, pack.id, pack.revision),),
            expected_revision=ledger.get_revision(RUN),
        )

    why = coordinator.why_not_complete(RUN)
    detail = why["field_diagnostics"]["goal_satisfaction"]
    assert detail == {
        "status": "fail",
        "reason": "oracle_duplicate",
        "oracles": ["oracle-1"],
    }
    assert "goal_satisfaction" in why["unmet_obligations"]

    with pytest.raises(CompletionBlockedError):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


def test_legacy_run_without_projection_fails_closed(tmp_path: Path) -> None:
    """A run whose confirmation record no longer resolves (no confirmed projection,
    e.g. a pre-#427 run or a superseded confirmation) fails closed with
    goal_satisfaction_unknown instead of silently completing."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare(ledger, coordinator)
    confirmed = next(item for item in ledger.load_run(RUN).artifacts if item.kind == "strategy-projection")
    revised = thaw_json(confirmed.payload)
    revised["revision"] = 2
    revised["display_payload"]["revision"] = 2
    revised["display_digest"] = "a" * 64
    revised["content_hash"] = "b" * 64
    ledger.append_artifact(
        RUN,
        confirmed.id,
        "strategy-projection",
        revised,
        parent_refs=(ArtifactRef(RUN, confirmed.id, confirmed.revision),),
        expected_revision=ledger.get_revision(RUN),
    )

    why = coordinator.why_not_complete(RUN)
    assert why["field_diagnostics"]["goal_satisfaction"] == {
        "status": "fail",
        "reason": "goal_satisfaction_unknown",
    }
    assert "goal_satisfaction" in why["unmet_obligations"]

    with pytest.raises(CompletionBlockedError):
        coordinator.transition(RUN, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN))


def test_why_not_complete_names_oracles(tmp_path: Path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _prepare(ledger, coordinator, satisfy=("oracle-1",), oracles=(ORACLE_1, ORACLE_2))

    why = coordinator.why_not_complete(RUN)
    assert why["field_diagnostics"]["goal_satisfaction"]["reason"] == "oracle_uncovered"
    assert why["field_diagnostics"]["goal_satisfaction"]["oracles"] == ["oracle-2"]
    assert why["next_actions"] == [
        "resolve:goal_satisfaction",
        "resolve:goal_satisfaction:oracle-2",
    ]
