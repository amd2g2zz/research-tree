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
    resolve_discipline_response,
    sliding_window_rate,
)
from research_tree.lifecycle_hook import observe

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
    return observe(payload, host="pi", event="PostToolUse", project_root=root, process_cwd=root)


def stop_event(root: Path) -> dict[str, object]:
    payload = {"cwd": str(root), "hook_event_name": "Stop", "project_id": "topic-1", "run_id": "run-1"}
    return observe(payload, host="pi", event="Stop", project_root=root, process_cwd=root)


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
    store.append([_violation(1), _violation(3, dimension="record", measured=0, cap=1, source="turn_record")])
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
