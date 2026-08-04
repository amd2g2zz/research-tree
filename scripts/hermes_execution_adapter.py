#!/usr/bin/env python3
"""Durable Hermes-native wave state for research-tree runs.

Hermes owns delegation and completion events; this adapter owns the durable
checkpoint that those events update. It deliberately does not invoke Hermes
tools itself.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any


SCHEMA = 1
STATUSES = {"aligned", "researching", "unknown", "delivery_pending", "complete"}
BATCH_STATUSES = {"running", "verified", "failed", "unknown"}
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class HermesExecutionError(ValueError):
    """Raised for invalid Hermes execution state or artifacts."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identifier(value: str, label: str) -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        raise HermesExecutionError(f"invalid {label}: {value!r}")
    return value


def _inside(workspace: Path, candidate: Path, label: str) -> Path:
    root = workspace.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise HermesExecutionError(f"{label} must remain in the workspace") from exc
    return resolved


def _run_dir(workspace: Path, run_id: str) -> Path:
    return _inside(workspace, workspace / ".research-tree-hermes" / _identifier(run_id, "run id"), "run directory")


def _state_path(workspace: Path, run_id: str) -> Path:
    return _run_dir(workspace, run_id) / "state.json"


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HermesExecutionError(f"missing {label}: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise HermesExecutionError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise HermesExecutionError(f"{label} must be an object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_state(workspace: Path, run_id: str) -> dict[str, Any]:
    state = _read_json(_state_path(workspace, run_id), "Hermes execution state")
    if state.get("schema") != SCHEMA or state.get("run_id") != run_id:
        raise HermesExecutionError("unsupported or mismatched Hermes execution state")
    if state.get("status") not in STATUSES:
        raise HermesExecutionError("Hermes execution state status is invalid")
    if not isinstance(state.get("batches"), dict):
        raise HermesExecutionError("Hermes execution batches must be an object")
    return state


def _save_state(workspace: Path, state: dict[str, Any]) -> None:
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated_at"] = _now()
    _write_json(_state_path(workspace, state["run_id"]), state)


def _load_handoff(workspace: Path, path: Path) -> tuple[dict[str, Any], Path]:
    resolved = _inside(workspace, path, "handoff path")
    handoff = _read_json(resolved, "alignment handoff")
    if handoff.get("schema") != 1 or handoff.get("kind") != "alignment-handoff":
        raise HermesExecutionError("handoff must be a schema-1 alignment-handoff artifact")
    if not isinstance(handoff.get("decision_slots"), dict) or not handoff["decision_slots"]:
        raise HermesExecutionError("handoff decision_slots must be nonempty")
    if not isinstance(handoff.get("execution_context"), dict):
        raise HermesExecutionError("handoff execution_context must be an object")
    return handoff, resolved


def init_run(workspace: Path, run_id: str, handoff_path: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    if _state_path(workspace, run_id).exists():
        raise HermesExecutionError(f"run already exists: {run_id}")
    handoff, resolved = _load_handoff(workspace, handoff_path)
    state = {
        "schema": SCHEMA,
        "run_id": run_id,
        "status": "aligned",
        "revision": 0,
        "created_at": _now(),
        "updated_at": _now(),
        "handoff_path": str(resolved),
        "handoff_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "alignment_run_id": handoff.get("run_id"),
        "decision_slots": handoff["decision_slots"],
        "execution_context": handoff["execution_context"],
        "batches": {},
        "deliverables": {
            "technical_research_package": {"status": "pending"},
            "human_research_report": {"status": "pending"},
        },
    }
    _save_state(workspace, state)
    return state


def record_batch(
    workspace: Path,
    run_id: str,
    batch_id: str,
    status: str,
    delegation_ids: list[str],
    finding_paths: list[Path],
) -> dict[str, Any]:
    state = _load_state(workspace, run_id)
    batch_id = _identifier(batch_id, "batch id")
    if status not in BATCH_STATUSES:
        raise HermesExecutionError(f"invalid batch status: {status}")
    if batch_id in state["batches"]:
        raise HermesExecutionError(f"batch already exists: {batch_id}")
    paths = []
    for path in finding_paths:
        resolved = _inside(workspace, path, "Finding Pack path")
        if status == "verified" and not resolved.is_file():
            raise HermesExecutionError(f"verified Finding Pack is missing: {resolved}")
        paths.append(str(resolved))
    state["batches"][batch_id] = {
        "batch_id": batch_id,
        "status": status,
        "delegation_ids": delegation_ids,
        "finding_paths": paths,
        "recorded_at": _now(),
    }
    state["status"] = "researching" if status in {"running", "verified"} else status
    _save_state(workspace, state)
    return state


def recover_run(workspace: Path, run_id: str) -> dict[str, Any]:
    state = _load_state(workspace, run_id)
    recovered = []
    for batch in state["batches"].values():
        if batch["status"] == "running":
            batch["status"] = "unknown"
            recovered.append(batch["batch_id"])
    if recovered:
        state["status"] = "unknown"
        _save_state(workspace, state)
    return {"recovered_batches": recovered, "state": state}


def _verify_report(workspace: Path, path: Path, kind: str, minimum_bytes: int, minimum_headings: int) -> dict[str, Any]:
    resolved = _inside(workspace, path, f"{kind} path")
    raw = resolved.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise HermesExecutionError(f"{kind} must be UTF-8 without BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HermesExecutionError(f"{kind} must be UTF-8") from exc
    headings = len(re.findall(r"(?m)^#{1,6}\s+\S", text))
    if len(raw) < minimum_bytes or headings < minimum_headings:
        raise HermesExecutionError(f"{kind} is too shallow")
    return {
        "status": "verified", "kind": kind, "path": str(resolved),
        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "heading_count": headings,
    }


def complete_run(workspace: Path, run_id: str, technical: Path, human: Path) -> dict[str, Any]:
    state = _load_state(workspace, run_id)
    if not state["batches"] or any(batch["status"] != "verified" for batch in state["batches"].values()):
        raise HermesExecutionError("all delegation batches must be verified before completion")
    state["deliverables"] = {
        "technical_research_package": _verify_report(workspace, technical, "technical_research_package", 1024, 3),
        "human_research_report": _verify_report(workspace, human, "human_research_report", 512, 2),
    }
    state["status"] = "complete"
    _save_state(workspace, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--run-id", required=True)
    init.add_argument("--handoff", type=Path, required=True)
    batch = commands.add_parser("record-batch")
    batch.add_argument("--run-id", required=True)
    batch.add_argument("--batch-id", required=True)
    batch.add_argument("--status", choices=sorted(BATCH_STATUSES), required=True)
    batch.add_argument("--delegation-id", action="append", default=[])
    batch.add_argument("--finding", type=Path, action="append", default=[])
    recover = commands.add_parser("recover")
    recover.add_argument("--run-id", required=True)
    status = commands.add_parser("status")
    status.add_argument("--run-id", required=True)
    complete = commands.add_parser("complete")
    complete.add_argument("--run-id", required=True)
    complete.add_argument("--technical-report", type=Path, required=True)
    complete.add_argument("--human-report", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    try:
        if args.command == "init":
            path = args.handoff if args.handoff.is_absolute() else workspace / args.handoff
            result = init_run(workspace, args.run_id, path)
        elif args.command == "record-batch":
            result = record_batch(workspace, args.run_id, args.batch_id, args.status, args.delegation_id, [
                path if path.is_absolute() else workspace / path for path in args.finding
            ])
        elif args.command == "recover":
            result = recover_run(workspace, args.run_id)
        elif args.command == "complete":
            technical = args.technical_report if args.technical_report.is_absolute() else workspace / args.technical_report
            human = args.human_report if args.human_report.is_absolute() else workspace / args.human_report
            result = complete_run(workspace, args.run_id, technical, human)
        else:
            result = _load_state(workspace, args.run_id)
    except (HermesExecutionError, OSError) as exc:
        print(str(exc))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
