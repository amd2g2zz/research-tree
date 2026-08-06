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
ACTIVATION_MARKER_RE = re.compile(
    r"<!--\s*research-tree-activation:\s*([a-z]+):([A-Z0-9-]+)\s*-->"
)
ACTIVATION_SENTINELS = {
    "codex": "RT-ACTIVE-V1-CODEX",
    "claude": "RT-ACTIVE-V1-CLAUDE",
    "hermes": "RT-ACTIVE-V1-HERMES",
}
HOST_ACTIVATION_PROBES = {
    "codex": "$research-tree --activation-probe",
    "claude": "/research-tree --activation-probe",
    "hermes": "/research-tree --activation-probe",
}
HOST_RELOAD_ACTIONS = {
    "codex": "Start a new Codex session after installing or refreshing a skill.",
    "claude": "Start a new Claude Code session after installing or refreshing a skill.",
    "hermes": "Run /reload-skills or start a new Hermes session after installing or refreshing a skill.",
}


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
    if not (package / "SKILL.md").is_file():
        raise SkillSetupError(
            f"{host} package is missing; run python scripts/build_skill_packages.py: "
            f"{package}"
        )
    return package


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
    """Return whether *path* is a symlink or Windows directory junction.

    ``Path.is_symlink`` does not report a Windows junction.  Comparing the
    lexical path with its resolved target detects both without following an
    arbitrary path for deletion.
    """
    if not _lexists(path):
        return False
    try:
        return _absolute(path) != path.resolve(strict=True)
    except OSError:
        return False


def _declares_research_tree_skill(path: Path) -> bool:
    skill_file = path / "SKILL.md"
    if not skill_file.is_file():
        return False
    try:
        text = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return bool(re.search(r"(?m)^name:\s*research-tree\s*$", text))


def _activation_contract(package: Path, host: str) -> dict[str, object]:
    """Validate the static evidence required before a live activation probe.

    This deliberately does not claim that a host injected the skill body into a
    particular model turn.  Only a host-visible probe can establish that.
    """
    expected = ACTIVATION_SENTINELS[host]
    skill_file = package / "SKILL.md"
    errors: list[str] = []
    marker = None
    if not skill_file.is_file():
        errors.append("missing SKILL.md")
        text = ""
    else:
        try:
            text = skill_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append("SKILL.md is not UTF-8")
            text = ""
    if text:
        matches = ACTIVATION_MARKER_RE.findall(text)
        expected_matches = [(host, expected)]
        if matches != expected_matches:
            errors.append(
                "SKILL.md activation marker does not match the host contract"
            )
        else:
            marker = expected
        if "--activation-probe" not in text:
            errors.append("SKILL.md is missing the activation probe contract")
        if "activation_receipt.py" not in text:
            errors.append("SKILL.md is missing the activation receipt contract")

    required = (
        "references/research-quality-playbook.md",
        "references/alignment-controller.md",
        "scripts/activation_receipt.py",
    )
    missing = [relative for relative in required if not (package / relative).is_file()]
    errors.extend(f"missing activation resource: {relative}" for relative in missing)
    return {
        "valid": not errors,
        "sentinel": marker,
        "required_resources": required,
        "errors": errors,
    }


def installation_status(
    target: Path,
    source: Path,
    *,
    legacy_source: Path | None = None,
) -> str:
    if not _lexists(target):
        return "missing"
    if _same_source(target, source):
        return "current"
    if legacy_source is not None and _same_source(target, legacy_source):
        return "legacy"
    if _is_link_like(target) and _declares_research_tree_skill(target):
        return "stale_link"
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
    refresh_stale_link: bool = False,
) -> dict[str, object]:
    repository = source.expanduser().resolve()
    if mode not in {"link", "copy"}:
        raise SkillSetupError(f"unsupported install mode: {mode}")

    ordered_hosts = tuple(dict.fromkeys(hosts))
    sources = {host: resolve_package(repository, host) for host in ordered_hosts}
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
            target, sources[host], legacy_source=repository
        )
        for host, target in targets.items()
    }
    stale_links = [
        host for host, status in statuses.items() if status == "stale_link"
    ]
    conflicts = [
        host
        for host, status in statuses.items()
        if status == "conflict" or (status == "stale_link" and not refresh_stale_link)
    ]
    if conflicts:
        details = ", ".join(f"{host}={targets[host]}" for host in conflicts)
        stale_hint = (
            "; use --refresh-stale-link only after confirming the stale link "
            "may be repointed"
            if stale_links
            else ""
        )
        raise SkillSetupError(
            "refusing to overwrite existing non-source skill installation(s): "
            + details
            + stale_hint
        )

    results: list[dict[str, str]] = []
    created: list[tuple[Path, Path | None]] = []
    try:
        for host, target in targets.items():
            status = statuses[host]
            action = "unchanged" if status == "current" else "planned"
            if status in {"missing", "legacy", "stale_link"} and not dry_run:
                previous = None
                if status == "legacy":
                    previous = repository
                elif status == "stale_link":
                    previous = target.resolve(strict=True)
                if status in {"legacy", "stale_link"}:
                    _remove_link_target(target)
                created.append((target, previous))
                if mode == "link":
                    _create_link(sources[host], target)
                else:
                    _copy_payload(sources[host], target, payloads[host])
                if status == "legacy":
                    action = "migrated"
                elif status == "stale_link":
                    action = "refreshed_stale_link"
                else:
                    action = "installed"
            elif status == "legacy":
                action = "planned_migration"
            elif status == "stale_link":
                action = "planned_stale_link_refresh"
            results.append(
                {
                    "host": host,
                    "scope": scope,
                    "mode": mode,
                    "target": str(target),
                    "package": str(sources[host]),
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
        "refresh_stale_link": refresh_stale_link,
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
        _read_payload(package)
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
                "status": installation_status(
                    target, package, legacy_source=repository
                ),
                "discovery": HOST_LAYOUTS[host].discovery,
            }
        )
    return {
        "repository": str(repository),
        "scope": scope,
        "installations": installations,
    }


def activation_status(
    hosts: Sequence[str],
    *,
    source: Path,
    scope: str,
    home: Path,
    project_root: Path,
    codex_home: Path | None = None,
) -> dict[str, object]:
    """Report static activation readiness without overstating live loading.

    The host owns model-context injection.  This command proves package shape
    and installation target only; it returns an explicit live probe for the
    requester to run in a fresh host session.
    """
    repository = source.expanduser().resolve()
    installations = []
    for host in tuple(dict.fromkeys(hosts)):
        package = resolve_package(repository, host)
        _read_payload(package)
        target = _absolute(resolve_target(
            host,
            scope=scope,
            home=home,
            project_root=project_root,
            codex_home=codex_home,
        ))
        installation = installation_status(
            target, package, legacy_source=repository
        )
        contract = _activation_contract(package, host)
        ready = installation == "current" and bool(contract["valid"])
        installations.append(
            {
                "host": host,
                "scope": scope,
                "package": str(package),
                "target": str(target),
                "installation_status": installation,
                "static_contract": contract,
                "static_readiness": "ready" if ready else "blocked",
                "manual_probe": {
                    "command": HOST_ACTIVATION_PROBES[host],
                    "expected_response": (
                        "research-tree activation: " + ACTIVATION_SENTINELS[host]
                    ),
                    "after_install": HOST_RELOAD_ACTIONS[host],
                },
                "proves": [
                    "the generated package has the host-specific activation contract",
                    "whether the configured installation points at this package",
                ],
                "does_not_prove": [
                    "that a particular live host session injected SKILL.md into model context",
                    "that a model followed the activated instructions after injection",
                ],
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
    for command in ("install", "status", "activation"):
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
        "--refresh-stale-link",
        action="store_true",
        help=(
            "repoint a confirmed stale research-tree symlink or Windows junction; "
            "never replaces a real directory"
        ),
    )
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
                refresh_stale_link=arguments.refresh_stale_link,
            )
        elif arguments.command == "status":
            result = skill_status(
                hosts,
                source=arguments.source,
                scope=arguments.scope,
                home=arguments.home,
                project_root=arguments.project_root,
                codex_home=arguments.codex_home,
            )
        else:
            result = activation_status(
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
