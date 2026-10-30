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
        host="pi",
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
        host="pi",
        event="PostToolUse",
        project_root=root,
        process_cwd=root,
        **observe_kwargs,
    )


@pytest.fixture(autouse=True)
def clean_phase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RESEARCH_PHASE_ENV, raising=False)
