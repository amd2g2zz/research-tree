"""Issue #453 defect 2: UserPromptSubmit classification signals are captured."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_tree.lifecycle_hook import (
    HOST_EVENTS,
    LifecycleHookError,
    classify_prompt_signal,
    observe,
)


def project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "packages").mkdir()
    (tmp_path / "skill-src").mkdir()
    return tmp_path


def project_run(root: Path) -> None:
    manifest = root / ".research-tree" / "projects" / "topic-1" / "runs" / "run-1" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"project_id":"topic-1","run_id":"run-1"}\n', encoding="utf-8")


def _submit(root: Path, prompt: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "cwd": str(root),
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
        "project_id": "topic-1",
        "run_id": "run-1",
        **extra,
    }
    return observe(payload, host="claude", event="UserPromptSubmit", project_root=root, process_cwd=root)


class TestClassifierRules:
    def test_correction_high_confidence(self) -> None:
        signal = classify_prompt_signal("No, use pytest not unittest")
        assert signal["category"] == "correction"
        assert signal["confidence"] == "high"
        assert signal["rule"] == "explicit_no"

    def test_correction_wrong_statement(self) -> None:
        signal = classify_prompt_signal("that's wrong, the API paginates")
        assert signal == {"category": "correction", "confidence": "high", "rule": "explicit_wrong"}

    def test_actually_prefix_is_medium_confidence(self) -> None:
        # Review calibration: a tentative "actually" add-on is not a clear
        # overturn of a prior conclusion, so it must not ride at high.
        signal = classify_prompt_signal("Actually, can you also add monitoring while you are at it?")
        assert signal == {"category": "correction", "confidence": "medium", "rule": "actually_prefix"}

    def test_continuation_semantics_downgrades_corrections(self) -> None:
        # Review calibration: prompts that pair correction vocabulary with an
        # explicit continue instruction are not overturns of the plan.
        signal = classify_prompt_signal("no. 5 files remain, keep going")
        assert signal == {"category": "correction", "confidence": "low", "rule": "explicit_no+continuation"}
        signal = classify_prompt_signal("the path in the docs is wrong but continue with the plan")
        assert signal == {"category": "correction", "confidence": "low", "rule": "explicit_wrong+continuation"}

    def test_genuine_overturn_stays_high_even_with_continue_words_elsewhere(self) -> None:
        # "Stop" semantics still outrank; and a correction without continuation
        # semantics must stay high.
        assert classify_prompt_signal("that's wrong, the API paginates")["confidence"] == "high"

    def test_medium_confidence_correction_is_not_fed_to_the_run(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        project_run(root)

        result = _submit(root, "Actually, can you also add monitoring while you are at it?")

        assert result["signal"]["category"] == "correction"
        assert result["signal"]["confidence"] == "medium"
        assert "run_signal_path" not in result

    def test_interruption_bare_stop(self) -> None:  # noqa: PLR6301
        assert classify_prompt_signal("stop") == {
            "category": "interruption",
            "confidence": "high",
            "rule": "explicit_stop",
        }

    def test_interruption_cancel_command(self) -> None:  # noqa: PLR6301
        assert classify_prompt_signal("cancel that search") == {
            "category": "interruption",
            "confidence": "high",
            "rule": "stop_command",
        }

    def test_insight_volunteered_observation(self) -> None:
        signal = classify_prompt_signal("I noticed the cache rebuilds on every run")
        assert signal == {"category": "insight", "confidence": "low", "rule": "volunteered_observation"}

    def test_answer_direct_affirmative(self) -> None:
        signal = classify_prompt_signal("yes, proceed with option A")
        assert signal == {"category": "answer", "confidence": "low", "rule": "direct_affirmative"}

    def test_neutral_ordinary_prompt(self) -> None:
        assert classify_prompt_signal("please continue with the implementation") == {
            "category": "neutral",
            "confidence": "low",
            "rule": "default",
        }

    def test_empty_prompt_is_neutral(self) -> None:  # noqa: PLR6301
        assert classify_prompt_signal("")["category"] == "neutral"

    def test_case_insensitive(self) -> None:  # noqa: PLR6301
        assert classify_prompt_signal("STOP")["rule"] == "explicit_stop"

    def test_rules_table_is_wellformed(self) -> None:  # noqa: PLR6301
        from research_tree.lifecycle_hook import PROMPT_SIGNAL_CATEGORIES, PROMPT_SIGNAL_RULES

        rules = [rule for _, rule, _, _ in PROMPT_SIGNAL_RULES]
        assert len(rules) == len(set(rules)), "rule identifiers must be unique"
        assert set(PROMPT_SIGNAL_CATEGORIES) == {"correction", "interruption", "insight", "answer", "neutral"}
        for category, _, _, confidence in PROMPT_SIGNAL_RULES:
            assert category in PROMPT_SIGNAL_CATEGORIES
            assert confidence in {"high", "medium", "low"}
        # Every category except neutral has at least one rule.
        assert {category for category, _, _, _ in PROMPT_SIGNAL_RULES} == set(PROMPT_SIGNAL_CATEGORIES) - {"neutral"}

    def test_first_matching_rule_wins(self) -> None:  # noqa: PLR6301
        # Interruption outranks correction signals in the same prompt.
        assert classify_prompt_signal("stop, that is wrong")["category"] == "interruption"


class TestSignalRecording:
    def test_prompt_submit_records_queryable_signal(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        project_run(root)

        result = _submit(root, "No, use pytest not unittest", session_id="session-7")

        assert result["status"] == "recorded"
        assert result["event"] == "UserPromptSubmit"
        assert result["signal"] == {"category": "correction", "confidence": "high", "rule": "explicit_no"}
        signals = root / ".research-tree-debug" / "signals"
        files = list(signals.glob("*.json"))
        assert len(files) == 1
        record = json.loads(files[0].read_text(encoding="utf-8"))
        assert record["schema"] == 1
        assert record["source"] == "research-tree-lifecycle-hook"
        assert record["host"] == "claude"
        assert record["event"] == "UserPromptSubmit"
        assert record["category"] == "correction"
        assert record["confidence"] == "high"
        assert record["rule"] == "explicit_no"
        assert record["session_id"] == "session-7"
        assert record["prompt_length"] == len("No, use pytest not unittest")
        # The raw user prompt is never persisted.
        assert "pytest" not in json.dumps(record)

    def test_signals_are_independent_append_only_records(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        project_run(root)

        first = _submit(root, "I noticed a duplicated cache entry")
        second = _submit(root, "yes, proceed")

        assert first["status"] == "recorded"
        assert second["status"] == "recorded"
        assert first["path"] != second["path"]
        assert len(list((root / ".research-tree-debug" / "signals").glob("*.json"))) == 2

    def test_high_confidence_correction_feeds_run_scoped_correction_path(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        project_run(root)

        result = _submit(root, "No, the launcher must use system python")

        run_signal_path = result["run_signal_path"]
        feed = json.loads((root / run_signal_path).read_text(encoding="utf-8"))
        assert feed["category"] == "correction"
        assert feed["confidence"] == "high"
        assert feed["route"] == "apply_correction"
        assert feed["project_id"] == "topic-1"
        assert feed["run_id"] == "run-1"
        assert ".research-tree/projects/topic-1/runs/run-1/events/" in run_signal_path

    def test_correction_without_run_context_only_records_the_signal(self, tmp_path: Path) -> None:
        root = project(tmp_path)  # no active run manifest

        result = _submit(root, "No, the launcher must use system python")

        assert result["status"] == "recorded"
        assert "run_signal_path" not in result
        assert len(list((root / ".research-tree-debug" / "signals").glob("*.json"))) == 1
        assert not (root / ".research-tree" / "projects").exists()

    def test_signals_directory_is_capped_at_200_records(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        project_run(root)
        signals = root / ".research-tree-debug" / "signals"
        signals.mkdir(parents=True)
        for index in range(200):
            name = f"20200101T000000000000Z-{index:016x}.json"
            (signals / name).write_text('{"schema":1}\n', encoding="utf-8")

        result = _submit(root, "No, use pytest not unittest")

        assert result["status"] == "recorded"
        remaining = sorted(path.name for path in signals.glob("*.json"))
        assert len(remaining) == 200, "cap must retain the newest 200 records"
        assert "20200101T000000000000Z-0000000000000000.json" not in remaining, "oldest record must be evicted"
        assert "20200101T000000000000Z-00000000000000c7.json" in remaining, "newest legacy record must be retained"
        remaining_sorted = sorted(remaining)
        assert remaining_sorted[-1].startswith("20"), "the fresh record must survive the cap"

    def test_signals_directory_below_cap_is_left_untouched(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        project_run(root)
        signals = root / ".research-tree-debug" / "signals"
        signals.mkdir(parents=True)
        for index in range(3):
            (signals / f"20200101T000000000000Z-{index:016x}.json").write_text("{}", encoding="utf-8")

        _submit(root, "yes, proceed")

        assert len(list(signals.glob("*.json"))) == 4

    def test_low_confidence_correction_is_not_fed_to_the_run(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        project_run(root)

        result = _submit(root, "use the typed client instead of the raw one")

        assert result["signal"]["category"] == "correction"
        assert result["signal"]["confidence"] == "low"
        assert "run_signal_path" not in result
        run_events = root / ".research-tree" / "projects" / "topic-1" / "runs" / "run-1" / "events"
        assert not run_events.exists() or not list(run_events.glob("*.json"))

    def test_empty_prompt_is_skipped(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        result = _submit(root, "   ")
        assert result == {"status": "skipped_empty_prompt", "host": "claude", "event": "UserPromptSubmit"}
        assert not (root / ".research-tree-debug").exists()

    def test_missing_prompt_is_skipped(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        result = observe(
            {"cwd": str(root), "hook_event_name": "UserPromptSubmit", "project_id": "topic-1", "run_id": "run-1"},
            host="claude",
            event="UserPromptSubmit",
            project_root=root,
            process_cwd=root,
        )
        assert result["status"] == "skipped_empty_prompt"

    def test_outside_checkout_fails_open_through_main(self, capsys: pytest.CaptureFixture[str]) -> None:
        from research_tree.lifecycle_hook import main

        # No payload on stdin and no Research Tree checkout at cwd: main must
        # still exit 0 and print exactly one labeled host response.
        exit_code = main(["--host", "claude", "--event", "UserPromptSubmit"])

        assert exit_code == 0
        output = capsys.readouterr().out
        assert output.count("<rt:event ") == 1
        assert output.rstrip().endswith("</rt:event>")

    def test_event_registered_for_claude_and_codex_only(self) -> None:  # noqa: PLR6301
        assert "UserPromptSubmit" in HOST_EVENTS["claude"]
        assert "UserPromptSubmit" in HOST_EVENTS["codex"]
        assert "UserPromptSubmit" not in HOST_EVENTS["hermes"]

    def test_unsupported_event_still_rejected(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        with pytest.raises(LifecycleHookError, match="unsupported claude hook event"):
            observe(
                {"cwd": str(root), "hook_event_name": "Nonsense", "prompt": "hello"},
                host="claude",
                event="Nonsense",
                project_root=root,
                process_cwd=root,
            )
