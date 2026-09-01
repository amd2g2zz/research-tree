"""Tests for authority-field binding at handoff confirmation (issue #292 gate 1).

The senior-user evaluation (senior-user-ux-20260820) observed a compiled
handoff retaining an earlier reconnaissance-only scope/authority after the
user granted broader research authority: confirmation was digest-bound but
compilation never re-materialized and compared each authority-bearing field.

Gate 1 fix: confirmation must embed an authority fingerprint over the five
authority-bearing fields (primary decision outcome, autonomy scope, authority
boundary, success oracles, delivery contract), and the downstream research
initialization must recompute the fingerprint and reject any drift BEFORE any
execution happens.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from strategy_support import prepare_strategy  # noqa: E402

from research_tree.coordinator import CoordinatorConflictError  # noqa: E402
from research_tree.domain import ArtifactRef  # noqa: E402
from research_tree.run_ledger import RunLedger  # noqa: E402
from research_tree.strategy_projection import authority_fingerprint  # noqa: E402


def _coordinator(tmp_path: Path):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-host")
    handoff = ledger.append_artifact(
        "run-host",
        "handoff-1",
        "alignment-handoff",
        {"confirmed": True},
        expected_revision=ledger.get_revision("run-host"),
    )
    target = ledger.append_artifact(
        "run-host",
        "target-1",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1", "priority": "P0"}]},
        parent_refs=(ArtifactRef("run-host", handoff.id, handoff.revision),),
        expected_revision=ledger.get_revision("run-host"),
    )
    from research_tree.coordinator import ResearchRunCoordinator

    coordinator = ResearchRunCoordinator(ledger)
    coordinator.initialize(
        run_id="run-host",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-host"),
    )
    return ledger, coordinator, "run-host"


def _confirmation(projection) -> str:
    return (
        f"I accept {projection.display_digest} "
        f"authority-fingerprint {authority_fingerprint(projection)} "
        "and authorize research."
    )


def test_confirmation_without_fingerprint_rejected(tmp_path: Path) -> None:
    ledger, coordinator, run_id = _coordinator(tmp_path)
    projection = prepare_strategy(ledger, coordinator, run_id)
    coordinator.display_strategy(run_id, projection, expected_revision=ledger.get_revision(run_id))
    with pytest.raises(CoordinatorConflictError, match="authority_fingerprint_required"):
        coordinator.confirm_handoff(
            run_id,
            projection_ref=ArtifactRef(run_id, projection.id, projection.revision),
            confirmation=f"I accept {projection.display_digest} and authorize research.",
            expected_revision=ledger.get_revision(run_id),
        )


def test_confirmation_with_wrong_fingerprint_rejected(tmp_path: Path) -> None:
    ledger, coordinator, run_id = _coordinator(tmp_path)
    projection = prepare_strategy(ledger, coordinator, run_id)
    coordinator.display_strategy(run_id, projection, expected_revision=ledger.get_revision(run_id))
    with pytest.raises(CoordinatorConflictError, match="authority_fingerprint_mismatch"):
        coordinator.confirm_handoff(
            run_id,
            projection_ref=ArtifactRef(run_id, projection.id, projection.revision),
            confirmation=(
                f"I accept {projection.display_digest} authority-fingerprint {'0' * 64} and authorize research."
            ),
            expected_revision=ledger.get_revision(run_id),
        )


def test_confirmation_with_correct_fingerprint_accepted(tmp_path: Path) -> None:
    ledger, coordinator, run_id = _coordinator(tmp_path)
    projection = prepare_strategy(ledger, coordinator, run_id)
    coordinator.display_strategy(run_id, projection, expected_revision=ledger.get_revision(run_id))
    coordinator.confirm_handoff(
        run_id,
        projection_ref=ArtifactRef(run_id, projection.id, projection.revision),
        confirmation=_confirmation(projection),
        expected_revision=ledger.get_revision(run_id),
    )
    # The fingerprint lands on the persisted lifecycle event, not on the
    # returned state artifact.
    event = next(
        item
        for item in ledger.load_run(run_id).artifacts
        if item.kind == "lifecycle-event" and item.payload.get("event") == "handoff_confirmed"
    )
    assert event.payload["payload"]["authority_fingerprint"] == authority_fingerprint(projection)


def test_guard_rejects_authority_drift_after_confirmation(tmp_path: Path) -> None:
    """A projection whose authority fields changed AFTER confirmation fails
    the handoff_confirmed guard — drift is blocked before compilation."""
    ledger, coordinator, run_id = _coordinator(tmp_path)
    projection = prepare_strategy(ledger, coordinator, run_id)
    coordinator.display_strategy(run_id, projection, expected_revision=ledger.get_revision(run_id))
    coordinator.confirm_handoff(
        run_id,
        projection_ref=ArtifactRef(run_id, projection.id, projection.revision),
        confirmation=_confirmation(projection),
        expected_revision=ledger.get_revision(run_id),
    )
    # Widen the authority fields after the fact: the persisted confirmation
    # fingerprint no longer matches the recomputed fingerprint, so the guard
    # fails with a named reason instead of letting stale authority compile.
    drifted = coordinator.revise_strategy(
        run_id,
        projection_ref=ArtifactRef(run_id, projection.id, projection.revision),
        changes={"autonomy_envelope": {"allowed": ["research", "implementation"], "authority": "broad"}},
        expected_revision=ledger.get_revision(run_id),
    )
    event = next(
        item
        for item in ledger.load_run(run_id).artifacts
        if item.kind == "lifecycle-event" and item.payload.get("event") == "handoff_confirmed"
    )
    recorded_payload = dict(event.payload["payload"])
    recorded_payload["projection_ref"] = ArtifactRef(run_id, drifted.id, drifted.revision).to_dict()
    # Satisfy the digest checks so the fingerprint check is what fails: the
    # recorded fingerprint was computed over the ORIGINAL authority fields,
    # and the drifted projection's fields no longer match it. This models a
    # replayed/tampered confirmation payload whose digest was re-derived but
    # whose recorded fingerprint is stale.
    recorded_payload["display_digest"] = drifted.payload["display_digest"]
    recorded_payload["confirmation"] = f"I accept {drifted.payload['display_digest']} and authorize research."
    allowed, reason = coordinator._guard_passes(run_id, "handoff_confirmed", recorded_payload)
    assert allowed is False
    assert reason == "authority_fingerprint_drift"


def test_fingerprint_is_deterministic_and_field_sensitive() -> None:
    values = dict(
        projection_id="strategy-projection",
        run_id="run-fp",
        decision_frame_ref=ArtifactRef("run-fp", "frame-1", 1),
        alignment_handoff_ref=ArtifactRef("run-fp", "handoff-1", 1),
        target_ref=ArtifactRef("run-fp", "target-1", 1),
        current_understanding="u",
        assumptions=("a",),
        decision_targets=("d",),
        tracks=({"id": "track-1"},),
        method_hypotheses=({"method": "repository"},),
        depth="deep",
        evidence_expectations=("e",),
        autonomy_envelope={"allowed": ["research"], "authority": "bounded"},
        replanning_policy={"same_round": ["depth"]},
        success_oracles=({"id": "oracle-1", "evidence_standard_ids": ("s1",)},),
        delivery_contract={"technical": "package", "human": "report"},
        stop_rule="oracles pass",
        preference_influences=(),
        revision=1,
        status="displayed",
    )
    from research_tree.strategy_projection import StrategyProjection

    base = StrategyProjection.create(**values, display_digest="0" * 64, content_hash="1" * 64)
    widened = StrategyProjection.create(
        **{**values, "autonomy_envelope": {"allowed": ["research", "implementation"], "authority": "broad"}},
        display_digest="0" * 64,
        content_hash="1" * 64,
    )
    narrowed = StrategyProjection.create(
        **{**values, "delivery_contract": {"technical": "package", "human": "brief"}},
        display_digest="0" * 64,
        content_hash="1" * 64,
    )
    assert authority_fingerprint(base) == authority_fingerprint(base)
    assert authority_fingerprint(base) != authority_fingerprint(widened)
    assert authority_fingerprint(base) != authority_fingerprint(narrowed)
