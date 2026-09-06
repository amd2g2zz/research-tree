"""Turn-shape gate tests (issue #493).

One turn-record, three measured composition dimensions (length,
decision-count, question-count — transformation ratio is the #499
placeholder), checked mechanically against the round discipline; verdicts are
flagged on the record, never silent.
"""

from __future__ import annotations

import json

import pytest

from research_tree.alignment_turn_record import (
    MAX_DECISION_POINTS,
    MAX_QUESTIONS,
    MAX_TURN_LENGTH,
    SCHEMA_VERSION,
    AlignmentTurnRecordStore,
    TurnRecordError,
    measure_turn_shape,
    refresh_validation,
)


def store(tmp_path):
    return AlignmentTurnRecordStore(tmp_path / "run")


def append_basic(s, index: int, **shape):
    return s.append(
        turn_index=index,
        mirror="I understand the goal.",
        gap="The scale is unnamed.",
        delta_summary="Scale anchored to a concrete deliverable.",
        user_move="answer",
        turn_shape=shape or None,
    )


def test_compliant_turn_shape_is_recorded(tmp_path) -> None:
    s = store(tmp_path)
    record = append_basic(
        s,
        1,
        **measure_turn_shape("Here is my reading and one question for you.", decision_count=1, question_count=1),
    )
    assert record.turn_shape is not None
    assert record.turn_shape["verdict"] == "compliant"
    assert record.turn_shape["violations"] == []
    assert record.turn_shape["length"] == len("Here is my reading and one question for you.")
    assert record.to_dict()["schema"] == SCHEMA_VERSION == 2
    assert s.latest().turn_shape["verdict"] == "compliant"


def test_overlong_turn_is_flagged_with_named_dimension(tmp_path) -> None:
    s = store(tmp_path)
    shape = measure_turn_shape("x" * (MAX_TURN_LENGTH + 1), decision_count=1, question_count=1)
    record = append_basic(s, 1, **shape)
    assert record.turn_shape["verdict"] == "violated"
    assert any("length" in v for v in record.turn_shape["violations"])
    # Flag-not-block: the record persists and stays the continuity grounding.
    assert s.latest().turn_index == 1
    assert s.check_continuity(2)["status"] == "allowed"


def test_multiple_decision_points_are_a_mechanical_violation(tmp_path) -> None:
    s = store(tmp_path)
    shape = measure_turn_shape("Pick one of three directions.", decision_count=3, question_count=1)
    record = append_basic(s, 1, **shape)
    assert record.turn_shape["verdict"] == "violated"
    assert any("decision_count" in v for v in record.turn_shape["violations"])
    questions = measure_turn_shape("Two questions then.", decision_count=1, question_count=2)
    assert any("question_count" in v for v in questions["violations"])


def test_transformation_ratio_placeholder_is_carried(tmp_path) -> None:
    s = store(tmp_path)
    shape = measure_turn_shape(
        "Digest first.", decision_count=1, question_count=0, transformation_ratio=0.8
    )
    record = append_basic(s, 1, **shape)
    assert record.turn_shape["transformation_ratio"] == 0.8


def test_legacy_schema_one_records_still_read(tmp_path) -> None:
    s = store(tmp_path)
    legacy = {
        "schema": 1,
        "turn_index": 1,
        "recorded_at": "2026-09-05T00:00:00+00:00",
        "mirror": "Understood.",
        "gap": "Open.",
        "delta": {"summary": "Anchored.", "nodes": []},
        "user_move": "answer",
        "contract_terms": None,
        "traces": [],
    }
    s.alignment_directory.mkdir(parents=True, exist_ok=True)
    s.records_path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    records = s.records()
    assert len(records) == 1
    assert records[0].turn_shape is None
    assert s.check_continuity(2)["status"] == "allowed"


def test_turn_shape_field_mismatch_is_rejected(tmp_path) -> None:
    s = store(tmp_path)
    bad = measure_turn_shape("ok", decision_count=1, question_count=0)
    bad["unknown_field"] = 1
    with pytest.raises(TurnRecordError, match="turn_shape"):
        append_basic(s, 1, **bad)


def test_refresh_receipt_carries_last_shape_verdict(tmp_path) -> None:
    s = store(tmp_path)
    append_basic(
        s,
        1,
        **measure_turn_shape("x" * (MAX_TURN_LENGTH + 5), decision_count=1, question_count=0),
    )
    verdict = refresh_validation(s.run_root)
    assert verdict["status"] == "validated"
    assert verdict["last_turn_shape"] == "violated"


def test_measure_turn_shape_thresholds_are_named_constants() -> None:
    assert MAX_TURN_LENGTH == 1000
    assert MAX_DECISION_POINTS == 1
    assert MAX_QUESTIONS == 1
