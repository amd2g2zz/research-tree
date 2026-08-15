from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest


ROOT = Path(__file__).parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = load_module("run_sealed_episodes", ROOT / "evaluation/harness/run_sealed_episodes.py")
FIXTURES = load_module("paired_benchmark_fixture_for_execution", ROOT / "tests/test_paired_benchmark.py")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def write_fixture_host(tmp_path: Path) -> Path:
    path = tmp_path / "host_stub.py"
    path.write_text(
        "import json\n"
        "from pathlib import Path\n"
        "import sys\n"
        "output = {\n"
        " 'source_capture_set_digest': 'sha256:' + '1' * 64,\n"
        " 'transcript_digest': 'sha256:' + '2' * 64,\n"
        " 'synthetic_session_receipt_digest': 'sha256:' + '3' * 64,\n"
        " 'token_usage': {'cache_hit_input_tokens': 1, 'cache_miss_input_tokens': 2, 'output_tokens': 3},\n"
        " 'integrity': {'completion_forgery': False, 'correction_regression': False, 'source_capture_missing': False, 'unresolved_evidence': False},\n"
        "}\n"
        "Path(sys.argv[2]).write_text(json.dumps(output), encoding='utf-8')\n",
        encoding="utf-8",
    )
    return path


def prepared_manifest(tmp_path: Path) -> tuple[dict[str, object], Path, Path]:
    manifest = FIXTURES.sealed_manifest()
    run_root = ROOT / ".research-tree/evaluation-runs/test-run-sealed-episodes" / uuid4().hex
    input_dir = run_root / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    input_payload = {
        "episode_id": "opaque-task-1",
        "initial_user_message": "Please investigate the available evidence.",
        "model": "deepseek-v4-flash",
        "source_proxy_url": "http://source-broker:8081/capture",
    }
    rendered_input = json.dumps(input_payload, sort_keys=True).encode("utf-8")
    for entry in manifest["episode_plan"]:
        entry["runner_input_digest"] = digest_bytes(rendered_input)
        (input_dir / f"{entry['episode_id']}.json").write_bytes(rendered_input)
    host_stub = write_fixture_host(tmp_path)
    command = f"{sys.executable} {host_stub} {{episode_input_path}} {{episode_output_path}}"
    for cell in manifest["cells"]:
        cell["host_command"] = command
        cell["host_command_digest"] = FIXTURES.text_digest(command)
    return manifest, run_root, input_dir


def test_executor_runs_all_sealed_episodes_and_checkpoints_outputs(tmp_path: Path) -> None:
    manifest, run_root, input_dir = prepared_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    key_path = run_root / "journal.key"
    key_path.write_bytes(b"evaluator-journal-key-v1\n")

    result = RUNNER.run(
        manifest_path,
        run_root / "journal",
        key_path,
        input_dir,
        harness_revision="test-revision",
        timeout_seconds=20,
    )

    assert result["status"] == "complete"
    assert len(result["executed_episode_ids"]) == 6


def test_executor_invalidates_a_paired_group_after_host_failure(tmp_path: Path) -> None:
    manifest, run_root, input_dir = prepared_manifest(tmp_path)
    failed_command = "false {episode_input_path} {episode_output_path}"
    for cell in manifest["cells"]:
        cell["host_command"] = failed_command
        cell["host_command_digest"] = FIXTURES.text_digest(failed_command)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    key_path = run_root / "journal.key"
    key_path.write_bytes(b"evaluator-journal-key-v1\n")

    with pytest.raises(RuntimeError, match="host command failed"):
        RUNNER.run(
            manifest_path,
            run_root / "journal",
            key_path,
            input_dir,
            harness_revision="test-revision",
            timeout_seconds=20,
            episode_ids=(manifest["episode_plan"][0]["episode_id"],),
        )

    journal = RUNNER._load_module("episode_journal").EpisodeJournal(
        run_root / "journal", attestation_key=b"evaluator-journal-key-v1"
    )
    try:
        run_id = journal.initialize(manifest, harness_revision="test-revision")
        assert len(journal.pending(run_id)) == 6
    finally:
        journal.close()
