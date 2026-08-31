"""Fail-open lifecycle observer shared by supported agent hosts."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Sequence

from .skill_activation import build_loader_receipt

MAX_INPUT_BYTES = 64 * 1024
MAX_IDENTIFIER_LENGTH = 256
PROJECT_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
HOST_EVENTS = {
    "codex": frozenset(
        {
            "SessionStart",
            "SessionEnd",
            "PreCompact",
            "PostCompact",
            "SubagentStart",
            "SubagentStop",
            "Stop",
        }
    ),
    "claude": frozenset({"SessionStart", "SessionEnd", "PreCompact", "SubagentStop", "PostToolUse", "Stop"}),
    "hermes": frozenset({"on_session_start", "on_session_end"}),
}


class LifecycleHookError(ValueError):
    """Raised when a lifecycle payload or hook configuration is invalid."""


def read_payload(stream: BinaryIO | None = None) -> dict[str, Any]:
    """Read one bounded UTF-8 JSON object from a host hook payload."""
    source = stream or sys.stdin.buffer
    raw = source.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise LifecycleHookError("hook input exceeds the maximum size")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LifecycleHookError("hook input must be a UTF-8 JSON object") from exc
    if not isinstance(payload, dict):
        raise LifecycleHookError("hook input must be a JSON object")
    return payload


def _inside(root: Path, candidate: Path, label: str) -> Path:
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise LifecycleHookError(f"{label} must remain inside the project") from exc
    return resolved


def find_project_root(start: Path) -> Path:
    """Find the Research Tree checkout that owns the running hook."""
    current = start.resolve(strict=False)
    for candidate in (current, *current.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "packages").is_dir()
            and (candidate / "skill-src").is_dir()
        ):
            return candidate
    raise LifecycleHookError("hook must run inside a Research Tree checkout")


def validate_workspace(
    payload: dict[str, Any],
    *,
    project_root: Path | None = None,
    process_cwd: Path | None = None,
) -> tuple[Path, Path]:
    """Validate both the process and host-reported working directories."""
    actual_cwd = (process_cwd or Path.cwd()).resolve(strict=False)
    root = project_root.resolve(strict=False) if project_root is not None else find_project_root(actual_cwd)
    _inside(root, actual_cwd, "process cwd")

    raw_cwd = payload.get("cwd")
    if not isinstance(raw_cwd, str) or not raw_cwd.strip():
        raise LifecycleHookError("hook input requires an absolute cwd")
    reported = Path(raw_cwd)
    if not reported.is_absolute():
        raise LifecycleHookError("hook cwd must be absolute")
    return root, _inside(root, reported, "reported cwd")


def _validate_event(payload: dict[str, Any], host: str, event: str) -> None:
    try:
        allowed = HOST_EVENTS[host]
    except KeyError as exc:
        raise LifecycleHookError(f"unsupported hook host: {host}") from exc
    if event not in allowed:
        raise LifecycleHookError(f"unsupported {host} hook event: {event}")
    actual = payload.get("hook_event_name")
    if actual is not None and actual != event:
        raise LifecycleHookError("hook event does not match configured event")


def _optional_identifier(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_IDENTIFIER_LENGTH:
        return None
    return value


def _write_record(root: Path, record: dict[str, Any], event_dir: Path) -> Path:
    event_dir = _inside(root, event_dir, "hook event directory")
    event_dir.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for _ in range(3):
        path = _inside(
            root,
            event_dir / f"{prefix}-{secrets.token_hex(8)}.json",
            "hook event file",
        )
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        return path
    raise LifecycleHookError("could not allocate a hook event file")


def observe(
    payload: dict[str, Any],
    *,
    host: str,
    event: str,
    project_root: Path | None = None,
    process_cwd: Path | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    """Persist sanitized lifecycle metadata without affecting host behavior."""
    if not isinstance(payload, dict):
        raise LifecycleHookError("hook input must be a JSON object")
    _validate_event(payload, host, event)

    if event == "Stop" and payload.get("stop_hook_active") is True:
        return {"status": "skipped_reentrant_stop", "host": host, "event": event}

    project_id = payload.get("project_id")
    run_id = payload.get("run_id")
    if project_id is None and run_id is None:
        project_id = os.environ.get("RESEARCH_TREE_PROJECT_ID")
        run_id = os.environ.get("RESEARCH_TREE_RUN_ID")
    if project_id is None and run_id is None:
        return {"status": "skipped_inactive", "host": host, "event": event}

    root, workspace = validate_workspace(payload, project_root=project_root, process_cwd=process_cwd)
    record: dict[str, Any] = {
        "schema": 1,
        "source": "research-tree-lifecycle-hook",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": host,
        "event": event,
        "workspace": workspace.relative_to(root).as_posix() or ".",
    }
    for key in ("session_id", "turn_id", "agent_id", "task_id", "attempt_id", "causation_id"):
        value = _optional_identifier(payload, key)
        if value is not None:
            record[key] = value
    if event in {"SessionStart", "on_session_start"}:
        skill_dir_raw = os.environ.get("RESEARCH_TREE_SKILL_DIR")
        session_id = record.get("session_id")
        if isinstance(skill_dir_raw, str) and isinstance(session_id, str):
            try:
                loader = build_loader_receipt(
                    Path(skill_dir_raw),
                    host=host,
                    session_id=session_id,
                    evidence="host-session-start",
                )
                record["skill_load"] = loader
            except (OSError, ValueError):
                record["skill_load"] = {"state": "unverified_loader_integrity", "host": host}
    if host == "claude" and event == "SubagentStop":
        identity = tuple(
            _optional_identifier(payload, key)
            for key in ("task_id", "attempt_id", "agent_id", "session_id", "causation_id")
        )
        record["binding_status"] = "candidate" if all(identity) else "unknown_outcome"
    if host == "claude" and event == "PostToolUse" and payload.get("tool_name") == "Agent":
        response = payload.get("tool_response")
        agent_id = _optional_identifier(response, "agentId") if isinstance(response, dict) else None
        causation_id = _optional_identifier(payload, "tool_use_id")
        if agent_id is not None:
            record["agent_id"] = agent_id
        if causation_id is not None:
            record["causation_id"] = causation_id
        record["binding_status"] = (
            "host_identity_recorded" if agent_id is not None and causation_id is not None else "unknown_outcome"
        )
    if host == "codex" and event in ("SubagentStart", "SubagentStop"):
        response = payload.get("tool_response")
        agent_id = _optional_identifier(response, "agentId") if isinstance(response, dict) else None
        if agent_id is not None:
            record["agent_id"] = agent_id
        record["binding_status"] = "candidate" if agent_id is not None else "unknown_outcome"
    if (
        not isinstance(project_id, str)
        or not isinstance(run_id, str)
        or not PROJECT_IDENTIFIER_RE.fullmatch(project_id)
        or not PROJECT_IDENTIFIER_RE.fullmatch(run_id)
    ):
        raise LifecycleHookError("project_id and run_id must be opaque identifiers")
    run_root = root / ".research-tree" / "projects" / project_id / "runs" / run_id
    if not (run_root / "manifest.json").is_file():
        raise LifecycleHookError("project run is not initialized")
    record["project_id"] = project_id
    record["run_id"] = run_id
    path = _write_record(root, record, run_root / "events")
    if debug:
        try:
            from .debug_trace import emit_trace

            emit_trace(
                host=host,
                phase="lifecycle_observed",
                status="completed",
                codes=(f"event:{event}",),
                project_root=root,
            )
        except (OSError, ValueError):
            # Debug tracing is opt-in observability, never lifecycle behavior.
            pass
    return {
        "status": "recorded",
        "host": host,
        "event": event,
        "path": path.relative_to(root).as_posix(),
        **({"skill_load": record["skill_load"]} if "skill_load" in record else {}),
    }


def host_response(host: str) -> dict[str, Any]:
    """Return a non-blocking response understood by the selected host."""
    if host not in HOST_EVENTS:
        raise LifecycleHookError(f"unsupported hook host: {host}")
    return {} if host == "hermes" else {"continue": True}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-tree-hook",
        description="Record sanitized Research Tree agent lifecycle events.",
    )
    parser.add_argument("--host", choices=tuple(HOST_EVENTS), required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--run-id")
    parser.add_argument("--session-id")
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        payload = read_payload()
        for key in ("project_id", "run_id", "session_id"):
            value = getattr(arguments, key)
            if value is not None:
                payload[key] = value
        observe(
            payload,
            host=arguments.host,
            event=arguments.event,
            project_root=arguments.project_root,
            debug=arguments.debug,
        )
    except (LifecycleHookError, OSError) as exc:
        # Lifecycle observation must never block an agent session.
        if arguments.debug:
            print(f"research-tree hook debug: {exc}", file=sys.stderr)
    print(json.dumps(host_response(arguments.host), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
