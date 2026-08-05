"""Write and summarize sanitized, opt-in research workflow traces."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import time
from typing import Any, Iterable, Mapping, Sequence


TRACE_DIRECTORY = Path(".research-tree-debug") / "events"
HOSTS = frozenset({"codex", "claude", "hermes"})
PHASES = frozenset(
    {
        "lifecycle_observed",
        "intake",
        "reconnaissance",
        "alignment_turn",
        "alignment_checkpoint",
        "alignment_blocked",
        "research_started",
        "implementation_started",
        "worker_blocked",
        "completed",
        "aborted",
    }
)
STATUSES = frozenset({"started", "completed", "blocked", "skipped", "failed"})
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
CODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")


class DebugTraceError(ValueError):
    """Raised when a debug trace would be ambiguous or unsafe to persist."""


def find_project_root(start: Path) -> Path:
    """Find the checkout that owns an opt-in debug trace."""
    current = start.resolve(strict=False)
    for candidate in (current, *current.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "packages").is_dir()
            and (candidate / "skill-src").is_dir()
        ):
            return candidate
    raise DebugTraceError("debug tracing must run inside a Research Tree checkout")


def _inside(root: Path, candidate: Path) -> Path:
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise DebugTraceError("debug trace path must remain inside the project") from exc
    return resolved


def _project_root(project_root: Path | None) -> Path:
    root = (
        project_root.resolve(strict=False)
        if project_root is not None
        else find_project_root(Path.cwd())
    )
    if not (
        (root / "pyproject.toml").is_file()
        and (root / "packages").is_dir()
        and (root / "skill-src").is_dir()
    ):
        raise DebugTraceError("project root is not a Research Tree checkout")
    return root


def _identifier(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if not IDENTIFIER_RE.fullmatch(value):
        raise DebugTraceError(f"{label} must be a bounded identifier")
    return value


def _codes(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not CODE_RE.fullmatch(value):
            raise DebugTraceError("debug code must be a bounded identifier")
        result.append(value)
    if len(result) > 16:
        raise DebugTraceError("a debug trace accepts at most 16 codes")
    return result


def _write_record(root: Path, record: dict[str, Any]) -> Path:
    destination = _inside(root, root / TRACE_DIRECTORY,)
    destination.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    for _ in range(3):
        prefix = f"{time.time_ns():020d}"
        path = _inside(
            root,
            destination / f"{prefix}-{secrets.token_hex(8)}.json",
        )
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        return path
    raise DebugTraceError("could not allocate a debug trace file")


def emit_trace(
    *,
    host: str,
    phase: str,
    status: str,
    codes: Iterable[str] = (),
    run_id: str | None = None,
    project_root: Path | None = None,
    sequence: int | None = None,
    causation_id: str | None = None,
    correlation_id: str | None = None,
    action: str | None = None,
    inputs: Iterable[str] = (),
    score_components: Mapping[str, float] | None = None,
    outcome: str | None = None,
    redaction_class: str | None = None,
    retention_class: str | None = None,
    prior_digest: str | None = None,
    next_digest: str | None = None,
) -> dict[str, Any]:
    """Persist one sanitized workflow transition and return its relative path."""
    if host not in HOSTS:
        raise DebugTraceError(f"unsupported debug host: {host}")
    if phase not in PHASES:
        raise DebugTraceError(f"unsupported debug phase: {phase}")
    if status not in STATUSES:
        raise DebugTraceError(f"unsupported debug status: {status}")
    if sequence is not None and (not isinstance(sequence, int) or sequence < 1):
        raise DebugTraceError("sequence must be a positive integer")

    root = _project_root(project_root)
    record: dict[str, Any] = {
        "schema": 1,
        "source": "research-tree-debug",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "host": host,
        "phase": phase,
        "status": status,
        "codes": _codes(codes),
    }
    normalized_run_id = _identifier(run_id, "run id")
    if normalized_run_id is not None:
        record["run_id"] = normalized_run_id
    optional = {
        "sequence": sequence, "causation_id": _identifier(causation_id, "causation id"),
        "correlation_id": _identifier(correlation_id, "correlation id"),
        "action": _identifier(action, "action"), "inputs": _codes(inputs),
        "score_components": dict(score_components or {}), "outcome": _identifier(outcome, "outcome"),
        "redaction_class": _identifier(redaction_class, "redaction class"),
        "retention_class": _identifier(retention_class, "retention class"),
        "prior_digest": prior_digest, "next_digest": next_digest,
    }
    for key, value in optional.items():
        if value is not None and value not in ([], {}):
            record[key] = value
    path = _write_record(root, record)
    return {"status": "recorded", "path": path.relative_to(root).as_posix()}


def emit_causal_trace(
    *, host: str, phase: str, status: str, run_id: str, event_id: str,
    sequence: int, actor: str, action: str, project_root: Path | None = None,
    causation_id: str | None = None, correlation_id: str | None = None,
    prior_digest: str | None = None, next_digest: str | None = None,
    codes: Iterable[str] = (), outcome: str | None = None,
) -> dict[str, Any]:
    """Emit the complete causal-trace surface while excluding prompts/diagnostics."""
    if not _identifier(event_id, "event id") or not _identifier(actor, "actor"):
        raise DebugTraceError("event_id and actor are required")
    result = emit_trace(
        host=host, phase=phase, status=status, codes=codes, run_id=run_id,
        project_root=project_root, sequence=sequence, causation_id=causation_id,
        correlation_id=correlation_id, action=action, outcome=outcome,
        prior_digest=prior_digest, next_digest=next_digest,
        redaction_class="sanitized", retention_class="release-plus-audit",
    )
    root = _project_root(project_root)
    path = root / result["path"]
    value = json.loads(path.read_text(encoding="utf-8"))
    value["trace_id"] = event_id
    value["event_id"] = event_id
    value["actor"] = actor
    path.write_text(json.dumps(value, ensure_ascii=True, separators=(",", ":")), encoding="utf-8", newline="\n")
    return result


def summarize_traces(
    *, project_root: Path | None = None, limit: int = 25
) -> dict[str, Any]:
    """Return a bounded, chronological summary of sanitized trace files."""
    if limit < 1 or limit > 200:
        raise DebugTraceError("limit must be between 1 and 200")
    root = _project_root(project_root)
    trace_dir = _inside(root, root / TRACE_DIRECTORY)
    records: list[dict[str, Any]] = []
    if trace_dir.is_dir():
        for path in sorted(trace_dir.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                records.append(value)
    records.sort(key=lambda item: (
        0 if isinstance(item.get("sequence"), int) else 1,
        item.get("sequence", 0) if isinstance(item.get("sequence"), int) else item.get("recorded_at", ""),
        str(item.get("causation_id") or ""), str(item.get("event_id") or ""),
    ))
    phases = Counter(
        item["phase"]
        for item in records
        if isinstance(item.get("phase"), str)
    )
    statuses = Counter(
        item["status"]
        for item in records
        if isinstance(item.get("status"), str)
    )
    return {
        "schema": 1,
        "trace_directory": trace_dir.relative_to(root).as_posix(),
        "event_count": len(records),
        "by_phase": dict(sorted(phases.items())),
        "by_status": dict(sorted(statuses.items())),
        "recent": records[-limit:],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-tree-debug",
        description="Emit or summarize sanitized Research Tree workflow traces.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    emit = commands.add_parser("emit", help="write one sanitized phase event")
    emit.add_argument("--host", choices=tuple(sorted(HOSTS)), required=True)
    emit.add_argument("--phase", choices=tuple(sorted(PHASES)), required=True)
    emit.add_argument("--status", choices=tuple(sorted(STATUSES)), required=True)
    emit.add_argument("--code", action="append", default=[])
    emit.add_argument("--run-id")
    emit.add_argument("--project-root", type=Path)

    summary = commands.add_parser("summary", help="summarize sanitized phase events")
    summary.add_argument("--project-root", type=Path)
    summary.add_argument("--limit", type=int, default=25)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "emit":
            result = emit_trace(
                host=arguments.host,
                phase=arguments.phase,
                status=arguments.status,
                codes=arguments.code,
                run_id=arguments.run_id,
                project_root=arguments.project_root,
            )
        else:
            result = summarize_traces(
                project_root=arguments.project_root, limit=arguments.limit
            )
    except DebugTraceError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
