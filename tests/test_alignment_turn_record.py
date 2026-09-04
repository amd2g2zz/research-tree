"""Alignment turn-record persistence and continuity gate (issue #497).

The issue's scenarios, named after them: a simulated 4+ turn conversation
whose state file exists, grows per turn, and grounds the agent's model of
the brief (the continuity gate reads before allowing the move); compaction /
long-session loss where a deleted, stale, or corrupt record blocks the next
alignment turn fail-closed; and the self-ask/self-answer guard where a turn
attempt with no persisted delta is rejected as a protocol violation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_tree.alignment_turn_record import (
    AlignmentTurnRecordStore,
    ContinuityGateError,
    TurnRecordError,
    refresh_validation,
)
from research_tree.turn_contract import (
    RESPONSE_CLASS_DISCRIMINATION,
    RESPONSE_CLASS_GENERATION,
    ContractTerms,
    CostCap,
    MissingTraceError,
)

RUN_ROOT_PARTS = (".research-tree", "projects", "topic-1", "runs", "run-1")


def store(tmp_path: Path) -> AlignmentTurnRecordStore:
    run_root = tmp_path.joinpath(*RUN_ROOT_PARTS)
    run_root.mkdir(parents=True, exist_ok=True)
    return AlignmentTurnRecordStore(run_root)


def terms(required_traces: tuple[str, ...] = ("option-set",)) -> ContractTerms:
    return ContractTerms(
        target_gap="scope-backend",
        required_traces=required_traces,
        cost_cap=CostCap(response_class=RESPONSE_CLASS_DISCRIMINATION, max_sentences=1),
    )


def append_turn(store: AlignmentTurnRecordStore, turn: int, **overrides: object) -> object:
    fields: dict[str, object] = {
        "turn_index": turn,
        "mirror": f"mirror {turn}",
        "gap": f"gap {turn}",
        "delta_summary": f"delta {turn}",
        "user_move": RESPONSE_CLASS_GENERATION,
    }
    fields.update(overrides)
    return store.append(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Scenario: the record file exists and grows per turn (simulated 4+ turns)
# ---------------------------------------------------------------------------


def test_four_turn_conversation_appends_one_record_per_turn(tmp_path: Path) -> None:
    target = store(tmp_path)
    for turn in range(1, 5):
        append_turn(target, turn)

    assert target.records_path.is_file()
    lines = target.records_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4

    records = target.records()
    assert [record.turn_index for record in records] == [1, 2, 3, 4]
    assert records[3].mirror == "mirror 4"
    assert records[3].gap == "gap 4"
    assert records[3].delta == {"summary": "delta 4", "nodes": []}
    assert records[3].user_move == RESPONSE_CLASS_GENERATION
    assert target.latest() is not None and target.latest().turn_index == 4  # type: ignore[union-attr]
    assert target.next_turn_index() == 5


def test_record_round_trips_contract_terms_and_traces_from_the_seam(tmp_path: Path) -> None:
    target = store(tmp_path)
    contract = terms()
    traces = ({"type": "option-set", "payload": {"options": ["postgres", "sqlite"]}},)
    append_turn(target, 1, contract_terms=contract, traces=traces)

    record = target.latest()
    assert record is not None
    assert record.contract_terms == contract
    assert record.traces == traces
    # The persisted JSON uses the seam schema verbatim.
    persisted = json.loads(target.records_path.read_text(encoding="utf-8").splitlines()[0])
    assert persisted["contract_terms"] == contract.to_dict()
    assert persisted["traces"] == list(traces)


def test_missing_required_trace_fails_naming_the_term(tmp_path: Path) -> None:
    target = store(tmp_path)
    with pytest.raises(MissingTraceError, match="possibility-survey"):
        append_turn(
            target,
            1,
            contract_terms=terms(required_traces=("possibility-survey",)),
            traces=({"type": "option-set", "payload": {"options": ["a"]}},),
        )
    assert not target.records_path.exists()


def test_trace_without_terms_is_validated_against_the_registry(tmp_path: Path) -> None:
    target = store(tmp_path)
    with pytest.raises(TurnRecordError, match="unregistered"):
        append_turn(target, 1, traces=({"type": "brainwave", "payload": {"idea": "x"}},))
    with pytest.raises(TurnRecordError, match="options"):
        append_turn(target, 1, traces=({"type": "option-set", "payload": {"wrong": "x"}},))


def test_user_move_outside_the_seam_response_classes_is_rejected(tmp_path: Path) -> None:
    target = store(tmp_path)
    with pytest.raises(TurnRecordError, match="user_move"):
        append_turn(target, 1, user_move="self-answered")
    assert not target.records_path.exists()


def test_mirror_gap_and_delta_nodes_are_validated(tmp_path: Path) -> None:
    target = store(tmp_path)
    with pytest.raises(TurnRecordError, match="mirror"):
        append_turn(target, 1, mirror="   ")
    with pytest.raises(TurnRecordError, match="gap"):
        append_turn(target, 1, gap="")
    with pytest.raises(TurnRecordError, match="node id"):
        append_turn(target, 1, delta_nodes=("has spaces",))
    append_turn(target, 1, delta_nodes=("scope-backend", "risk-latency-1"))
    assert target.latest() is not None  # type: ignore[union-attr]
    assert target.latest().delta == {"summary": "delta 1", "nodes": ["scope-backend", "risk-latency-1"]}  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Scenario: the continuity gate reads before allowing the move
# ---------------------------------------------------------------------------


def test_continuity_gate_returns_grounding_for_the_next_turn(tmp_path: Path) -> None:
    target = store(tmp_path)
    for turn in range(1, 4):
        append_turn(target, turn)

    verdict = target.check_continuity(4)
    assert verdict["status"] == "allowed"
    assert verdict["grounding"]["turn_index"] == 3
    assert verdict["grounding"]["mirror"] == "mirror 3"
    assert verdict["grounding"]["gap"] == "gap 3"
    assert verdict["grounding"]["delta"] == {"summary": "delta 3", "nodes": []}


def test_continuity_gate_allows_regrounding_after_compaction_or_crash(tmp_path: Path) -> None:
    target = store(tmp_path)
    append_turn(target, 1)
    append_turn(target, 2)
    # The record for this exchange is already persisted: re-ground, do not block.
    verdict = target.check_continuity(2)
    assert verdict["status"] == "allowed"
    assert verdict["grounding"]["turn_index"] == 2


def test_continuity_gate_allows_the_opening_turn(tmp_path: Path) -> None:
    target = store(tmp_path)
    verdict = target.check_continuity(1)
    assert verdict == {"status": "allowed", "grounding": None, "record_count": 0}


# ---------------------------------------------------------------------------
# Scenario: a deleted/stale record blocks the next turn (fail-closed)
# ---------------------------------------------------------------------------


def test_missing_record_file_blocks_the_next_turn(tmp_path: Path) -> None:
    target = store(tmp_path)
    with pytest.raises(ContinuityGateError, match="missing_turn_record"):
        target.check_continuity(2)


def test_stale_record_blocks_the_next_turn(tmp_path: Path) -> None:
    target = store(tmp_path)
    append_turn(target, 1)
    with pytest.raises(ContinuityGateError, match="stale_turn_record"):
        target.check_continuity(4)


def test_corrupt_record_file_blocks_the_next_turn(tmp_path: Path) -> None:
    target = store(tmp_path)
    append_turn(target, 1)
    target.records_path.write_text(
        target.records_path.read_text(encoding="utf-8") + "{not json at all}\n", encoding="utf-8"
    )
    with pytest.raises(ContinuityGateError, match="invalid_turn_record"):
        target.check_continuity(2)


def test_append_refuses_out_of_order_turn_indices(tmp_path: Path) -> None:
    target = store(tmp_path)
    append_turn(target, 1)
    with pytest.raises(ContinuityGateError, match="missing_turn_record"):
        append_turn(target, 3)
    with pytest.raises(ContinuityGateError, match="duplicate_turn_index"):
        append_turn(target, 1)
    assert len(target.records()) == 1


def test_append_rejects_non_positive_turn_index(tmp_path: Path) -> None:
    target = store(tmp_path)
    with pytest.raises(TurnRecordError, match="turn_index"):
        append_turn(target, 0)


# ---------------------------------------------------------------------------
# Scenario: a turn with no persisted delta is a protocol violation
# (self-ask/self-answer guard)
# ---------------------------------------------------------------------------


def test_turn_without_persisted_delta_is_rejected_as_protocol_violation(tmp_path: Path) -> None:
    target = store(tmp_path)
    with pytest.raises(TurnRecordError, match="no persisted delta"):
        append_turn(target, 1, delta_summary="   ")
    with pytest.raises(TurnRecordError, match="no persisted delta"):
        append_turn(target, 1, delta_summary="")
    assert not target.records_path.exists()


def test_refresh_validation_reports_missing_invalid_and_validated(tmp_path: Path) -> None:
    target = store(tmp_path)
    assert refresh_validation(target.run_root) == {
        "status": "missing",
        "record_count": 0,
        "last_turn_index": None,
    }
    append_turn(target, 1)
    verdict = refresh_validation(target.run_root)
    assert verdict == {"status": "validated", "record_count": 1, "last_turn_index": 1}
    receipt = json.loads(target.receipt_path.read_text(encoding="utf-8"))
    assert receipt["state"] == "validated"
    assert receipt["record_count"] == 1
    assert receipt["last_turn_index"] == 1
    assert receipt["schema"] == 1
    assert receipt["validated_at"]
    target.records_path.write_text("{broken\n", encoding="utf-8")
    verdict = refresh_validation(target.run_root)
    assert verdict["status"] == "invalid"
    assert verdict["reason"]
    receipt = json.loads(target.receipt_path.read_text(encoding="utf-8"))
    assert receipt["state"] == "invalid"
