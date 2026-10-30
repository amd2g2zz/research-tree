"""Two-option research re-entry protocol in the lifecycle hook (issue #492).

During the research phase the runtime accepts exactly two protocol paths —
reopen alignment or supplemental evidence — plus status echo; every other
prompt (chatty drift, bare interruptions that pick no path) is refused.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_tree.lifecycle_hook import (
    RUN_PHASES,
    observe,
    resolve_research_reentry,
)

RESEARCH_PHASE_ENV = "RESEARCH_TREE_RUN_PHASE"


def project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "packages").mkdir()
    (tmp_path / "skill-src").mkdir()
    return tmp_path


def project_run(root: Path, *, phase: str | None = None) -> None:
    manifest = root / ".research-tree" / "projects" / "topic-1" / "runs" / "run-1" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    document = '{"project_id":"topic-1","run_id":"run-1"}'
    if phase is not None:
        document = json.dumps({"project_id": "topic-1", "run_id": "run-1", "phase": phase})
    manifest.write_text(document + "\n", encoding="utf-8")


def submit(root: Path, prompt: str, **observe_kwargs: object) -> dict[str, object]:
    payload = {
        "cwd": str(root),
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
    }
    if observe_kwargs.pop("with_run", True):
        payload["project_id"] = "topic-1"
        payload["run_id"] = "run-1"
    return observe(
        payload,
        host="pi",
        event="UserPromptSubmit",
        project_root=root,
        process_cwd=root,
        **observe_kwargs,
    )


@pytest.fixture(autouse=True)
def clean_phase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RESEARCH_PHASE_ENV, raising=False)


def test_run_phases_mirror_the_run_discriminator() -> None:
    assert RUN_PHASES == {"intake", "alignment", "compiled", "research", "validation", "delivery"}


@pytest.mark.parametrize(
    "prompt",
    [
        "stop — let's realign the strategy with me first",
        "re-align with my confirmation before going further",
        "I want to change the strategy for this research",
        "reopen alignment",
        "back to the drawing board on the scope",
        "recompile with the revised goals",
        "let's revise the goals before continuing",
        "重新对齐一下再继续",
    ],
)
def test_interruptions_picking_realign_resolve_to_reopen_alignment(prompt: str) -> None:
    assert resolve_research_reentry(prompt)["path"] == "reopen_alignment"


@pytest.mark.parametrize(
    "prompt",
    [
        "fyi, here's a new source on the mechanism",
        "adding additional evidence for the open frontier",
        "here's a paper that covers the second track",
        "supplemental data from my own experiment",
        "补充一份新证据",
    ],
)
def test_interruptions_supplying_material_resolve_to_supplemental_evidence(prompt: str) -> None:
    assert resolve_research_reentry(prompt)["path"] == "supplemental_evidence"


@pytest.mark.parametrize(
    "prompt",
    [
        "status?",
        "what's the current status",
        "where are we now",
        "progress update?",
        "进度如何",
    ],
)
def test_status_queries_resolve_to_status_echo(prompt: str) -> None:
    assert resolve_research_reentry(prompt)["path"] == "status_echo"


@pytest.mark.parametrize(
    "prompt",
    [
        "btw what do you think about coffee?",
        "haha nice one",
        "tell me a joke while you're at it",
    ],
)
def test_chatty_conversational_drift_is_refused(prompt: str) -> None:
    resolution = resolve_research_reentry(prompt)
    assert resolution["path"] == "refused"
    assert resolution["code"] == "research_reentry_refused"


@pytest.mark.parametrize("prompt", ["stop", "wait!", "pause.", "cancel that"])
def test_bare_interruptions_that_pick_no_path_are_refused(prompt: str) -> None:
    resolution = resolve_research_reentry(prompt)
    assert resolution["path"] == "refused"
    assert resolution["code"] == "research_reentry_refused"


def test_reopen_intent_outranks_a_status_question() -> None:
    assert resolve_research_reentry("status? also I want to realign the strategy")["path"] == ("reopen_alignment")
