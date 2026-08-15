"""Install the checked-out research-tree skill for supported agent hosts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Iterable, Sequence

from .skill_activation import package_digests


SKILL_NAME = "research-tree"
RESOURCE_RE = re.compile(r"`((?:references|templates|scripts|assets)/[^`\r\n]+)`")
WORKSPACE_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
PROJECTS_DIRECTORY = Path(".research-tree") / "projects"
RUN_DIRECTORIES = (
    "alignment",
    "plans",
    "attempts",
    "sessions",
    "events",
    "checkpoints",
    "logs",
    "deliveries",
)


class SkillSetupError(ValueError):
    """Raised when a skill installation cannot be completed safely."""


def _workspace_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not WORKSPACE_IDENTIFIER_RE.fullmatch(value):
        raise SkillSetupError(f"{label} must be an opaque identifier")
    return value


def _project_root(repository: Path, project_id: str) -> Path:
    root = _absolute(repository)
    return root / PROJECTS_DIRECTORY / _workspace_identifier(project_id, "project_id")


def workspace_paths(
    repository: Path,
    *,
    project_id: str,
    run_id: str,
    session_id: str | None = None,
    require_initialized: bool = False,
) -> dict[str, str]:
    """Return the only local path authority for a project/run descriptor."""
    project_root = _project_root(repository, project_id)
    run_root = project_root / "runs" / _workspace_identifier(run_id, "run_id")
    if require_initialized and not (run_root / "manifest.json").is_file():
        raise SkillSetupError(f"project run is not initialized: {project_id}/{run_id}")
    result = {
        "project_id": project_id,
        "run_id": run_id,
        "project_root": str(project_root),
        "run_root": str(run_root),
    }
    if session_id is not None:
        result["session_id"] = _workspace_identifier(session_id, "session_id")
        result["session_root"] = str(run_root / "sessions" / session_id)
    return result


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def initialize_project_workspace(
    repository: Path,
    *,
    project_id: str,
    run_id: str,
    session_id: str | None = None,
) -> dict[str, str]:
    """Create one durable local project/run tree without host-specific roots."""
    workspace = workspace_paths(repository, project_id=project_id, run_id=run_id, session_id=session_id)
    project_root = Path(workspace["project_root"])
    run_root = Path(workspace["run_root"])
    project_root.mkdir(parents=True, exist_ok=True)
    project_manifest = project_root / "project.json"
    if not project_manifest.exists():
        _atomic_write_text(
            project_manifest,
            json.dumps({"schema": 1, "project_id": project_id}, sort_keys=True) + "\n",
        )
    elif json.loads(project_manifest.read_text(encoding="utf-8")).get("project_id") != project_id:
        raise SkillSetupError(f"project manifest does not match {project_id!r}")
    run_root.mkdir(parents=True, exist_ok=True)
    for name in RUN_DIRECTORIES:
        (run_root / name).mkdir(exist_ok=True)
    run_manifest = run_root / "manifest.json"
    if not run_manifest.exists():
        _atomic_write_text(
            run_manifest,
            json.dumps({"schema": 1, "project_id": project_id, "run_id": run_id}, sort_keys=True) + "\n",
        )
    elif json.loads(run_manifest.read_text(encoding="utf-8")) != {
        "project_id": project_id,
        "run_id": run_id,
        "schema": 1,
    }:
        raise SkillSetupError(f"run manifest does not match {project_id}/{run_id}")
    if session_id is not None:
        Path(workspace["session_root"]).mkdir(parents=True, exist_ok=True)
    return workspace


def _load_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillSetupError(f"project hook configuration is invalid JSON: {path}") from exc
    if not isinstance(loaded, dict):
        raise SkillSetupError(f"project hook configuration must be an object: {path}")
    return loaded


def _hook_template(repository: Path, name: str) -> dict[str, object]:
    try:
        loaded = json.loads((repository / "hooks" / name).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillSetupError(f"hook template is invalid: {name}") from exc
    if not isinstance(loaded, dict) or not isinstance(loaded.get("hooks"), dict):
        raise SkillSetupError(f"hook template has no hooks object: {name}")
    return loaded


def _template_repository() -> Path:
    """Locate bundled templates without requiring the target project checkout."""
    return Path(__file__).resolve().parents[2]


def _configured_entry(entry: object, workspace: dict[str, str]) -> object:
    serialized = json.dumps(entry, separators=(",", ":"))
    if "research-tree-hook" not in serialized:
        return entry
    suffix = (
        f" --project-root {json.dumps(workspace['project_root'])}"
        f" --project-id {workspace['project_id']} --run-id {workspace['run_id']}"
    )
    if isinstance(entry, dict):
        copied = dict(entry)
        if isinstance(copied.get("command"), str):
            copied["command"] += suffix
        if isinstance(copied.get("commandWindows"), str):
            copied["commandWindows"] += suffix
        if isinstance(copied.get("hooks"), list):
            copied["hooks"] = [_configured_entry(item, workspace) for item in copied["hooks"]]
        return copied
    return entry


def _is_owned_entry(entry: object, workspace: dict[str, str]) -> bool:
    serialized = json.dumps(entry, separators=(",", ":"))
    return (
        "research-tree-hook" in serialized
        and f"--project-id {workspace['project_id']}" in serialized
        and f"--run-id {workspace['run_id']}" in serialized
    )


def _merge_hook_config(
    existing: dict[str, object], template: dict[str, object], workspace: dict[str, str]
) -> dict[str, object]:
    merged = dict(existing)
    hooks = existing.get("hooks", {})
    if not isinstance(hooks, dict):
        raise SkillSetupError("project hook configuration hooks must be an object")
    merged_hooks = {event: list(entries) for event, entries in hooks.items() if isinstance(entries, list)}
    if len(merged_hooks) != len(hooks):
        raise SkillSetupError("project hook configuration entries must be lists")
    template_hooks = template["hooks"]
    assert isinstance(template_hooks, dict)
    for event, entries in template_hooks.items():
        assert isinstance(entries, list)
        current = [entry for entry in merged_hooks.get(event, []) if not _is_owned_entry(entry, workspace)]
        current.extend(_configured_entry(entry, workspace) for entry in entries)
        merged_hooks[event] = current
    merged["hooks"] = merged_hooks
    return merged


def _restore_file(path: Path, original: bytes | None) -> None:
    if original is None:
        path.unlink(missing_ok=True)
        return
    _atomic_write_text(path, original.decode("utf-8"))


def bootstrap_project_hooks(repository: Path, workspace: dict[str, str]) -> dict[str, object]:
    """Atomically configure project-local hooks for one initialized run."""
    root = _absolute(repository)
    expected = workspace_paths(
        root,
        project_id=workspace.get("project_id", ""),
        run_id=workspace.get("run_id", ""),
        require_initialized=True,
    )
    if workspace.get("project_root") != expected["project_root"] or workspace.get("run_root") != expected["run_root"]:
        raise SkillSetupError("workspace descriptor does not match initialized project run")
    targets = (
        (root / ".codex" / "hooks.json", "codex.hooks.template.json"),
        (root / ".claude" / "settings.json", "claude-code.settings.template.json"),
    )
    originals = {path: path.read_bytes() if path.exists() else None for path, _ in targets}
    hermes_config = Path(expected["run_root"]) / "hermes-home" / "config.yaml"
    originals[hermes_config] = hermes_config.read_bytes() if hermes_config.exists() else None
    try:
        for path, template_name in targets:
            merged = _merge_hook_config(
                _load_json_object(path), _hook_template(_template_repository(), template_name), expected
            )
            _atomic_write_text(path, json.dumps(merged, indent=2, sort_keys=True) + "\n")
        hermes_text = (_template_repository() / "hooks" / "hermes.config.template.yaml").read_text(encoding="utf-8")
        hermes_text = hermes_text.replace(
            "D:/absolute/path/to/packages/hermes/research-tree/scripts/hermes_runtime_hook.py",
            f"research-tree-hook --host hermes --project-root {json.dumps(expected['project_root'])} --project-id {expected['project_id']} --run-id {expected['run_id']}",
        )
        _atomic_write_text(hermes_config, hermes_text)
    except (OSError, SkillSetupError) as exc:
        for path, original in originals.items():
            _restore_file(path, original)
        if isinstance(exc, SkillSetupError):
            raise
        raise SkillSetupError(str(exc)) from exc
    return {
        "status": "configured",
        "workspace": expected,
        "codex": {"config": str(targets[0][0])},
        "claude": {"config": str(targets[1][0])},
        "hermes": {"config": str(hermes_config), "environment": {"HERMES_HOME": str(hermes_config.parent)}},
    }


@dataclass(frozen=True)
class HostLayout:
    name: str
    package_parts: tuple[str, ...]
    user_parts: tuple[str, ...]
    project_parts: tuple[str, ...] | None
    discovery: str


HOST_LAYOUTS = {
    "codex": HostLayout(
        name="codex",
        package_parts=("packages", "codex", SKILL_NAME),
        user_parts=(".codex", "skills", SKILL_NAME),
        project_parts=(".agents", "skills", SKILL_NAME),
        discovery="Codex Agent Skills user/repository discovery",
    ),
    "claude": HostLayout(
        name="claude",
        package_parts=("packages", "claude-code", SKILL_NAME),
        user_parts=(".claude", "skills", SKILL_NAME),
        project_parts=(".claude", "skills", SKILL_NAME),
        discovery="Claude Code personal/project skill discovery",
    ),
    "hermes": HostLayout(
        name="hermes",
        package_parts=("packages", "hermes", SKILL_NAME),
        user_parts=(".hermes", "skills", SKILL_NAME),
        project_parts=None,
        discovery="Hermes primary skill directory",
    ),
}


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _inside(parent: Path, candidate: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _absolute(path: Path) -> Path:
    """Make a path absolute without following an existing symlink or junction."""
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _lexically_inside(parent: Path, candidate: Path) -> bool:
    try:
        _absolute(candidate).relative_to(_absolute(parent))
    except ValueError:
        return False
    return True


def resolve_target(
    host: str,
    *,
    scope: str,
    home: Path,
    project_root: Path,
    codex_home: Path | None = None,
) -> Path:
    try:
        layout = HOST_LAYOUTS[host]
    except KeyError as exc:
        raise SkillSetupError(f"unsupported host: {host}") from exc

    if scope == "user":
        if host == "codex":
            configured_home = codex_home
            if configured_home is None:
                raw_home = os.environ.get("CODEX_HOME")
                configured_home = Path(raw_home) if raw_home else home / ".codex"
            return configured_home.expanduser() / "skills" / SKILL_NAME
        return home.expanduser().joinpath(*layout.user_parts)
    if scope != "project":
        raise SkillSetupError(f"unsupported scope: {scope}")
    if layout.project_parts is None:
        raise SkillSetupError(
            "Hermes has no native project skill directory; install at user scope "
            "or add the source parent to skills.external_dirs in "
            "~/.hermes/config.yaml"
        )
    return project_root.expanduser().joinpath(*layout.project_parts)


def resolve_package(repository: Path, host: str) -> Path:
    try:
        layout = HOST_LAYOUTS[host]
    except KeyError as exc:
        raise SkillSetupError(f"unsupported host: {host}") from exc
    package = repository.expanduser().resolve().joinpath(*layout.package_parts)
    skill_source = package / "skills" / SKILL_NAME if host == "claude" else package
    if host == "claude":
        manifest = package / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            raise SkillSetupError(
                f"Claude plugin manifest is missing; run python scripts/build_skill_packages.py: {manifest}"
            )
        try:
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SkillSetupError(f"Claude plugin manifest is invalid JSON: {manifest}") from exc
        if not isinstance(metadata, dict) or metadata.get("name") != SKILL_NAME:
            raise SkillSetupError(f"Claude plugin manifest does not name {SKILL_NAME!r}: {manifest}")
    if not (skill_source / "SKILL.md").is_file():
        raise SkillSetupError(f"{host} package is missing; run python scripts/build_skill_packages.py: {package}")
    return package


def resolve_skill_source(repository: Path, host: str) -> Path:
    package = resolve_package(repository, host)
    return package / "skills" / SKILL_NAME if host == "claude" else package


def _read_payload(source: Path) -> tuple[Path, ...]:
    source = source.expanduser().resolve()
    skill_file = source / "SKILL.md"
    if not skill_file.is_file():
        raise SkillSetupError(f"source does not contain SKILL.md: {source}")
    try:
        text = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SkillSetupError("SKILL.md must be UTF-8") from exc
    if not text.startswith("---"):
        raise SkillSetupError("SKILL.md must start with YAML frontmatter")

    relative_files = {Path("SKILL.md")}
    for raw_relative in RESOURCE_RE.findall(text):
        relative = Path(raw_relative)
        candidate = (source / relative).resolve(strict=False)
        if not _inside(source, candidate):
            raise SkillSetupError(f"resource escapes source directory: {relative}")
        if not candidate.is_file():
            raise SkillSetupError(f"referenced resource is missing: {relative}")
        relative_files.add(relative)
    for candidate in source.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(source)
        if "__pycache__" in relative.parts or candidate.suffix == ".pyc":
            continue
        relative_files.add(relative)
    return tuple(sorted(relative_files, key=lambda item: item.as_posix()))


def _same_source(target: Path, source: Path) -> bool:
    if not _lexists(target):
        return False
    try:
        return target.resolve(strict=True) == source.resolve(strict=True)
    except OSError:
        return False


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _same_payload(target: Path, source: Path) -> bool:
    if not target.is_dir() or not source.is_dir():
        return False
    try:
        return package_digests(target) == package_digests(source)
    except (OSError, ValueError):
        return False


def installation_status(
    target: Path,
    source: Path,
) -> str:
    if not _lexists(target):
        return "missing"
    if _same_source(target, source):
        return "current"
    if _is_link_like(target):
        return "unsupported"
    if _same_payload(target, source):
        return "current"
    return "unsupported"


def _create_link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(source, target_is_directory=True)
        return
    except OSError as symlink_error:
        if os.name != "nt":
            raise SkillSetupError(f"could not create skill symlink: {symlink_error}") from symlink_error

    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(target), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SkillSetupError(f"could not create Windows skill junction: {detail}")


def _copy_payload(source: Path, target: Path, payload: Iterable[Path]) -> None:
    target.mkdir(parents=True, exist_ok=False)
    for relative in payload:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)


def _remove_created_target(target: Path, mode: str) -> None:
    if not _lexists(target):
        return
    if mode == "copy":
        shutil.rmtree(target)
        return
    if target.is_symlink():
        target.unlink()
        return
    if os.name == "nt":
        target.rmdir()
        return
    raise SkillSetupError(f"created link is not removable as a link: {target}")


def install_skill(
    hosts: Sequence[str],
    *,
    source: Path,
    scope: str,
    mode: str,
    home: Path,
    project_root: Path,
    codex_home: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    repository = source.expanduser().resolve()
    if mode not in {"link", "copy"}:
        raise SkillSetupError(f"unsupported install mode: {mode}")

    ordered_hosts = tuple(dict.fromkeys(hosts))
    packages = {host: resolve_package(repository, host) for host in ordered_hosts}
    sources = {
        host: package / "skills" / SKILL_NAME if host == "claude" else package for host, package in packages.items()
    }
    payloads = {host: _read_payload(package) for host, package in sources.items()}
    targets = {
        host: _absolute(
            resolve_target(
                host,
                scope=scope,
                home=home,
                project_root=project_root,
                codex_home=codex_home,
            )
        )
        for host in ordered_hosts
    }
    if mode == "link":
        recursive = [host for host, target in targets.items() if _lexically_inside(sources[host], target)]
        if recursive:
            names = ", ".join(recursive)
            raise SkillSetupError(
                f"link target for {names} is inside the source checkout; use --mode copy for a project-scoped install"
            )

    statuses = {host: installation_status(target, sources[host]) for host, target in targets.items()}
    unsupported = [host for host, status in statuses.items() if status == "unsupported"]
    if unsupported:
        details = ", ".join(f"{host}={statuses[host]}:{targets[host]}" for host in unsupported)
        raise SkillSetupError("refusing to modify unsupported user-owned skill installation(s): " + details)

    results: list[dict[str, str]] = []
    created: list[Path] = []
    try:
        for host, target in targets.items():
            status = statuses[host]
            action = "unchanged" if status == "current" else "planned"
            if status == "missing" and not dry_run:
                created.append(target)
                if mode == "link":
                    _create_link(sources[host], target)
                else:
                    _copy_payload(sources[host], target, payloads[host])
                action = "installed"
            results.append(
                {
                    "host": host,
                    "scope": scope,
                    "mode": mode,
                    "target": str(target),
                    "package": str(packages[host]),
                    "skill_source": str(sources[host]),
                    "action": action,
                    "discovery": HOST_LAYOUTS[host].discovery,
                    "payload_files": [item.as_posix() for item in payloads[host]],
                }
            )
    except (OSError, SkillSetupError) as exc:
        for target in reversed(created):
            _remove_created_target(target, mode)
        if isinstance(exc, SkillSetupError):
            raise
        raise SkillSetupError(str(exc)) from exc

    return {
        "repository": str(repository),
        "scope": scope,
        "mode": mode,
        "dry_run": dry_run,
        "installations": results,
    }


def skill_status(
    hosts: Sequence[str],
    *,
    source: Path,
    scope: str,
    home: Path,
    project_root: Path,
    codex_home: Path | None = None,
) -> dict[str, object]:
    repository = source.expanduser().resolve()
    installations = []
    for host in tuple(dict.fromkeys(hosts)):
        package = resolve_package(repository, host)
        skill_source = package / "skills" / SKILL_NAME if host == "claude" else package
        _read_payload(skill_source)
        target = _absolute(
            resolve_target(
                host,
                scope=scope,
                home=home,
                project_root=project_root,
                codex_home=codex_home,
            )
        )
        status = installation_status(target, skill_source)
        installations.append(
            {
                "host": host,
                "scope": scope,
                "target": str(target),
                "package": str(package),
                "skill_source": str(skill_source),
                "status": status,
                "activation_state": "static_ready" if status == "current" else "discovered",
                "live_activation": "unproven",
                "discovery": HOST_LAYOUTS[host].discovery,
            }
        )
    return {
        "repository": str(repository),
        "scope": scope,
        "installations": installations,
    }


def _selected_hosts(raw_hosts: Sequence[str] | None) -> tuple[str, ...]:
    if not raw_hosts or "all" in raw_hosts:
        return tuple(HOST_LAYOUTS)
    return tuple(dict.fromkeys(raw_hosts))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-tree-setup",
        description="Install isolated research-tree packages for Codex, Claude Code, or Hermes.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("install", "status"):
        child = commands.add_parser(command)
        child.add_argument(
            "--host",
            action="append",
            choices=("all", *HOST_LAYOUTS),
            help="repeat for multiple hosts; defaults to all",
        )
        child.add_argument("--scope", choices=("user", "project"), default="user")
        child.add_argument("--source", type=Path, default=Path.cwd())
        child.add_argument("--home", type=Path, default=Path.home())
        child.add_argument(
            "--codex-home",
            type=Path,
            help="override CODEX_HOME for a user-scoped Codex install",
        )
        child.add_argument("--project-root", type=Path, default=Path.cwd())
    install = commands.choices["install"]
    install.add_argument("--mode", choices=("link", "copy"), default="link")
    install.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    hosts = _selected_hosts(arguments.host)
    try:
        if arguments.command == "install":
            result = install_skill(
                hosts,
                source=arguments.source,
                scope=arguments.scope,
                mode=arguments.mode,
                home=arguments.home,
                project_root=arguments.project_root,
                codex_home=arguments.codex_home,
                dry_run=arguments.dry_run,
            )
        else:
            result = skill_status(
                hosts,
                source=arguments.source,
                scope=arguments.scope,
                home=arguments.home,
                project_root=arguments.project_root,
                codex_home=arguments.codex_home,
            )
    except SkillSetupError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
