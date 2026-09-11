"""Turn-record self-heal: baseline reconstruction from the event log (issue #529).

The issue's scenarios, named after them: a deleted record file with an intact
alignment event log heals into a reconstructed baseline (degraded, never
silently pristine); empty/corrupt event logs and contradictory histories
still fail closed exactly as #497/#509 pinned them; and the reconstructed
marker is enforced in the schema so a repaired record can never masquerade
as an authored one.

The alignment graph is fixture ground truth here and read-only ground truth
in production: reconstruction opens its database read-only and never writes
to it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from research_tree.alignment_graph import AlignmentGraphStore
from research_tree.alignment_turn_record import (
    AlignmentTurnRecord,
    AlignmentTurnRecordStore,
    ContinuityGateError,
    TurnRecordError,
    refresh_validation,
)
from research_tree.turn_contract import RESPONSE_CLASS_GENERATION

RUN_ROOT_PARTS = (".research-tree", "projects", "topic-1", "runs", "run-1")


def run_root(tmp_path: Path) -> Path:
    root = tmp_path.joinpath(*RUN_ROOT_PARTS)
    root.mkdir(parents=True, exist_ok=True)
    return root


def seeded_graph(tmp_path: Path, *, turns: int = 3, traces: bool = False) -> tuple[Path, AlignmentGraphStore]:
    """Seed the run-shaped alignment graph with ``turns`` response events."""
    database = tmp_path.joinpath(*RUN_ROOT_PARTS) / "alignment" / "alignment.db"
    graph = AlignmentGraphStore(database)
    graph.initialize("run-1")
    graph.merge(
        {
            "nodes": [
                {
                    "id": "scope-backend",
                    "type": "unknown",
                    "statement": "The backend scope is the named consequential gap.",
                    "status": "candidate",
                    "impact": 5,
                    "human_only": True,
                    "confidence": "low",
                    "source": "agent",
                }
            ]
        }
    )
    for turn in range(1, turns + 1):
        outcome = "answered" if turn == 1 else ("changed" if turn == 2 else "unchanged")
        kwargs: dict[str, object] = {"user_move": RESPONSE_CLASS_GENERATION}
        if traces and turn == 1:
            kwargs["traces"] = [{"type": "option-set", "payload": {"options": ["postgres", "sqlite"]}}]
        graph.record("scope-backend", outcome, f"fp-{turn}", **kwargs)  # type: ignore[arg-type]
    return database, graph


def seeded_store(tmp_path: Path, turns: int) -> AlignmentTurnRecordStore:
    store = AlignmentTurnRecordStore(tmp_path.joinpath(*RUN_ROOT_PARTS))
    for turn in range(1, turns + 1):
        store.append(
            turn_index=turn,
            mirror=f"mirror {turn}",
            gap=f"gap {turn}",
            delta_summary=f"delta {turn}",
            user_move=RESPONSE_CLASS_GENERATION,
        )
    return store


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Scenario: a deleted record file with an intact event log heals (degraded)
# ---------------------------------------------------------------------------


def test_deleted_record_file_with_intact_event_log_proceeds_with_reconstructed_marker(tmp_path: Path) -> None:
    seeded_graph(tmp_path, turns=2, traces=True)
    target = seeded_store(tmp_path, turns=2)
    target.records_path.unlink()

    verdict = target.check_continuity(3)

    assert verdict["status"] == "allowed"
    assert verdict["degraded"] is True
    assert verdict["recovery"] == {"turn_index": 2, "source": "alignment_event_log"}
    grounding = verdict["grounding"]
    assert grounding["turn_index"] == 2
    assert grounding["reconstructed"] is True
    assert "scope-backend" in grounding["mirror"]
    # The baseline is grounded in the event delta, not fabricated content.
    assert "scope-backend" in grounding["gap"]
    assert grounding["delta"]["nodes"] == ["scope-backend"]
    assert grounding["user_move"] == RESPONSE_CLASS_GENERATION
    # The recovery record is persisted, marked, and counted.
    assert verdict["record_count"] == 1
    lines = target.records_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    persisted = json.loads(lines[0])
    assert persisted["reconstructed"] is True
    assert persisted["turn_index"] == 2
    assert persisted["traces"] == [{"type": "option-set", "payload": {"options": ["postgres", "sqlite"]}}]


def test_degraded_receipt_reports_the_reconstructed_baseline(tmp_path: Path) -> None:
    seeded_graph(tmp_path, turns=2)
    target = seeded_store(tmp_path, turns=2)
    target.records_path.unlink()
    target.check_continuity(3)

    verdict = refresh_validation(target.run_root)
    assert verdict["degraded"] is True
    assert verdict["reconstructed_count"] == 1
    receipt = json.loads(target.receipt_path.read_text(encoding="utf-8"))
    assert receipt["degraded"] is True
    assert receipt["reconstructed_count"] == 1
    assert receipt["state"] == "validated"


def test_later_turns_stay_visibly_degraded_after_the_heal(tmp_path: Path) -> None:
    seeded_graph(tmp_path, turns=2)
    target = seeded_store(tmp_path, turns=2)
    target.records_path.unlink()
    target.check_continuity(3)

    verdict = target.check_continuity(3)
    assert verdict["status"] == "allowed"
    assert verdict["degraded"] is True
    assert verdict["grounding"]["reconstructed"] is True
    assert "recovery" not in verdict  # no new heal happened; the marker persists

    # Continuity continues: the next authored turn appends normally.
    record = target.append(
        turn_index=3,
        mirror="mirror 3",
        gap="gap 3",
        delta_summary="delta 3",
        user_move=RESPONSE_CLASS_GENERATION,
    )
    assert record.reconstructed is False
    assert "reconstructed" not in record.to_dict()
    assert target.latest() is not None and target.latest().reconstructed is False  # type: ignore[union-attr]


def test_reconstruction_never_writes_the_alignment_graph(tmp_path: Path) -> None:
    database, _graph = seeded_graph(tmp_path, turns=2)
    target = seeded_store(tmp_path, turns=2)
    target.records_path.unlink()
    before = digest(database)

    target.check_continuity(3)

    assert digest(database) == before


# ---------------------------------------------------------------------------
# Scenario: a single missing index with subsequent events present heals
# ---------------------------------------------------------------------------


def test_single_missing_index_with_subsequent_events_heals_from_the_log(tmp_path: Path) -> None:
    seeded_graph(tmp_path, turns=3)
    target = seeded_store(tmp_path, turns=2)

    verdict = target.check_continuity(4)

    assert verdict["status"] == "allowed"
    assert verdict["degraded"] is True
    assert verdict["recovery"] == {"turn_index": 3, "source": "alignment_event_log"}
    assert verdict["grounding"]["turn_index"] == 3
    assert verdict["grounding"]["reconstructed"] is True
    lines = target.records_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[2])["reconstructed"] is True
    assert [record.turn_index for record in target.records()] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Scenario: empty/corrupt event log and contradictory histories stay fail-closed
# ---------------------------------------------------------------------------


def test_empty_event_log_blocks_unchanged(tmp_path: Path) -> None:
    seeded_graph(tmp_path, turns=0)
    target = seeded_store(tmp_path, turns=2)
    target.records_path.unlink()

    with pytest.raises(ContinuityGateError, match="missing_turn_record"):
        target.check_continuity(3)
    assert not target.records_path.exists()


def test_missing_event_log_blocks_unchanged(tmp_path: Path) -> None:
    target = seeded_store(tmp_path, turns=2)
    target.records_path.unlink()

    with pytest.raises(ContinuityGateError, match="missing_turn_record"):
        target.check_continuity(3)


def test_corrupted_event_log_blocks(tmp_path: Path) -> None:
    database, _graph = seeded_graph(tmp_path, turns=2)
    target = seeded_store(tmp_path, turns=2)
    target.records_path.unlink()
    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "UPDATE events SET details_json='{not json at all}' WHERE event_type='response_recorded' "
            "AND sequence=(SELECT MAX(sequence) FROM events)"
        )
    connection.close()

    with pytest.raises(ContinuityGateError, match="missing_turn_record"):
        target.check_continuity(3)
    assert not target.records_path.exists()


def test_event_log_behind_the_record_file_fails_closed(tmp_path: Path) -> None:
    seeded_graph(tmp_path, turns=1)
    target = seeded_store(tmp_path, turns=2)

    with pytest.raises(ContinuityGateError, match="stale_turn_record"):
        target.check_continuity(4)
    assert len(target.records_path.read_text(encoding="utf-8").splitlines()) == 2


def test_event_log_short_of_the_expected_turn_fails_closed(tmp_path: Path) -> None:
    seeded_graph(tmp_path, turns=1)
    target = seeded_store(tmp_path, turns=2)
    target.records_path.unlink()

    with pytest.raises(ContinuityGateError, match="missing_turn_record"):
        target.check_continuity(3)
    assert not target.records_path.exists()


def test_gapped_event_turn_axis_fails_closed(tmp_path: Path) -> None:
    database, _graph = seeded_graph(tmp_path, turns=2)
    target = seeded_store(tmp_path, turns=2)
    target.records_path.unlink()
    connection = sqlite3.connect(database)
    with connection:
        row = connection.execute(
            "SELECT state_json FROM events WHERE event_type='response_recorded' ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        state = json.loads(row[0])
        state["controller"]["turn"] = 5
        connection.execute(
            "UPDATE events SET state_json=? WHERE event_type='response_recorded' "
            "AND sequence=(SELECT MAX(sequence) FROM events)",
            (json.dumps(state),),
        )
    connection.close()

    with pytest.raises(ContinuityGateError, match="missing_turn_record"):
        target.check_continuity(3)


def test_corrupt_record_file_does_not_heal(tmp_path: Path) -> None:
    seeded_graph(tmp_path, turns=2)
    target = seeded_store(tmp_path, turns=2)
    target.records_path.write_text("{broken\n", encoding="utf-8")

    with pytest.raises(ContinuityGateError, match="invalid_turn_record"):
        target.check_continuity(2)
    assert target.records_path.read_text(encoding="utf-8") == "{broken\n"


# ---------------------------------------------------------------------------
# Scenario: the reconstructed marker is enforced in the schema
# ---------------------------------------------------------------------------


def test_marker_round_trips_and_rejects_anything_but_true() -> None:
    payload = {
        "schema": 2,
        "turn_index": 1,
        "recorded_at": "2026-09-12T00:00:00+00:00",
        "mirror": "mirror",
        "gap": "gap",
        "delta": {"summary": "delta", "nodes": []},
        "user_move": RESPONSE_CLASS_GENERATION,
        "contract_terms": None,
        "traces": [],
        "reconstructed": True,
    }
    record = AlignmentTurnRecord.from_dict(payload)
    assert record.reconstructed is True
    assert AlignmentTurnRecord.from_dict(record.to_dict()).reconstructed is True

    for forged in (False, "true", 1, None):
        with pytest.raises(TurnRecordError, match="reconstructed"):
            AlignmentTurnRecord.from_dict({**payload, "reconstructed": forged})


def test_authored_records_never_carry_the_marker(tmp_path: Path) -> None:
    target = AlignmentTurnRecordStore(run_root(tmp_path))
    record = target.append(
        turn_index=1,
        mirror="mirror",
        gap="gap",
        delta_summary="delta",
        user_move=RESPONSE_CLASS_GENERATION,
    )
    assert record.reconstructed is False
    persisted = json.loads(target.records_path.read_text(encoding="utf-8").splitlines()[0])
    assert "reconstructed" not in persisted


def test_reconstructed_records_have_no_contract_terms_and_shape(tmp_path: Path) -> None:
    seeded_graph(tmp_path, turns=2)
    target = seeded_store(tmp_path, turns=2)
    target.records_path.unlink()
    target.check_continuity(3)

    latest = target.latest()
    assert latest is not None and latest.reconstructed is True  # type: ignore[union-attr]
    assert latest.contract_terms is None  # type: ignore[union-attr]
    assert latest.turn_shape is None  # type: ignore[union-attr]
    # A terms-less latest record keeps the #490 policy seam fail-open.
    verdict = refresh_validation(target.run_root)
    assert verdict["status"] == "validated"
