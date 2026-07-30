"""Frozen-snapshot evidence retrieval for the dedicated Q&A subagent."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import corpus
import engine
import project


def workspace() -> Path:
    return Path(os.environ.get("RESEARCH_WORKSPACE", os.getcwd()))


def ask(snapshot: str, question: str, top: int) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if isinstance(top, bool) or not isinstance(top, int) or not 1 <= top <= 16:
        raise ValueError("top must be an integer from 1 through 16")
    snapshot = engine.safe_snapshot_id(snapshot)
    verified = project.verify_snapshot(snapshot)
    if not verified["ok"]:
        raise ValueError(f"frozen snapshot integrity check failed: {verified['issues']}")
    root = verified["path"]
    manifest_path = root / "manifest.json"
    state_path = root / "research_state.json"
    corpus_path = root / "corpus"
    if not (manifest_path.is_file() and state_path.is_file() and corpus_path.is_dir()):
        raise FileNotFoundError("Q&A is available only for a frozen snapshot with corpus")
    result = corpus.search_files(corpus_path / "chunks.jsonl", corpus_path / "inverted_index.json", question.strip(), top)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return {"status": "retrieved", "snapshot_id": snapshot, "question": question.strip(),
            "reference_time": state["reference_time"], "frozen_at": json.loads(manifest_path.read_text(encoding="utf-8"))["frozen_at"],
            "evidence_packets": result,
            "instruction": "Answer only from these frozen packets. Cite source_path/chunk_id; return partial or unknown when evidence is insufficient."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qa", description="retrieve frozen research evidence for Q&A")
    sub = parser.add_subparsers(dest="command", required=True)
    ask_cmd = sub.add_parser("ask"); ask_cmd.add_argument("--snapshot", required=True); ask_cmd.add_argument("--question", required=True); ask_cmd.add_argument("--top", type=int, default=8)
    args = parser.parse_args(argv)
    print(json.dumps(ask(args.snapshot, args.question, args.top), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
