"""Install the checked-out research-tree skill for supported agent hosts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .setup_hooks import SetupHookError, install_setup_hooks, plan_setup_hooks, setup_hook_status
from .skill_activation import package_digests

SKILL_NAME = "research-tree"
RESOURCE_RE = re.compile(r"`((?:references|templates|scripts|assets)/[^`\r\n]+)`")


class SkillSetupError(ValueError):
    """Raised when a skill installation cannot be completed safely."""


@dataclass(frozen=True)
class HostLayout:
    name: str
    package_parts: tuple[str, ...]
    user_parts: tuple[str, ...]
    project_parts: tuple[str, ...] | None
    discovery: str


HERMES_DEPENDENCY_SCHEMA = 1
# Pinned against the upstream artifact: anysearch-ai/anysearch-skill tag
# v2.1.0 = 6ff6aa958ad9747659d669b5e9984f07c896f2aa. The digest covers every
# tracked payload file in sorted order (name\0 content\0 per file).
ANYSEARCH_PINNED_SHA256 = "f06c1a94a0cf8eca345cde609e62deb47907cb3b24889a0a37f5e1fdd0279d37"
ANYSEARCH_PAYLOAD_FILES = (
    ".env.example",
    ".gitignore",
    "README.md",
    "SKILL.md",
    "runtime.conf.example",
    "scripts/anysearch_cli.js",
    "scripts/anysearch_cli.ps1",
    "scripts/anysearch_cli.py",
    "scripts/anysearch_cli.sh",
    "scripts/generate.py",
    "scripts/shared/constants.json",
    "scripts/shared/doc_spec.md",
)
ANYSEARCH_SOURCE_REPO = "https://github.com/anysearch-ai/anysearch-skill.git"


def hermes_dependency_manifest() -> dict[str, object]:
    """Return the pinned run-local Hermes dependency manifest."""

    return {
        "schema": HERMES_DEPENDENCY_SCHEMA,
        "dependencies": {
            "anysearch": {
                "version": "2.1.0",
                "revision": "6ff6aa958ad9747659d669b5e9984f07c896f2aa",
                "install_path": "skills/anysearch",
                "payload_files": list(ANYSEARCH_PAYLOAD_FILES),
                "payload_sha256": ANYSEARCH_PINNED_SHA256,
            }
        },
    }


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


def _payload_digest(root: Path) -> str | None:
    try:
        return package_digests(root)["package_digest"]
    except (OSError, ValueError):
        return None


def _installation_status_detail(target: Path, source: Path) -> tuple[str, str, str | None, str | None]:
    if not _lexists(target):
        return "missing", "target_missing", _payload_digest(source), None
    if _same_source(target, source):
        source_digest = _payload_digest(source)
        return "current", "link_target_current", source_digest, source_digest
    if _is_link_like(target):
        return "conflict", "link_target_mismatch", None, None
    source_digest = _payload_digest(source)
    if not target.is_dir():
        return "conflict", "target_not_directory", source_digest, None
    try:
        _read_payload(target)
    except SkillSetupError as error:
        reason = "missing_referenced_resource" if "referenced resource is missing" in str(error) else "legacy_payload"
        return "conflict", reason, source_digest, _payload_digest(target)
    target_digest = _payload_digest(target)
    if source_digest is not None and target_digest == source_digest:
        return "current", "payload_digest_match", source_digest, target_digest
    return "conflict", "payload_digest_mismatch", source_digest, target_digest


def installation_status(
    target: Path,
    source: Path,
) -> str:
    return _installation_status_detail(target, source)[0]


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
    conflicts = [host for host, status in statuses.items() if status == "conflict"]
    if conflicts:
        details = ", ".join(f"{host}={statuses[host]}:{targets[host]}" for host in conflicts)
        raise SkillSetupError("refusing to modify conflicting user-owned skill installation(s): " + details)

    try:
        hook_plans = plan_setup_hooks(
            ordered_hosts,
            repository=repository,
            home=home,
            codex_home=codex_home,
            targets=targets,
        )
    except (OSError, SetupHookError) as exc:
        raise SkillSetupError(str(exc)) from exc

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
        hooks = install_setup_hooks(hook_plans, dry_run=dry_run)
    except (OSError, SkillSetupError, SetupHookError) as exc:
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
        "hooks": hooks,
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
        status, reason, source_digest, target_digest = _installation_status_detail(target, skill_source)
        hook = setup_hook_status(
            host,
            repository=repository,
            home=home,
            codex_home=codex_home,
            target=target,
        )
        overall_status = status if status != "current" else hook["status"]
        overall_reason = reason if status != "current" or hook["status"] == "current" else hook["reason"]
        installations.append(
            {
                "host": host,
                "scope": scope,
                "target": str(target),
                "package": str(package),
                "skill_source": str(skill_source),
                "status": overall_status,
                "reason": overall_reason,
                "skill_status": status,
                "skill_reason": reason,
                "hook_status": hook["status"],
                "hook_reason": hook["reason"],
                "hook_config": hook["config"],
                "source_payload_digest": source_digest,
                "target_payload_digest": target_digest,
                "activation_state": "static_ready" if overall_status == "current" else "discovered",
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


def _dependency_payload_digest(root: Path, payload_files: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for name in payload_files:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / name).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def install_hermes_dependencies(*, home: Path, source_root: Path | None = None) -> dict[str, object]:
    """Install pinned run-local Hermes dependencies before Hermes starts.

    Fail closed when the payload at ``source_root`` does not match the pinned
    manifest revision or an already-installed dependency drifted.
    """

    manifest = hermes_dependency_manifest()
    resolved_home = _absolute(home)
    dependencies: dict[str, dict[str, object]] = {}
    for name, spec in manifest["dependencies"].items():
        assert isinstance(spec, dict)
        install_root = resolved_home / str(spec["install_path"])
        payload_files = tuple(str(item) for item in spec["payload_files"])
        pinned_digest = str(spec["payload_sha256"])
        source = _absolute(source_root / "skills" / name) if source_root else None
        if source is not None:
            missing = [item for item in payload_files if not (source / item).is_file()]
            if missing:
                raise SkillSetupError(f"{name} source is missing pinned payload files: {', '.join(missing)}")
            source_digest = _dependency_payload_digest(source, payload_files)
            if source_digest != pinned_digest:
                raise SkillSetupError(
                    f"{name} source payload digest {source_digest} does not match the pinned manifest digest"
                )
        if install_root.is_dir():
            installed_digest = _dependency_payload_digest(install_root, payload_files)
        elif source is not None:
            installed_digest = None
        else:
            raise SkillSetupError(f"{name} is not installed and no source was provided")
        if source is not None:
            if installed_digest is not None and installed_digest != pinned_digest:
                raise SkillSetupError(
                    f"{name} payload drift: installed dependency does not match the pinned manifest digest"
                )
            if not install_root.exists():
                install_root.mkdir(parents=True)
                for item in payload_files:
                    destination = install_root / item
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source / item, destination)
                installed_digest = _dependency_payload_digest(install_root, payload_files)
        dependencies[name] = {
            "version": spec["version"],
            "revision": spec["revision"],
            "status": "current",
            "payload_sha256": installed_digest,
        }
    return {
        "home": str(resolved_home),
        "status": "installed",
        "manifest_schema": HERMES_DEPENDENCY_SCHEMA,
        "dependencies": dependencies,
    }


def hermes_dependency_status(*, home: Path) -> dict[str, object]:
    """Report installed dependency revisions without mutating anything."""

    manifest = hermes_dependency_manifest()
    resolved_home = _absolute(home)
    dependencies: dict[str, dict[str, object]] = {}
    for name, spec in manifest["dependencies"].items():
        assert isinstance(spec, dict)
        install_root = resolved_home / str(spec["install_path"])
        payload_files = tuple(str(item) for item in spec["payload_files"])
        if install_root.is_dir() and all((install_root / item).is_file() for item in payload_files):
            dependencies[name] = {
                "version": spec["version"],
                "revision": spec["revision"],
                "status": "current",
                "payload_sha256": _dependency_payload_digest(install_root, payload_files),
            }
        else:
            dependencies[name] = {"version": spec["version"], "revision": spec["revision"], "status": "missing"}
    return {
        "home": str(resolved_home),
        "manifest_schema": HERMES_DEPENDENCY_SCHEMA,
        "dependencies": dependencies,
    }


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
    install.add_argument(
        "--hermes-dependency-source",
        type=Path,
        help="directory holding pinned run-local Hermes dependency payloads",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    hosts = _selected_hosts(arguments.host)
    try:
        dependency_result: dict[str, object] | None = None
        if "hermes" in hosts and getattr(arguments, "hermes_dependency_source", None):
            hermes_home = arguments.home / ".hermes"
            if arguments.command == "install" and not arguments.dry_run:
                dependency_result = install_hermes_dependencies(
                    home=hermes_home, source_root=arguments.hermes_dependency_source
                )
            else:
                dependency_result = hermes_dependency_status(home=hermes_home)
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
    if dependency_result is not None and isinstance(result, dict):
        result["hermes_dependencies"] = dependency_result
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def hermes_external_dirs_snippet(*, source_parent: Path, config_path: Path | None = None) -> dict[str, object]:
    """Issue #328: machine-readable, idempotent Hermes external_dirs snippet.

    The snippet is idempotent — re-apply yields the same config — and never
    overwrites unrelated keys.  Returns a dict with `yaml`, `path`, and `idempotent`
    fields; consumers apply via their existing config-merge path.
    """

    normalized = source_parent.expanduser().resolve()
    snippet = f"skills:\n  external_dirs:\n    - {normalized.as_posix()}\n"
    return {
        "yaml": snippet,
        "path": str((config_path or Path("~/.hermes/config.yaml")).expanduser()),
        "idempotent": True,
        "source_parent": str(normalized),
    }


def plan_heterogeneous_install(
    hosts: Sequence[str],
    *,
    source: Path,
    scope: str,
    home: Path,
    project_root: Path,
    codex_home: Path | None = None,
    dry_run: bool = True,
) -> dict[str, object]:
    """Issue #328: per-host plan; unsupported combinations become skipped entries, not exceptions.

    Returns a dict with `entries` (one per host, in order) and `aggregate_ready` (bool).
    Each entry carries: host, scope, mode, target, package, skill_source, action
    (install|skipped|current|conflict), discovery, rollback_boundary (path), required_config.
    """

    if scope not in {"user", "project"}:
        raise SkillSetupError(f"unsupported scope: {scope}")
    repository = source.expanduser().resolve()
    home_resolved = home.expanduser().resolve()
    project_resolved = project_root.expanduser().resolve()

    by_host: dict[str, dict[str, object]] = {}
    snippet_emitted = False
    for host in dict.fromkeys(hosts):
        layout = HOST_LAYOUTS.get(host)
        if layout is None:
            entry = {
                "host": host,
                "scope": scope,
                "mode": "n/a",
                "target": "n/a",
                "package": str(_resolve_package(repository, host)),
                "skill_source": "n/a",
                "action": "skipped",
                "discovery": "host not in registry",
                "rollback_boundary": "n/a",
                "required_config": f"unsupported host: {host}",
                "reason": "unsupported host",
            }
            by_host[host] = entry
            continue
        if scope == "project" and layout.project_parts is None:
            entry = {
                "host": host,
                "scope": scope,
                "mode": "n/a",
                "target": "n/a",
                "package": str(_resolve_package(repository, host)),
                "skill_source": "n/a",
                "action": "skipped",
                "discovery": layout.discovery,
                "rollback_boundary": "n/a",
                "required_config": hermes_external_dirs_snippet(source_parent=repository)
                if host == "hermes"
                else "n/a",
                "reason": f"{host} has no native project scope; user scope or external_dirs required",
            }
            snippet_emitted = snippet_emitted or host == "hermes"
            by_host[host] = entry
            continue
        target = _absolute(
            resolve_target(
                host,
                scope=scope,
                home=home_resolved,
                project_root=project_resolved,
                codex_home=codex_home,
            )
        )
        package = _resolve_package(repository, host)
        source_path = package / "skills" / SKILL_NAME if host == "claude" else package
        status = installation_status(target, source_path)
        action = "install" if status == "missing" else ("conflict" if status == "conflict" else "current")
        by_host[host] = {
            "host": host,
            "scope": scope,
            "mode": "copy",
            "target": str(target),
            "package": str(package),
            "skill_source": str(source_path),
            "action": action,
            "discovery": layout.discovery,
            "rollback_boundary": str(target),
            "required_config": None,
            "reason": f"install target={'conflict' if status == 'conflict' else ('current' if status == 'current' else 'missing')}",
        }

    entries = [by_host[host] for host in dict.fromkeys(hosts)]
    aggregate = all(entry["action"] in {"install", "current"} for entry in entries)
    return {
        "scope": scope,
        "mode": "copy",
        "dry_run": dry_run,
        "entries": entries,
        "aggregate_ready": aggregate,
        "snippet_required": snippet_emitted,
        "snippet": hermes_external_dirs_snippet(source_parent=repository) if snippet_emitted else None,
    }


def _resolve_package(repository: Path, host: str) -> Path:
    """Local copy of resolve_package for plan_heterogeneous_install use."""

    try:
        layout = HOST_LAYOUTS[host]
    except KeyError as exc:
        raise SkillSetupError(f"unsupported host: {host}") from exc
    return repository.joinpath(*layout.package_parts)


def installation_status_per_host(
    hosts: Sequence[str],
    *,
    source: Path,
    scope: str,
    home: Path,
    project_root: Path,
    codex_home: Path | None = None,
) -> dict[str, object]:
    """Issue #328: per-host installation status + aggregate (does not hide partial readiness)."""

    repository = source.expanduser().resolve()
    home_resolved = home.expanduser().resolve()
    project_resolved = project_root.expanduser().resolve()
    per_host: dict[str, dict[str, object]] = {}
    for host in dict.fromkeys(hosts):
        layout = HOST_LAYOUTS.get(host)
        if layout is None or (scope == "project" and layout.project_parts is None):
            per_host[host] = {
                "ready": False,
                "reason": f"{host} does not support this combination",
                "scope": scope,
            }
            continue
        target = _absolute(
            resolve_target(
                host,
                scope=scope,
                home=home_resolved,
                project_root=project_resolved,
                codex_home=codex_home,
            )
        )
        package = _resolve_package(repository, host)
        source_path = package / "skills" / SKILL_NAME if host == "claude" else package
        status, reason, _source_digest, _target_digest = _installation_status_detail(target, source_path)
        per_host[host] = {"ready": status == "current", "reason": reason, "scope": scope}
    aggregate = all(entry["ready"] for entry in per_host.values())
    return {
        "scope": scope,
        "hosts": per_host,
        "aggregate_ready": aggregate,
    }
