"""Install the checked-out research-tree skill for supported agent hosts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Iterable, Sequence


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
                f"Claude plugin manifest is missing; run python scripts/build_skill_packages.py: "
                f"{manifest}"
            )
        try:
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SkillSetupError(f"Claude plugin manifest is invalid JSON: {manifest}") from exc
        if not isinstance(metadata, dict) or metadata.get("name") != SKILL_NAME:
            raise SkillSetupError(
                f"Claude plugin manifest does not name {SKILL_NAME!r}: {manifest}"
            )
    if not (skill_source / "SKILL.md").is_file():
        raise SkillSetupError(
            f"{host} package is missing; run python scripts/build_skill_packages.py: "
            f"{package}"
        )
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


def installation_status(
    target: Path,
    source: Path,
    *,
    legacy_source: Path | None = None,
    additional_legacy_sources: Iterable[Path] = (),
) -> str:
    if not _lexists(target):
        return "missing"
    if _same_source(target, source):
        return "current"
    legacy_sources = tuple(additional_legacy_sources)
    if legacy_source is not None:
        legacy_sources = (legacy_source, *legacy_sources)
    if any(_same_source(target, candidate) for candidate in legacy_sources):
        return "legacy"
    return "conflict"


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


def _remove_link_target(target: Path) -> None:
    if target.is_symlink():
        target.unlink()
        return
    if os.name == "nt":
        target.rmdir()
        return
    raise SkillSetupError(f"legacy installation is not a removable link: {target}")


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
        host: package / "skills" / SKILL_NAME if host == "claude" else package
        for host, package in packages.items()
    }
    payloads = {host: _read_payload(package) for host, package in sources.items()}
    targets = {
        host: _absolute(resolve_target(
            host,
            scope=scope,
            home=home,
            project_root=project_root,
            codex_home=codex_home,
        ))
        for host in ordered_hosts
    }
    if mode == "link":
        recursive = [
            host for host, target in targets.items()
            if _lexically_inside(sources[host], target)
        ]
        if recursive:
            names = ", ".join(recursive)
            raise SkillSetupError(
                f"link target for {names} is inside the source checkout; use --mode copy "
                "for a project-scoped install"
            )

    statuses = {
        host: installation_status(
            target,
            sources[host],
            legacy_source=repository,
            additional_legacy_sources=(packages[host],) if host == "claude" else (),
        )
        for host, target in targets.items()
    }
    conflicts = [host for host, status in statuses.items() if status == "conflict"]
    if conflicts:
        details = ", ".join(f"{host}={targets[host]}" for host in conflicts)
        raise SkillSetupError(
            "refusing to overwrite existing non-source skill installation(s): " + details
        )

    results: list[dict[str, str]] = []
    created: list[tuple[Path, Path | None]] = []
    try:
        for host, target in targets.items():
            status = statuses[host]
            action = "unchanged" if status == "current" else "planned"
            if status in {"missing", "legacy"} and not dry_run:
                previous = repository if status == "legacy" else None
                if status == "legacy":
                    _remove_link_target(target)
                created.append((target, previous))
                if mode == "link":
                    _create_link(sources[host], target)
                else:
                    _copy_payload(sources[host], target, payloads[host])
                action = "migrated" if status == "legacy" else "installed"
            elif status == "legacy":
                action = "planned_migration"
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
                    "payload_files": [
                        item.as_posix() for item in payloads[host]
                    ],
                }
            )
    except (OSError, SkillSetupError) as exc:
        for target, previous in reversed(created):
            _remove_created_target(target, mode)
            if previous is not None:
                _create_link(previous, target)
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
        target = _absolute(resolve_target(
            host,
            scope=scope,
            home=home,
            project_root=project_root,
            codex_home=codex_home,
        ))
        installations.append(
            {
                "host": host,
                "scope": scope,
                "target": str(target),
                "package": str(package),
                "skill_source": str(skill_source),
                "status": installation_status(
                    target,
                    skill_source,
                    legacy_source=repository,
                    additional_legacy_sources=(package,) if host == "claude" else (),
                ),
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
