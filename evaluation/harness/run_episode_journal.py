"""Initialize and recover an evaluator-owned paired benchmark journal."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).parents[2]
RUN_ROOT = ROOT / ".research-tree" / "evaluation-runs"


def _journal_module():
    path = Path(__file__).with_name("episode_journal.py")
    spec = importlib.util.spec_from_file_location("episode_journal", path)
    if spec is None or spec.loader is None:
        raise ValueError("unable to load episode journal")
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


def _load_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("sealed manifest must be a JSON object")
    return value


def run(
    manifest_path: Path, journal_dir: Path, key_path: Path, *, harness_revision: str, abandon_started: bool
) -> dict[str, object]:
    journal_dir = _evaluator_path(journal_dir, "journal directory")
    key_path = _evaluator_path(key_path, "journal attestation key")
    key = key_path.read_bytes().strip()
    if not key:
        raise ValueError("journal attestation key must not be empty")
    journal = _journal_module().EpisodeJournal(journal_dir, attestation_key=key)
    try:
        run_id = journal.initialize(_load_mapping(manifest_path), harness_revision=harness_revision)
        abandoned = journal.abandon_started(run_id) if abandon_started else ()
        pending = journal.pending(run_id)
        return {"run_id": run_id, "abandoned_episode_ids": list(abandoned), "pending_episode_ids": list(pending)}
    finally:
        journal.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--journal-dir", type=Path, required=True)
    parser.add_argument("--journal-attestation-key-file", type=Path, required=True)
    parser.add_argument("--harness-revision", required=True)
    parser.add_argument("--abandon-started", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(
            args.manifest,
            args.journal_dir,
            args.journal_attestation_key_file,
            harness_revision=args.harness_revision,
            abandon_started=args.abandon_started,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
