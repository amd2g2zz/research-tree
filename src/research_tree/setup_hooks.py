"""Install and inspect setup-managed global lifecycle hooks."""

from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

HOST_HOOK_EVENTS = {
    "codex": ("SessionStart", "SessionEnd", "PreCompact", "PostCompact", "SubagentStart", "SubagentStop", "Stop"),
    "claude": ("SessionStart", "SessionEnd", "PreCompact", "SubagentStop", "PostToolUse", "Stop"),
    "hermes": (
        "on_session_start",
        "on_session_end",
        "on_session_finalize",
        "on_session_reset",
        "subagent_start",
        "subagent_stop",
        "post_tool_call",
    ),
}
HERMES_MANAGED_MARKER = "# research-tree-setup managed"


class SetupHookError(ValueError):
    """Raised when global hook configuration cannot be updated safely."""


@dataclass(frozen=True, slots=True)
class HookPlan:
    host: str
    path: Path
    original: bytes | None
    rendered: bytes
    prior_status: str


def _codex_root(home: Path, codex_home: Path | None) -> Path:
    if codex_home is not None:
        return codex_home.expanduser()
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else home.expanduser() / ".codex"


def hook_config_path(host: str, *, home: Path, codex_home: Path | None = None) -> Path:
    if host == "codex":
        return _codex_root(home, codex_home) / "hooks.json"
    if host == "claude":
        return home.expanduser() / ".claude" / "settings.json"
    if host == "hermes":
        return home.expanduser() / ".hermes" / "config.yaml"
    raise SetupHookError(f"unsupported hook host: {host}")


def _read_json_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SetupHookError(f"hook configuration is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise SetupHookError(f"hook configuration must be a JSON object: {path}")
    hooks = payload.get("hooks", {})
    if not isinstance(hooks, dict) or not all(isinstance(entries, list) for entries in hooks.values()):
        raise SetupHookError(f"hook configuration hooks must map events to lists: {path}")
    return payload


def _hook_command(repository: Path, host: str, event: str) -> str:
    return shlex.join(
        (
            "uv",
            "run",
            "--project",
            str(repository),
            "--frozen",
            "research-tree-hook",
            "--host",
            host,
            "--event",
            event,
        )
    )


def _json_hook_entry(repository: Path, host: str, event: str) -> dict[str, Any]:
    command = _hook_command(repository, host, event)
    hook: dict[str, Any] = {"type": "command", "command": command, "timeout": 10}
    if host == "codex":
        hook["commandWindows"] = command
        hook["statusMessage"] = "Recording Research Tree lifecycle event"
    return {"hooks": [hook]}


def _entry_commands(entry: object) -> tuple[str, ...]:
    if not isinstance(entry, dict):
        return ()
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        return ()
    commands = []
    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        for field in ("command", "commandWindows"):
            value = hook.get(field)
            if isinstance(value, str):
                commands.append(value)
    return tuple(commands)


def _owned_json_entry(entry: object, host: str) -> bool:
    return any("research-tree-hook" in command and f"--host {host}" in command for command in _entry_commands(entry))


def _merge_json_hooks(existing: dict[str, Any], *, repository: Path, host: str) -> dict[str, Any]:
    hooks = existing.get("hooks", {})
    merged = dict(existing)
    merged_hooks = {
        event: [entry for entry in entries if not _owned_json_entry(entry, host)] for event, entries in hooks.items()
    }
    for event in HOST_HOOK_EVENTS[host]:
        merged_hooks.setdefault(event, []).append(_json_hook_entry(repository, host, event))
    merged["hooks"] = merged_hooks
    return merged


def _json_hook_status(existing: dict[str, Any], *, repository: Path, host: str) -> str:
    hooks = existing.get("hooks", {})
    owned = {event: [entry for entry in entries if _owned_json_entry(entry, host)] for event, entries in hooks.items()}
    owned_count = sum(len(entries) for entries in owned.values())
    if owned_count == 0:
        return "missing"
    expected_events = HOST_HOOK_EVENTS[host]
    if owned_count != len(expected_events):
        return "conflict"
    for event in expected_events:
        if owned.get(event) != [_json_hook_entry(repository, host, event)]:
            return "conflict"
    if any(entries for event, entries in owned.items() if event not in expected_events):
        return "conflict"
    return "current"


def _yaml_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _hermes_item(command: str, event: str) -> list[str]:
    lines = [f"    {HERMES_MANAGED_MARKER}"]
    if event == "post_tool_call":
        lines.extend(('    - matcher: "^delegate_task$"', f"      command: {_yaml_single_quote(command)}"))
    else:
        lines.append(f"    - command: {_yaml_single_quote(command)}")
    lines.append("      timeout: 10")
    return lines


def _top_level_key(line: str) -> bool:
    return bool(line) and not line[0].isspace() and not line.lstrip().startswith("#")


def _remove_managed_hermes_items(lines: list[str], launcher: Path) -> list[str]:
    cleaned: list[str] = []
    index = 0
    while index < len(lines):
        marker = lines[index].strip() == HERMES_MANAGED_MARKER
        item_start = index + 1 if marker else index
        if item_start >= len(lines) or not lines[item_start].startswith("    - "):
            if not marker:
                cleaned.append(lines[index])
            index += 1
            continue
        item_end = item_start + 1
        while item_end < len(lines) and (lines[item_end].startswith("      ") or not lines[item_end].strip()):
            item_end += 1
        owned = marker or any(str(launcher) in line for line in lines[item_start:item_end])
        if owned:
            index = item_end
            continue
        cleaned.extend(lines[index:item_end])
        index = item_end
    return cleaned


def _merge_hermes_hooks(existing: str, *, launcher: Path) -> str:
    lines = existing.splitlines()
    malformed = [line for line in lines if line.startswith("hooks:") and line.strip() != "hooks:"]
    if malformed:
        raise SetupHookError("hook configuration has an unsupported inline hooks value")
    hook_indexes = [index for index, line in enumerate(lines) if line.strip() == "hooks:" and line == line.lstrip()]
    if len(hook_indexes) > 1:
        raise SetupHookError("hook configuration contains duplicate top-level hooks sections")

    if hook_indexes:
        start = hook_indexes[0]
        end = start + 1
        while end < len(lines) and not _top_level_key(lines[end]):
            end += 1
        before = lines[: start + 1]
        body = _remove_managed_hermes_items(lines[start + 1 : end], launcher)
        after = lines[end:]
    else:
        before = list(lines)
        if before and before[-1].strip():
            before.append("")
        before.append("hooks:")
        body = []
        after = []

    event_indexes: dict[str, int] = {}
    for index, line in enumerate(body):
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            event = line.strip()[:-1]
            if event in event_indexes:
                raise SetupHookError(f"hook configuration contains duplicate Hermes event: {event}")
            event_indexes[event] = index

    command = shlex.join((sys.executable, str(launcher)))
    for event in HOST_HOOK_EVENTS["hermes"]:
        event_indexes = {
            line.strip()[:-1]: index
            for index, line in enumerate(body)
            if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":")
        }
        if event not in event_indexes:
            body.append(f"  {event}:")
            body.extend(_hermes_item(command, event))
            continue
        insert_at = event_indexes[event] + 1
        while insert_at < len(body) and not (
            body[insert_at].startswith("  ") and not body[insert_at].startswith("    ")
        ):
            insert_at += 1
        body[insert_at:insert_at] = _hermes_item(command, event)

    if not any(line.startswith("hooks_auto_accept:") for line in lines):
        if after and after[0].strip():
            after.insert(0, "")
        after.insert(0, "hooks_auto_accept: false")
    rendered = before + body + after
    return "\n".join(rendered).rstrip() + "\n"


def _hermes_hook_status(existing: str, *, launcher: Path) -> str:
    if HERMES_MANAGED_MARKER not in existing:
        return "conflict" if str(launcher) in existing else "missing"
    return "current" if _merge_hermes_hooks(existing, launcher=launcher) == existing else "conflict"


def _read_hermes_config(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SetupHookError(f"hook configuration is not valid UTF-8: {path}") from exc


def plan_setup_hooks(
    hosts: Sequence[str],
    *,
    repository: Path,
    home: Path,
    codex_home: Path | None,
    targets: dict[str, Path],
) -> tuple[HookPlan, ...]:
    plans = []
    for host in hosts:
        path = hook_config_path(host, home=home, codex_home=codex_home)
        original = path.read_bytes() if path.exists() else None
        if host in {"codex", "claude"}:
            existing = _read_json_config(path)
            prior_status = _json_hook_status(existing, repository=repository, host=host)
            rendered = (
                json.dumps(_merge_json_hooks(existing, repository=repository, host=host), sort_keys=True) + "\n"
            ).encode()
        else:
            existing_text = _read_hermes_config(path)
            launcher = targets[host] / "scripts" / "hermes_runtime_hook.py"
            prior_status = _hermes_hook_status(existing_text, launcher=launcher)
            rendered = _merge_hermes_hooks(existing_text, launcher=launcher).encode()
        plans.append(HookPlan(host, path, original, rendered, prior_status))
    return tuple(plans)


def _restore(path: Path, contents: bytes | None) -> None:
    if contents is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.restore")
    try:
        temporary.write_bytes(contents)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install_setup_hooks(plans: Sequence[HookPlan], *, dry_run: bool) -> list[dict[str, object]]:
    if not dry_run:
        written: list[HookPlan] = []
        try:
            for plan in plans:
                if plan.original == plan.rendered:
                    continue
                plan.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = plan.path.with_name(f".{plan.path.name}.{os.getpid()}.tmp")
                try:
                    temporary.write_bytes(plan.rendered)
                    os.replace(temporary, plan.path)
                finally:
                    temporary.unlink(missing_ok=True)
                written.append(plan)
        except OSError as exc:
            for plan in reversed(written):
                _restore(plan.path, plan.original)
            raise SetupHookError(f"could not install hook configuration: {exc}") from exc
    return [
        {
            "host": plan.host,
            "scope": "global",
            "config": str(plan.path),
            "status": "current",
            "previous_status": plan.prior_status,
            "action": "planned" if dry_run else ("unchanged" if plan.original == plan.rendered else "installed"),
            "events": list(HOST_HOOK_EVENTS[plan.host]),
        }
        for plan in plans
    ]


def setup_hook_status(
    host: str,
    *,
    repository: Path,
    home: Path,
    codex_home: Path | None,
    target: Path,
) -> dict[str, str]:
    path = hook_config_path(host, home=home, codex_home=codex_home)
    try:
        if host in {"codex", "claude"}:
            status = _json_hook_status(_read_json_config(path), repository=repository, host=host)
        else:
            launcher = target / "scripts" / "hermes_runtime_hook.py"
            status = _hermes_hook_status(_read_hermes_config(path), launcher=launcher)
    except SetupHookError:
        return {"status": "conflict", "reason": "hook_config_invalid", "config": str(path)}
    reason = {"current": "hooks_current", "missing": "hooks_missing", "conflict": "hooks_mismatch"}[status]
    return {"status": status, "reason": reason, "config": str(path)}


__all__ = [
    "HookPlan",
    "SetupHookError",
    "hook_config_path",
    "install_setup_hooks",
    "plan_setup_hooks",
    "setup_hook_status",
]
