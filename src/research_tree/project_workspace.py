"""Durable, project-scoped local workspace authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
from typing import Any
import re


PROJECTS_ROOT = Path(".research-tree") / "projects"
RUN_DIRECTORIES = ("alignment", "plans", "attempts", "sessions", "events", "checkpoints", "logs", "deliveries", "legacy")
RUN_BOUND_LEGACY_ROOTS = (
    (Path(".research-tree-native"), "native"),
    (Path(".research-tree-alignment"), "alignment"),
    (Path(".research-tree-hermes"), "hermes"),
)
UNATTRIBUTED_LEGACY_ROOTS = (Path(".research-tree-hooks"),)
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
HOST_HOOK_EVENTS = {
    "codex": ("SessionStart", "SessionEnd", "PreCompact", "PostCompact", "SubagentStart", "SubagentStop", "Stop"),
    "claude": ("SessionStart", "SessionEnd", "PreCompact", "SubagentStop", "Stop"),
    "hermes": ("on_session_start", "on_session_end", "on_session_finalize", "on_session_reset", "subagent_start", "subagent_stop", "post_tool_call"),
}


class ProjectWorkspaceError(ValueError):
    """Raised when local project workspace authority is unsafe or ambiguous."""


@dataclass(frozen=True, slots=True)
class ProjectRunWorkspace:
    project_root: Path
    run_root: Path
    manifest_path: Path
    project_id: str
    run_id: str


@dataclass(frozen=True, slots=True)
class LifecycleHookProbe:
    status: str
    record_path: Path | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ProjectWorkspaceError(f"invalid {label}")
    return value


def _workspace(repository: Path, project_id: str, run_id: str) -> ProjectRunWorkspace:
    root = repository.expanduser().resolve()
    project_root = root / PROJECTS_ROOT / project_id
    run_root = project_root / "runs" / run_id
    return ProjectRunWorkspace(project_root, run_root, run_root / "manifest.json", project_id, run_id)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_manifest(workspace: ProjectRunWorkspace) -> dict[str, Any]:
    try:
        payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectWorkspaceError("project run manifest is invalid") from error
    if not isinstance(payload, dict) or payload.get("project_id") != workspace.project_id or payload.get("run_id") != workspace.run_id:
        raise ProjectWorkspaceError("project run manifest identity does not match arguments")
    return payload


def _assert_no_unattributed_legacy_root(repository: Path) -> None:
    present = [str(path) for path in UNATTRIBUTED_LEGACY_ROOTS if (repository / path).exists()]
    if present:
        joined = ", ".join(present)
        raise ProjectWorkspaceError(f"explicit migration is required for unattributed legacy root(s): {joined}")


def _migrate_legacy_roots(repository: Path, workspace: ProjectRunWorkspace) -> list[str]:
    _assert_no_unattributed_legacy_root(repository)
    staged: list[tuple[Path, Path]] = []
    try:
        for legacy_root, destination_name in RUN_BOUND_LEGACY_ROOTS:
            source = repository / legacy_root / workspace.run_id
            if not source.exists():
                continue
            destination = workspace.run_root / "legacy" / destination_name
            if destination.exists():
                raise ProjectWorkspaceError(f"legacy destination already exists: {destination_name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            staged.append((source, destination))
    except (OSError, ProjectWorkspaceError):
        for source, destination in reversed(staged):
            if destination.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
        raise
    return [source.relative_to(repository).as_posix() for source, _destination in staged]


def initialize_project_run(repository: Path, *, project_id: str, run_id: str, host: str) -> ProjectRunWorkspace:
    project_id = _identifier(project_id, "project_id")
    run_id = _identifier(run_id, "run_id")
    if host not in {"codex", "claude", "hermes"}:
        raise ProjectWorkspaceError("unsupported host")
    workspace = _workspace(repository, project_id, run_id)
    if workspace.manifest_path.exists():
        manifest = _load_manifest(workspace)
        manifest["hosts"] = sorted(set(manifest.get("hosts", ())).union({host}))
        manifest["updated_at"] = _now()
        _atomic_json(workspace.manifest_path, manifest)
        return workspace
    workspace.project_root.mkdir(parents=True, exist_ok=True)
    workspace.run_root.mkdir(parents=True, exist_ok=True)
    for directory in RUN_DIRECTORIES:
        (workspace.run_root / directory).mkdir(exist_ok=True)
    migrated = _migrate_legacy_roots(repository.expanduser().resolve(), workspace)
    _atomic_json(
        workspace.manifest_path,
        {
            "schema": 1,
            "project_id": project_id,
            "run_id": run_id,
            "hosts": [host],
            "created_at": _now(),
            "updated_at": _now(),
            "migrated_legacy_roots": migrated,
            "capabilities": {"lifecycle_hooks": "unknown"},
        },
    )
    return workspace


def resume_project_run(repository: Path, *, project_id: str, run_id: str, host: str) -> ProjectRunWorkspace:
    return initialize_project_run(repository, project_id=project_id, run_id=run_id, host=host)


def write_installed_hook_launcher(workspace: ProjectRunWorkspace) -> Path:
    """Write a self-contained launcher that accepts one hook JSON object."""
    launcher = workspace.run_root / "hooks" / "research_tree_lifecycle_hook.py"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    event_directory = workspace.run_root / "events"
    script = f'''#!/usr/bin/env {Path(sys.executable).name}
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

EVENT_DIRECTORY = Path({str(event_directory)!r})
PROJECT_ID = {workspace.project_id!r}
RUN_ID = {workspace.run_id!r}
payload = json.load(sys.stdin)
if not isinstance(payload, dict) or not isinstance(payload.get("hook_event_name"), str):
    raise SystemExit(2)
record = {{"schema": 1, "project_id": PROJECT_ID, "run_id": RUN_ID, "event": payload["hook_event_name"], "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}}
EVENT_DIRECTORY.mkdir(parents=True, exist_ok=True)
path = EVENT_DIRECTORY / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + secrets.token_hex(8) + ".json")
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    json.dump(record, handle, sort_keys=True)
print("{{}}")
'''
    launcher.write_text(script, encoding="utf-8")
    launcher.chmod(0o700)
    return launcher


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectWorkspaceError(f"project hook configuration is invalid: {path}") from error
    if not isinstance(payload, dict):
        raise ProjectWorkspaceError(f"project hook configuration must be an object: {path}")
    return payload


def _restore_file(path: Path, contents: bytes | None) -> None:
    if contents is None:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.restore")
    try:
        temporary.write_bytes(contents)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _command(launcher: Path) -> str:
    return shlex.join((sys.executable, str(launcher)))


def _owned_entry(entry: object, launcher: Path) -> bool:
    return str(launcher) in json.dumps(entry, sort_keys=True)


def _host_hook_entry(host: str, event: str, launcher: Path) -> dict[str, Any]:
    command = _command(launcher)
    hook: dict[str, Any] = {"type": "command", "command": command, "timeout": 10}
    if host == "codex":
        hook["commandWindows"] = command
        hook["statusMessage"] = "Recording research lifecycle event"
    return {"hooks": [hook]}


def _merged_host_hooks(existing: dict[str, Any], *, host: str, launcher: Path) -> dict[str, Any]:
    hooks = existing.get("hooks", {})
    if not isinstance(hooks, dict) or not all(isinstance(entries, list) for entries in hooks.values()):
        raise ProjectWorkspaceError("project hook configuration hooks must map events to lists")
    merged = dict(existing)
    merged_hooks = {event: [entry for entry in entries if not _owned_entry(entry, launcher)] for event, entries in hooks.items()}
    for event in HOST_HOOK_EVENTS[host]:
        merged_hooks.setdefault(event, []).append(_host_hook_entry(host, event, launcher))
    merged["hooks"] = merged_hooks
    return merged


def _render_hermes_config(launcher: Path) -> str:
    lines = ["hooks:"]
    command = _command(launcher)
    for event in HOST_HOOK_EVENTS["hermes"]:
        lines.extend((f"  {event}:", f"    - command: {json.dumps(command)}", "      timeout: 10"))
    lines.extend(("", "hooks_auto_accept: false", ""))
    return "\n".join(lines)


def install_project_hooks(repository: Path, workspace: ProjectRunWorkspace) -> dict[str, Any]:
    """Atomically install run-bound, dependency-free hooks in project-local config."""
    root = repository.expanduser().resolve()
    expected = _workspace(root, workspace.project_id, workspace.run_id)
    if workspace != expected or not workspace.manifest_path.is_file():
        raise ProjectWorkspaceError("workspace is not an initialized project run")
    launcher = write_installed_hook_launcher(workspace)
    targets = ((root / ".codex" / "hooks.json", "codex"), (root / ".claude" / "settings.json", "claude"))
    hermes_config = workspace.run_root / "hermes-home" / "config.yaml"
    originals = {path: path.read_bytes() if path.exists() else None for path, _host in targets}
    originals[hermes_config] = hermes_config.read_bytes() if hermes_config.exists() else None
    try:
        for path, host in targets:
            _atomic_json(path, _merged_host_hooks(_read_json_object(path), host=host, launcher=launcher))
        hermes_config.parent.mkdir(parents=True, exist_ok=True)
        temporary = hermes_config.with_name(f".{hermes_config.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(_render_hermes_config(launcher), encoding="utf-8")
            os.replace(temporary, hermes_config)
        finally:
            temporary.unlink(missing_ok=True)
    except (OSError, ProjectWorkspaceError):
        for path, contents in originals.items():
            _restore_file(path, contents)
        raise
    return {
        "status": "configured",
        "launcher": str(launcher),
        "codex": {"config": str(targets[0][0])},
        "claude": {"config": str(targets[1][0])},
        "hermes": {"config": str(hermes_config), "environment": {"HERMES_HOME": str(hermes_config.parent)}},
    }


def probe_lifecycle_hook(workspace: ProjectRunWorkspace, *, launcher: Path | None) -> LifecycleHookProbe:
    manifest = _load_manifest(workspace)
    if launcher is None or not launcher.is_file():
        manifest["capabilities"]["lifecycle_hooks"] = "unavailable"
        manifest["updated_at"] = _now()
        _atomic_json(workspace.manifest_path, manifest)
        return LifecycleHookProbe("unavailable", None)
    completed = subprocess.run(
        [sys.executable, str(launcher)],
        input=json.dumps({"hook_event_name": "probe"}),
        text=True,
        capture_output=True,
        check=False,
    )
    records = sorted((workspace.run_root / "events").glob("*.json"))
    if completed.returncode != 0 or not records:
        manifest["capabilities"]["lifecycle_hooks"] = "unavailable"
        manifest["updated_at"] = _now()
        _atomic_json(workspace.manifest_path, manifest)
        return LifecycleHookProbe("unavailable", None)
    record_path = records[-1]
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        record = {}
    if record.get("project_id") != workspace.project_id or record.get("run_id") != workspace.run_id:
        manifest["capabilities"]["lifecycle_hooks"] = "unavailable"
        manifest["updated_at"] = _now()
        _atomic_json(workspace.manifest_path, manifest)
        return LifecycleHookProbe("unavailable", None)
    manifest["capabilities"]["lifecycle_hooks"] = "available"
    manifest["updated_at"] = _now()
    _atomic_json(workspace.manifest_path, manifest)
    return LifecycleHookProbe("available", record_path)


__all__ = [
    "LifecycleHookProbe",
    "ProjectRunWorkspace",
    "ProjectWorkspaceError",
    "initialize_project_run",
    "install_project_hooks",
    "probe_lifecycle_hook",
    "resume_project_run",
    "write_installed_hook_launcher",
]
