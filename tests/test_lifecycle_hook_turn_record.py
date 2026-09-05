"""Lifecycle-hook refresh and validation of the alignment turn record (#497).

UserPromptSubmit and PostToolUse refresh and validate the turn-record file
so compaction or long sessions cannot silently orphan it, then surface the
verdict. The hook stays fail-open: it never blocks the host session, and the
#503 research re-entry protocol is untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_tree.alignment_turn_record import (
    AlignmentTurnRecordStore,
    ContinuityGateError,
)
from research_tree.lifecycle_hook import observe
from research_tree.turn_contract import RESPONSE_CLASS_GENERATION

RUN_ROOT_PARTS = (".research-tree", "projects", "topic-1", "runs", "run-1")
RESEARCH_PHASE_ENV = "RESEARCH_TREE_RUN_PHASE"


def project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "packages").mkdir()
    (tmp_path / "skill-src").mkdir()
    return tmp_path


def project_run(root: Path, *, phase: str | None = None) -> Path:
    run_root = root.joinpath(*RUN_ROOT_PARTS)
    manifest = run_root / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, str] = {"project_id": "topic-1", "run_id": "run-1"}
    if phase is not None:
        document["phase"] = phase
    manifest.write_text(json.dumps(document) + "\n", encoding="utf-8")
    return run_root


def seeded_store(run_root: Path, turns: int = 2) -> AlignmentTurnRecordStore:
    store = AlignmentTurnRecordStore(run_root)
    for turn in range(1, turns + 1):
        store.append(
            turn_index=turn,
            mirror=f"mirror {turn}",
            gap=f"gap {turn}",
            delta_summary=f"delta {turn}",
            user_move=RESPONSE_CLASS_GENERATION,
        )
    return store


def submit(root: Path, prompt: str, **observe_kwargs: object) -> dict[str, object]:
    payload = {
        "cwd": str(root),
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
        "project_id": "topic-1",
        "run_id": "run-1",
    }
    return observe(
        payload,
        host="codex",
        event="UserPromptSubmit",
        project_root=root,
        process_cwd=root,
        **observe_kwargs,
    )


def post_tool_use(root: Path, **observe_kwargs: object) -> dict[str, object]:
    payload = {
        "cwd": str(root),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_response": {"filePath": "notes.md"},
        "project_id": "topic-1",
        "run_id": "run-1",
    }
    return observe(
        payload,
        host="claude",
        event="PostToolUse",
        project_root=root,
        process_cwd=root,
        **observe_kwargs,
    )


@pytest.fixture(autouse=True)
def clean_phase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RESEARCH_PHASE_ENV, raising=False)


def test_prompt_submit_validates_the_record_file_and_writes_a_receipt(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root, phase="alignment")
    seeded_store(run_root, turns=2)

    result = submit(root, "the backend scope question, again")

    assert result["status"] == "recorded"
    verdict = result["alignment_turn_record"]
    assert verdict == {"status": "validated", "record_count": 2, "last_turn_index": 2}
    record = json.loads((root / str(result["path"])).read_text(encoding="utf-8"))
    assert record["alignment_turn_record"] == verdict
    receipt_path = run_root / "alignment" / "turn-records.state.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["state"] == "validated"
    assert receipt["record_count"] == 2
    assert receipt["last_turn_index"] == 2


def test_prompt_submit_reads_the_phase_from_the_manifest(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root, phase="alignment")
    seeded_store(run_root)

    result = submit(root, "next exchange")

    assert result["alignment_turn_record"]["status"] == "validated"


def test_missing_record_file_reports_missing_but_stays_recorded(tmp_path: Path) -> None:
    root = project(tmp_path)
    project_run(root, phase="alignment")

    result = submit(root, "let us start aligning")

    assert result["status"] == "recorded"
    assert result["alignment_turn_record"] == {
        "status": "missing",
        "record_count": 0,
        "last_turn_index": None,
    }


def test_corrupt_record_file_reports_invalid_with_reason(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root, phase="alignment")
    store = seeded_store(run_root, turns=1)
    store.records_path.write_text(store.records_path.read_text(encoding="utf-8") + "{broken\n", encoding="utf-8")

    result = submit(root, "next exchange")

    verdict = result["alignment_turn_record"]
    assert verdict["status"] == "invalid"
    assert verdict["reason"]


def test_post_tool_use_refreshes_and_validates_the_record_file(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root, phase="alignment")
    seeded_store(run_root, turns=3)

    result = post_tool_use(root)

    assert result["status"] == "recorded"
    assert result["alignment_turn_record"] == {
        "status": "validated",
        "record_count": 3,
        "last_turn_index": 3,
    }
    record = json.loads((root / str(result["path"])).read_text(encoding="utf-8"))
    assert record["alignment_turn_record"] == result["alignment_turn_record"]


def test_after_hook_refresh_continuity_holds_and_a_deleted_record_blocks(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root, phase="alignment")
    store = seeded_store(run_root, turns=2)

    # Compaction simulation: the hook refreshes the file; continuity holds.
    result = submit(root, "the third exchange")
    assert result["alignment_turn_record"]["status"] == "validated"
    verdict = store.check_continuity(3)
    assert verdict["status"] == "allowed"
    assert verdict["grounding"]["mirror"] == "mirror 2"

    # The record file is deleted (orphaned): fail-closed block.
    store.records_path.unlink()
    result = submit(root, "the third exchange, again")
    assert result["alignment_turn_record"]["status"] == "missing"
    with pytest.raises(ContinuityGateError, match="missing_turn_record"):
        store.check_continuity(3)


def test_reentry_protocol_is_untouched_when_the_record_file_is_present(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root, phase="research")
    seeded_store(run_root)

    result = submit(root, "stop — let's realign the strategy first")

    assert result["reentry"]["path"] == "reopen_alignment"
    assert result["alignment_turn_record"]["status"] == "validated"
    run_events = run_root / "events"
    routed = [json.loads(item.read_text(encoding="utf-8")) for item in run_events.glob("*.json")]
    assert len(routed) == 1
    assert routed[0]["route"] == "research_reentry"


def test_no_verdict_without_an_active_run(tmp_path: Path) -> None:
    root = project(tmp_path)
    # No run manifest exists, so the prompt resolves to no active run.
    result = submit(root, "hello there")

    assert result["status"] == "recorded"
    assert "alignment_turn_record" not in result


def test_no_verdict_outside_alignment_without_a_record_file(tmp_path: Path) -> None:
    root = project(tmp_path)
    project_run(root, phase="research")

    result = submit(root, "fyi, here's a new source on the mechanism")

    assert result["status"] == "recorded"
    assert "alignment_turn_record" not in result


def test_refresh_never_creates_the_alignment_directory(tmp_path: Path) -> None:
    root = project(tmp_path)
    run_root = project_run(root, phase="alignment")

    result = submit(root, "opening exchange")

    assert result["alignment_turn_record"]["status"] == "missing"
    assert not (run_root / "alignment").exists()
