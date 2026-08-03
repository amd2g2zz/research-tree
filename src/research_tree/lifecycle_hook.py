"""Fail-open lifecycle observer shared by supported agent hosts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import sys
from typing import Any, BinaryIO, Sequence


MAX_INPUT_BYTES = 64 * 1024
MAX_IDENTIFIER_LENGTH = 256
EVENT_DIRECTORY = Path(".research-tree-hooks") / "events"
HOST_EVENTS = {
    "codex": frozenset({"SessionStart", "Stop"}),
    "claude": frozenset({"SessionStart", "Stop"}),
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
    root = (
        project_root.resolve(strict=False)
        if project_root is not None
        else find_project_root(actual_cwd)
    )
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


def _write_record(root: Path, record: dict[str, Any]) -> Path:
    event_dir = _inside(root, root / EVENT_DIRECTORY, "hook event directory")
    event_dir.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        record, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
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

    if host == "claude" and event == "Stop" and payload.get("stop_hook_active") is True:
        return {"status": "skipped_reentrant_stop", "host": host, "event": event}

    root, workspace = validate_workspace(
        payload, project_root=project_root, process_cwd=process_cwd
    )
    record: dict[str, Any] = {
        "schema": 1,
        "source": "research-tree-lifecycle-hook",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": host,
        "event": event,
        "workspace": workspace.relative_to(root).as_posix() or ".",
    }
    for key in ("session_id", "turn_id", "agent_id"):
        value = _optional_identifier(payload, key)
        if value is not None:
            record[key] = value
    path = _write_record(root, record)
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
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        observe(
            read_payload(),
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
