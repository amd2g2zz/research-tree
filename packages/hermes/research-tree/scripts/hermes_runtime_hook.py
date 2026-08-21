#!/usr/bin/env python3
"""Record sanitized Hermes lifecycle metadata without package dependencies."""

from __future__ import annotations

import json
import hashlib
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_INPUT_BYTES = 1_048_576
EVENTS = frozenset(
    {
        "on_session_start",
        "on_session_end",
        "on_session_finalize",
        "on_session_reset",
        "subagent_start",
        "subagent_stop",
        "post_tool_call",
    }
)
SAFE_EXTRA_KEYS = (
    "delegation_id",
    "task_id",
    "attempt_id",
    "action_id",
    "causation_id",
    "tool_call_id",
    "child_id",
    "child_session_id",
    "child_subagent_id",
    "parent_subagent_id",
    "parent_turn_id",
    "turn_id",
    "api_request_id",
    "role",
    "status",
    "duration_ms",
)
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
ENV_IDENTITY_FALLBACKS = (
    ("RESEARCH_TREE_TASK_ID", "task_id"),
    ("RESEARCH_TREE_ATTEMPT_ID", "attempt_id"),
    ("RESEARCH_TREE_ACTION_ID", "action_id"),
)


def _bounded_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("hook payload exceeds limit")
    value = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    if not isinstance(value, dict):
        raise ValueError("hook payload must be an object")
    return value


def _safe_scalar(value: Any) -> str | int | float | bool | None:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def _safe_identifier(value: Any) -> str | None:
    return value if isinstance(value, str) and IDENTIFIER_RE.fullmatch(value) else None


def _event_record(payload: dict[str, Any]) -> dict[str, Any] | None:
    event = payload.get("hook_event_name")
    if event not in EVENTS:
        return None
    tool_name = payload.get("tool_name")
    if event == "post_tool_call" and tool_name != "delegate_task":
        return None

    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    for key in ("session_id", "tool_name"):
        value = _safe_scalar(payload.get(key))
        if value is not None:
            record[key] = value
    for key in ("task_id", "attempt_id", "action_id", "causation_id"):
        value = _safe_identifier(payload.get(key))
        if value is not None:
            record[key] = value

    tool_input = payload.get("tool_input")
    if tool_name == "delegate_task" and isinstance(tool_input, dict):
        tasks = tool_input.get("tasks")
        if isinstance(tasks, list):
            record["task_count"] = len(tasks)

    extra = payload.get("extra")
    if isinstance(extra, dict):
        for key in SAFE_EXTRA_KEYS:
            value = _safe_identifier(extra.get(key)) if key.endswith("_id") else _safe_scalar(extra.get(key))
            if value is not None:
                record[key] = value
                if key == "child_subagent_id":
                    record.setdefault("agent_id", value)
                elif key == "tool_call_id":
                    record.setdefault("causation_id", value)
    for env_key, record_key in ENV_IDENTITY_FALLBACKS:
        if record_key not in record:
            value = _safe_identifier(os.environ.get(env_key))
            if value is not None:
                record[record_key] = value
    return record


def _workspace(payload: dict[str, Any]) -> Path:
    raw = payload.get("cwd")
    return Path(raw).resolve() if isinstance(raw, str) and raw else Path.cwd().resolve()


def _event_directory(payload: dict[str, Any]) -> Path | None:
    project_id = os.environ.get("RESEARCH_TREE_PROJECT_ID")
    run_id = os.environ.get("RESEARCH_TREE_RUN_ID")
    if not project_id or not run_id or not IDENTIFIER_RE.fullmatch(project_id) or not IDENTIFIER_RE.fullmatch(run_id):
        return None
    run_root = _workspace(payload) / ".research-tree" / "projects" / project_id / "runs" / run_id
    if not (run_root / "manifest.json").is_file():
        return None
    return run_root / "events"


def main() -> int:
    try:
        payload = _bounded_payload()
        record = _event_record(payload)
        event_directory = _event_directory(payload)
        if record is not None and event_directory is not None:
            if payload.get("hook_event_name") == "on_session_start":
                skill_file = Path(__file__).resolve().parents[1] / "SKILL.md"
                if skill_file.is_file():
                    skill_bytes = skill_file.read_bytes()
                    record = {
                        "timestamp": record["timestamp"],
                        "event": "skill-load",
                        "session_id": record.get("session_id"),
                        "host": "hermes",
                        "state": "host_message_verified",
                        "byte_count": len(skill_bytes),
                        "line_count": len(skill_bytes.decode("utf-8").splitlines()),
                        "skill_body_digest": hashlib.sha256(skill_bytes).hexdigest(),
                        "evidence": "hermes-runtime-hook",
                    }
            record["schema"] = 1
            record["source"] = "research-tree-hermes-hook"
            event_directory.mkdir(parents=True, exist_ok=True)
            target = event_directory / (
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + secrets.token_hex(8) + ".json"
            )
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(record, stream, ensure_ascii=True, separators=(",", ":"))
    except Exception as exc:  # Hooks are observational and must never block Hermes.
        print(f"research-tree Hermes hook ignored error: {exc}", file=sys.stderr)
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
