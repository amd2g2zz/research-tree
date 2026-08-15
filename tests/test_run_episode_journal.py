from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_journal_runner_only_uses_disposable_evaluator_paths(tmp_path: Path) -> None:
    runner = load_module("run_episode_journal", ROOT / "evaluation/harness/run_episode_journal.py")
    fixtures = load_module("paired_benchmark_fixture_for_journal", ROOT / "tests/test_paired_benchmark.py")
    run_root = ROOT / ".research-tree/evaluation-runs/test-run-episode-journal" / tmp_path.name
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(fixtures.sealed_manifest()), encoding="utf-8")
    journal_dir = run_root / "journal"
    key_path = run_root / "journal.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(b"evaluator-journal-key-v1\n")

    result = runner.run(manifest_path, journal_dir, key_path, harness_revision="test-revision", abandon_started=False)

    assert result["run_id"].startswith("run-")
    assert len(result["pending_episode_ids"]) == 6
