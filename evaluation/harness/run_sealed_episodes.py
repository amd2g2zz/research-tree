"""Run sealed paired episodes through evaluator-owned host commands."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Mapping


ROOT = Path(__file__).parents[2]
RUN_ROOT = ROOT / ".research-tree" / "evaluation-runs"


def _load_module(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_research_tree_{name}", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _evaluator_path(path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(RUN_ROOT)
    except ValueError as error:
        raise ValueError(f"{label} must be under .research-tree/evaluation-runs") from error
    return resolved


def _load_mapping(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _safe_environment() -> dict[str, str]:
    environment = {"HOME": "/nonexistent", "PATH": os.environ.get("PATH", "")}
    key_file = os.environ.get("DEEPSEEK_API_KEY_FILE")
    if key_file:
        environment["DEEPSEEK_API_KEY_FILE"] = key_file
    return environment


def _episode_payload(path: Path, expected_digest: str) -> dict[str, str]:
    payload = _load_mapping(path, "episode input")
    protocol = _load_module("synthetic_user_protocol")
    try:
        normalized = protocol.validate_runner_episode_input(payload)
    except protocol.SyntheticUserProtocolError as error:
        raise ValueError(str(error)) from error
    if _digest_file(path) != expected_digest:
        raise ValueError("episode input digest does not match the sealed plan")
    return normalized


def _terminal_payload(path: Path) -> dict[str, object]:
    payload = _load_mapping(path, "episode output")
    required = {
        "source_capture_set_digest",
        "transcript_digest",
        "synthetic_session_receipt_digest",
        "token_usage",
        "integrity",
    }
    if set(payload) != required:
        raise ValueError("episode output has an unexpected shape")
    return payload


def _cell_by_pair(manifest: Mapping[str, object]) -> dict[tuple[str, str], Mapping[str, object]]:
    cells = manifest["cells"]
    if not isinstance(cells, tuple):
        raise ValueError("normalized manifest cells are unavailable")
    return {(str(cell["host"]), str(cell["condition"])): cell for cell in cells}


def _render_command(template: str, *, input_path: Path, output_path: Path) -> list[str]:
    rendered = template.format(episode_input_path=str(input_path), episode_output_path=str(output_path))
    command = shlex.split(rendered)
    if not command:
        raise ValueError("host command must not be empty")
    return command


def run(
    manifest_path: Path,
    journal_dir: Path,
    key_path: Path,
    input_dir: Path,
    *,
    harness_revision: str,
    timeout_seconds: int,
    episode_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    if timeout_seconds < 1 or timeout_seconds > 86_400:
        raise ValueError("timeout_seconds must be between one and 86400")
    journal_dir = _evaluator_path(journal_dir, "journal directory")
    key_path = _evaluator_path(key_path, "journal attestation key")
    input_dir = _evaluator_path(input_dir, "episode input directory")
    benchmark = _load_module("paired_benchmark")
    raw_manifest = _load_mapping(manifest_path, "sealed manifest")
    manifest = benchmark.validate_sealed_manifest(raw_manifest)
    journal_module = _load_module("episode_journal")
    journal = journal_module.EpisodeJournal(journal_dir, attestation_key=key_path.read_bytes().strip())
    try:
        run_id = journal.initialize(raw_manifest, harness_revision=harness_revision)
        plan = {str(entry["episode_id"]): entry for entry in manifest["episode_plan"]}
        selected = tuple(sorted(episode_ids)) if episode_ids else journal.pending(run_id)
        if not selected:
            return {"run_id": run_id, "executed_episode_ids": [], "status": "complete"}
        if any(episode_id not in plan for episode_id in selected):
            raise ValueError("requested episode is not in the sealed plan")
        cells = _cell_by_pair(manifest)
        executed: list[str] = []
        for episode_id in selected:
            entry = plan[episode_id]
            cell = cells[(str(entry["host"]), str(entry["condition"]))]
            input_path = input_dir / f"{episode_id}.json"
            _episode_payload(input_path, str(entry["runner_input_digest"]))
            episode_root = journal_dir / "episodes" / episode_id
            episode_root.mkdir(parents=True, exist_ok=True)
            output_path = episode_root / "host-result.json"
            attempt_id = journal.reserve(run_id, episode_id)
            contract = journal._contract(run_id, episode_id)
            journal.start(
                run_id, episode_id, attempt_id, {name: contract[name] for name in journal_module._OBSERVED_FIELDS}
            )
            command = _render_command(str(cell["host_command"]), input_path=input_path, output_path=output_path)
            completed = subprocess.run(
                command,
                cwd=episode_root,
                env=_safe_environment(),
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
            (episode_root / "stdout.log").write_bytes(completed.stdout)
            (episode_root / "stderr.log").write_bytes(completed.stderr)
            if completed.returncode != 0 or not output_path.is_file():
                journal.checkpoint(
                    run_id,
                    episode_id,
                    attempt_id,
                    status="failed",
                    result_digest=_digest_bytes(completed.stdout + completed.stderr),
                    source_capture_set_digest=_digest_bytes(b""),
                    transcript_digest=_digest_bytes(b""),
                    synthetic_session_receipt_digest=_digest_bytes(b""),
                    token_usage={"cache_hit_input_tokens": 0, "cache_miss_input_tokens": 0, "output_tokens": 0},
                    integrity={"host_command_failed": True},
                )
                journal.invalidate_group(run_id, episode_id, reason_code="host_command_failed")
                raise RuntimeError(f"host command failed for {episode_id}")
            result = _terminal_payload(output_path)
            journal.checkpoint(
                run_id,
                episode_id,
                attempt_id,
                status="completed",
                result_digest=_digest_file(output_path),
                source_capture_set_digest=str(result["source_capture_set_digest"]),
                transcript_digest=str(result["transcript_digest"]),
                synthetic_session_receipt_digest=str(result["synthetic_session_receipt_digest"]),
                token_usage=result["token_usage"],
                integrity=result["integrity"],
            )
            executed.append(episode_id)
        return {
            "run_id": run_id,
            "executed_episode_ids": executed,
            "status": "incomplete" if journal.pending(run_id) else "complete",
        }
    finally:
        journal.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--journal-dir", type=Path, required=True)
    parser.add_argument("--journal-attestation-key-file", type=Path, required=True)
    parser.add_argument("--episode-input-dir", type=Path, required=True)
    parser.add_argument("--harness-revision", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=3_600)
    parser.add_argument("--episode-id", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        result = run(
            args.manifest,
            args.journal_dir,
            args.journal_attestation_key_file,
            args.episode_input_dir,
            harness_revision=args.harness_revision,
            timeout_seconds=args.timeout_seconds,
            episode_ids=tuple(args.episode_id),
        )
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
