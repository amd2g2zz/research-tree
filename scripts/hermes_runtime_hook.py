#!/usr/bin/env python3
"""Fail-open Hermes wake-up hook with no research-state authority."""

from __future__ import annotations

import json
from pathlib import Path
import sys
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


def _bounded_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("hook payload exceeds limit")
    value = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    if not isinstance(value, dict):
        raise ValueError("hook payload must be an object")
    return value


def _touch_wakeup(payload: dict[str, Any]) -> None:
    event = payload.get("hook_event_name")
    if event not in EVENTS:
        if event is None:
            return
        raise ValueError("unsupported hook event")
    if event == "post_tool_call" and payload.get("tool_name") != "delegate_task":
        return
    raw_workspace = payload.get("cwd")
    if not isinstance(raw_workspace, str) or not raw_workspace:
        return
    target = (
        Path(raw_workspace).resolve()
        / ".research-tree"
        / "host-wakeups"
        / "hermes.signal"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=True)


def main() -> int:
    try:
        payload = _bounded_payload()
        _touch_wakeup(payload)
        # The marker is an optional wake-up only. Canonical recovery queries a
        # fresh host snapshot, so a skipped or failed hook cannot create a gap.
    except Exception as exc:  # The host contract is explicitly fail-open.
        print(f"research-tree Hermes hook ignored error: {type(exc).__name__}", file=sys.stderr)
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
