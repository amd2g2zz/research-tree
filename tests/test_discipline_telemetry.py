"""Discipline telemetry tests (issue #525) — the external, never-forgetting loop.

The hook consumes what the event stream already emits (#527 agent turn
budget violations, #514 turn-shape verdicts, #497 record compliance),
appends the unseen ones to an append-only per-run violation stream, and
escalates the sliding-window violation rate through a graduated response
ladder: receipt-only, reminder injection, forced discipline reload, block.
Observation is fail-open; only the block step is fail-closed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_tree import lifecycle_hook
from research_tree.alignment_graph import AlignmentGraphStore
from research_tree.alignment_turn_record import AlignmentTurnRecordStore
from research_tree.discipline import (
    DISCIPLINE_BLOCK,
    DISCIPLINE_BLOCK_RATE,
    DISCIPLINE_INJECTION_MAX_CHARS,
    DISCIPLINE_RELOAD,
    DISCIPLINE_RELOAD_RATE,
    DISCIPLINE_REMINDER,
    DISCIPLINE_REMINDER_RATE,
    DISCIPLINE_WINDOW_TURNS,
    RECEIPT_ONLY,
    DisciplineViolationStore,
    build_discipline_section,
    check_discipline_gate,
    resolve_discipline_response,
    sliding_window_rate,
)
from research_tree.lifecycle_hook import observe
from research_tree.turn_contract import DEFAULT_MAX_QUESTIONS_PER_TURN, RESPONSE_CLASS_GENERATION

RUN_ROOT_PARTS = (".research-tree", "projects", "topic-1", "runs", "run-1")
VIOLATIONS_RELPATH = ("discipline", "violations.jsonl")


def project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "packages").mkdir()
    (tmp_path / "skill-src").mkdir()
    return tmp_path


def project_run(root: Path) -> Path:
    run_root = root.joinpath(*RUN_ROOT_PARTS)
    manifest = run_root / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"project_id": "topic-1", "run_id": "run-1"}) + "\n", encoding="utf-8")
    return run_root


def _violation(
    turn_index: int,
    *,
    dimension: str = "questions",
    measured: int = 2,
    cap: int = 1,
    source: str = "agent_turn_budget",
) -> dict[str, object]:
    return {"turn_index": turn_index, "dimension": dimension, "measured": measured, "cap": cap, "source": source}


def post_tool_use(root: Path) -> dict[str, object]:
    payload = {
        "cwd": str(root),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_response": {"filePath": "notes.md"},
        "project_id": "topic-1",
        "run_id": "run-1",
    }
    return observe(payload, host="claude", event="PostToolUse", project_root=root, process_cwd=root)


def stop_event(root: Path) -> dict[str, object]:
    payload = {"cwd": str(root), "hook_event_name": "Stop", "project_id": "topic-1", "run_id": "run-1"}
    return observe(payload, host="claude", event="Stop", project_root=root, process_cwd=root)


# --- Scenario: the violation stream appends and persists ---------------------


def test_the_violation_stream_appends_and_persists(tmp_path: Path) -> None:
    run_root = project_run(project(tmp_path))
    store = DisciplineViolationStore(run_root)
    appended = store.append(
        [_violation(1), _violation(2, dimension="chars", measured=1500, cap=1200, source="turn_shape")]
    )
    assert len(appended) == 2
    # Append-only JSONL beside the turn record, one named record per violation.
    lines = run_root.joinpath(*VIOLATIONS_RELPATH).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert (
        first["turn_index"],
        first["dimension"],
        first["measured"],
        first["cap"],
        first["source"],
    ) == (1, "questions", 2, 1, "agent_turn_budget")
    # A fresh store reads the persisted records back.
    assert DisciplineViolationStore(run_root).records() == tuple(appended)
    # Re-appending the same emitted violations is idempotent; new ones append.
    store.append(
        [_violation(1), _violation(3, dimension="record", measured=0, cap=1, source="turn_record")]
    )
    assert len(store.records()) == 3


# --- Scenario: the sliding window counts only the last N turns ---------------


def test_the_sliding_window_counts_only_the_last_window_turns() -> None:
    assert sliding_window_rate([]) == 0.0
    # A single violation is data, not a verdict: 1/N over the full window.
    assert sliding_window_rate([_violation(3)], turns_observed=10) == 1 / DISCIPLINE_WINDOW_TURNS
    recent = [_violation(index) for index in (12, 14, 16)]
    assert sliding_window_rate(recent, turns_observed=20) == pytest.approx(0.3)
    assert sliding_window_rate(recent) == pytest.approx(0.3)
    # Records older than the window slide out as the turn axis advances.
    assert sliding_window_rate(recent + [_violation(5)], turns_observed=20) == pytest.approx(0.3)
    # The rate saturates at a full window of violations.
    burst = [_violation(20, measured=count) for count in range(20)]
    assert sliding_window_rate(burst) == 1.0


# --- Scenario: ladder thresholds trigger the right response marker -----------


def test_ladder_thresholds_trigger_the_right_response_marker_at_each_step() -> None:
    assert resolve_discipline_response(DISCIPLINE_REMINDER_RATE - 0.01) == RECEIPT_ONLY
    assert resolve_discipline_response(DISCIPLINE_REMINDER_RATE) == DISCIPLINE_REMINDER
    assert resolve_discipline_response(DISCIPLINE_RELOAD_RATE - 0.01) == DISCIPLINE_REMINDER
    assert resolve_discipline_response(DISCIPLINE_RELOAD_RATE) == DISCIPLINE_RELOAD
    assert resolve_discipline_response(DISCIPLINE_BLOCK_RATE - 0.01) == DISCIPLINE_RELOAD
    assert resolve_discipline_response(DISCIPLINE_BLOCK_RATE) == DISCIPLINE_BLOCK
    assert resolve_discipline_response(1.0) == DISCIPLINE_BLOCK
    # Below the low threshold: receipt-only, no injection entry, no gate verdict.
    section = build_discipline_section([_violation(1)])
    assert section["response"] == RECEIPT_ONLY
    assert section["rate"] == pytest.approx(1 / DISCIPLINE_WINDOW_TURNS)
    assert "injection" not in section and "gate" not in section
    # Elevated: the reminder rides the tail-injection channel as a bounded,
    # fixed-slot, single-line payload.
    section = build_discipline_section([_violation(index) for index in (1, 2)])
    assert section["response"] == DISCIPLINE_REMINDER
    assert section["rate"] == pytest.approx(DISCIPLINE_REMINDER_RATE)
    injection = section["injection"]
    assert injection["marker"] == DISCIPLINE_REMINDER and injection["slot"] == "discipline"
    assert "\n" not in injection["line"] and len(injection["line"]) <= DISCIPLINE_INJECTION_MAX_CHARS
    # Sustained high: the reload entry requests the SKILL discipline section.
    section = build_discipline_section([_violation(index) for index in range(1, 5)])
    assert section["response"] == DISCIPLINE_RELOAD
    assert "SKILL discipline section" in section["injection"]["line"]
    # Extreme sustained: the block step carries a gate verdict, not an injection.
    section = build_discipline_section([_violation(index) for index in range(1, 7)])
    assert section["response"] == DISCIPLINE_BLOCK
    assert section["gate"] == {"status": "blocked", "reason": DISCIPLINE_BLOCK}
    assert "injection" not in section


# --- Scenario: fail-open without records -------------------------------------


def test_fail_open_without_records(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root)
    # No measurements, no false violations, no receipt section, no stream file.
    assert "discipline" not in post_tool_use(root)
    assert "discipline" not in stop_event(root)
    assert not (run_root / "discipline").exists()
    assert check_discipline_gate(run_root) == {"status": "allowed", "rate": 0.0, "response": RECEIPT_ONLY}


# --- Scenario: telemetry without the module degrades to no measurements ------


def test_telemetry_without_the_module_degrades_to_no_measurements(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path)
    run_root = project_run(root)
    monkeypatch.setattr(lifecycle_hook, "_discipline", None)
    assert "discipline" not in post_tool_use(root)
    assert not (run_root / "discipline").exists()


# --- Scenario: agent turn budget violations are counted from the event stream


def test_agent_turn_budget_violations_are_counted_from_the_event_stream(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root)
    store = AlignmentGraphStore(run_root / "alignment" / "alignment.db")
    store.initialize("run-1")
    store.merge(
        {
            "nodes": [
                {
                    "id": "gap-a",
                    "type": "unknown",
                    "statement": "Requester-only dimension gap-a.",
                    "status": "candidate",
                    "impact": 5,
                    "human_only": True,
                    "confidence": "low",
                    "source": "agent",
                }
            ]
        }
    )
    decision = store.plan()
    result = store.record(decision["gap_id"], "unchanged", "fp-1", question_count=2)
    assert result["turn_budget_violations"] == [
        {"dimension": "max_questions", "limit": DEFAULT_MAX_QUESTIONS_PER_TURN, "observed": 2}
    ]
    receipt = post_tool_use(root)
    # The #527 event entry is consumed, normalized, and counted exactly once.
    stream = DisciplineViolationStore(run_root).records()
    assert [
        (record["turn_index"], record["dimension"], record["measured"], record["cap"], record["source"])
        for record in stream
    ] == [(1, "questions", 2, DEFAULT_MAX_QUESTIONS_PER_TURN, "agent_turn_budget")]
    section = receipt["discipline"]
    assert section["rate"] == pytest.approx(1 / DISCIPLINE_WINDOW_TURNS)
    assert section["response"] == RECEIPT_ONLY
    assert section["recent"][0]["source"] == "agent_turn_budget"
    # Re-observing the same event stream (PostToolUse, then Stop) never
    # double-counts; the stream remembers.
    post_tool_use(root)
    stop_event(root)
    assert len(DisciplineViolationStore(run_root).records()) == 1


# --- Scenario: turn-shape verdicts are counted from the turn record ----------


def test_turn_shape_verdicts_are_counted_from_the_turn_record(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root)
    records = AlignmentTurnRecordStore(run_root)
    records.append(
        turn_index=1,
        mirror="mirror 1",
        gap="gap 1",
        delta_summary="delta 1",
        user_move=RESPONSE_CLASS_GENERATION,
        turn_shape={
            "length": 1500,
            "decision_count": 1,
            "question_count": 1,
            "transformation_ratio": None,
            "verdict": "violated",
            "violations": ["length>1000: 1500"],
        },
    )
    post_tool_use(root)
    records.append(
        turn_index=2,
        mirror="mirror 2",
        gap="gap 2",
        delta_summary="delta 2",
        user_move=RESPONSE_CLASS_GENERATION,
        turn_shape={
            "length": 500,
            "decision_count": 2,
            "question_count": 0,
            "transformation_ratio": None,
            "verdict": "violated",
            "violations": ["decision_count>1: 2"],
        },
    )
    post_tool_use(root)
    stream = DisciplineViolationStore(run_root).records()
    assert [
        (record["turn_index"], record["dimension"], record["measured"], record["cap"], record["source"])
        for record in stream
    ] == [
        (1, "chars", 1500, 1000, "turn_shape"),
        (2, "other", 2, 1, "turn_shape"),
    ]
    # A persisted record that violates its own schema — the empty-delta turn
    # the #497 store refuses to write — is observed as a record violation.
    broken = {
        "schema": 2,
        "turn_index": 3,
        "recorded_at": "2026-09-12T00:00:00+00:00",
        "mirror": "mirror 3",
        "gap": "gap 3",
        "delta": {"summary": "", "nodes": []},
        "user_move": RESPONSE_CLASS_GENERATION,
        "contract_terms": None,
        "traces": [],
    }
    with records.records_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(broken) + "\n")
    post_tool_use(root)
    assert [record["source"] for record in DisciplineViolationStore(run_root).records()] == [
        "turn_shape",
        "turn_shape",
        "turn_record",
    ]


# --- Scenario: the block step is honored by a gate check ---------------------


def test_the_block_step_is_honored_by_a_gate_check(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root)
    store = DisciplineViolationStore(run_root)
    # Sustained high but below the block threshold: observation, not a block.
    store.append([_violation(index) for index in range(1, 6)])
    assert check_discipline_gate(run_root)["status"] == "allowed"
    # At the block threshold: the only fail-closed step.
    store.append([_violation(6)])
    verdict = check_discipline_gate(run_root)
    assert verdict["status"] == "blocked" and verdict["reason"] == DISCIPLINE_BLOCK
    # The hook receipt names the block verdict for the next-turn gate, on
    # both PostToolUse and Stop.
    assert post_tool_use(root)["discipline"]["response"] == DISCIPLINE_BLOCK
    assert stop_event(root)["discipline"]["response"] == DISCIPLINE_BLOCK
    # An unreadable stream fails open — absence of telemetry is not a block.
    run_root.joinpath(*VIOLATIONS_RELPATH).write_text("{broken\n", encoding="utf-8")
    assert check_discipline_gate(run_root)["status"] == "allowed"
