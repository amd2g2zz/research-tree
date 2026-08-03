#!/usr/bin/env python3
"""Build isolated Codex, Claude Code, and Hermes skill packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "skill-src" / "SKILL.template.md"
HERMES_ADAPTER = ROOT / "skill-src" / "hermes-adapter.md"
TOKEN = "<!-- HOST_ADAPTER -->"
FRONTMATTER_TOKEN = "<!-- HOST_FRONTMATTER -->"
RESOURCE_RE = re.compile(r"`((?:references|templates|scripts|assets)/[^`\r\n]+)`")
PACKAGE_RELATIVES = {
    "codex": Path("packages/codex/research-tree"),
    "claude": Path("packages/claude-code/research-tree"),
    "hermes": Path("packages/hermes/research-tree"),
}
COMMON_FILES = (
    Path("assets/brief-template.md"),
    Path("assets/human-brief-template.md"),
    Path("assets/research-strategy-template.md"),
    Path("assets/technical-research-package-template.md"),
    Path("references/blueprint-generation-research.md"),
    Path("references/product-contracts.md"),
    Path("references/research-quality-playbook.md"),
)
HERMES_FILES = (
    Path("references/hermes-agent-compatibility.md"),
    Path("scripts/hermes_skill_adapter.py"),
)
HOST_FILE_MAP = {
    "codex": (
        (Path("skill-src/codex-openai.yaml"), Path("agents/openai.yaml")),
    ),
    "claude": (),
    "hermes": (),
}


def package_source(host: str, root: Path = ROOT) -> Path:
    try:
        relative = PACKAGE_RELATIVES[host]
    except KeyError as exc:
        raise ValueError(f"unsupported host package: {host}") from exc
    return root / relative


def _render_skill(host: str, root: Path) -> str:
    template = (root / TEMPLATE.relative_to(ROOT)).read_text(encoding="utf-8")
    if template.count(TOKEN) != 1:
        raise ValueError(f"template must contain exactly one {TOKEN!r} marker")
    if template.count(FRONTMATTER_TOKEN) != 1:
        raise ValueError(
            f"template must contain exactly one {FRONTMATTER_TOKEN!r} marker"
        )
    frontmatter = ""
    if host == "claude":
        frontmatter = (
            root / "skill-src" / "claude-frontmatter.yaml"
        ).read_text(encoding="utf-8").strip()
    adapter = ""
    if host == "hermes":
        adapter = (
            root / HERMES_ADAPTER.relative_to(ROOT)
        ).read_text(encoding="utf-8").strip()
    return (
        template.replace(
            FRONTMATTER_TOKEN + "\n",
            frontmatter + "\n" if frontmatter else "",
        )
        .replace(TOKEN, adapter)
        .rstrip()
        + "\n"
    )


def _copy_files(root: Path, target: Path, relatives: tuple[Path, ...]) -> None:
    for relative in relatives:
        source = root / relative
        if not source.is_file():
            raise ValueError(f"package source file is missing: {relative.as_posix()}")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _copy_mapped_files(
    root: Path, target: Path, mappings: tuple[tuple[Path, Path], ...]
) -> None:
    for source_relative, target_relative in mappings:
        source = root / source_relative
        if not source.is_file():
            raise ValueError(
                f"package source file is missing: {source_relative.as_posix()}"
            )
        destination = target / target_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def validate_package(
    package: Path, host: str, root: Path = ROOT
) -> dict[str, object]:
    skill_file = package / "SKILL.md"
    errors: list[str] = []
    if not skill_file.is_file():
        errors.append("missing SKILL.md")
        text = ""
    else:
        text = skill_file.read_text(encoding="utf-8")
        if not text.startswith("---"):
            errors.append("SKILL.md must start with frontmatter")
        if TOKEN in text:
            errors.append("unexpanded host adapter marker")
        if FRONTMATTER_TOKEN in text:
            errors.append("unexpanded host frontmatter marker")
        if text != _render_skill(host, root):
            errors.append("SKILL.md is stale relative to its host template")

    expected_files = {Path("SKILL.md"), *COMMON_FILES}
    if host == "hermes":
        expected_files.update(HERMES_FILES)
    expected_files.update(target for _source, target in HOST_FILE_MAP[host])
    actual_files = {
        path.relative_to(package)
        for path in package.rglob("*")
        if path.is_file()
    }
    for relative in sorted(expected_files - actual_files):
        errors.append(f"missing package file: {relative.as_posix()}")
    for relative in sorted(actual_files - expected_files):
        errors.append(f"unexpected package file: {relative.as_posix()}")
    for relative in sorted(expected_files - {Path("SKILL.md")}):
        package_file = package / relative
        source_relative = next(
            (
                source
                for source, target in HOST_FILE_MAP[host]
                if target == relative
            ),
            relative,
        )
        source_file = root / source_relative
        if package_file.is_file() and source_file.is_file():
            if package_file.read_bytes() != source_file.read_bytes():
                errors.append(f"stale package file: {relative.as_posix()}")

    resources = sorted(set(RESOURCE_RE.findall(text)))
    for relative in resources:
        if not (package / relative).is_file():
            errors.append(f"missing referenced resource: {relative}")

    has_hermes_material = (
        "Hermes runtime adapter" in text
        or (package / "references/hermes-agent-compatibility.md").exists()
        or (package / "scripts/hermes_skill_adapter.py").exists()
    )
    if host == "hermes" and not has_hermes_material:
        errors.append("Hermes package is missing its compatibility adapter")
    if host != "hermes" and has_hermes_material:
        errors.append(f"{host} package contains Hermes-only compatibility material")

    claude_fields = (
        "argument-hint:",
        "disable-model-invocation:",
        "user-invocable:",
    )
    has_claude_frontmatter = all(field in text for field in claude_fields)
    if host == "claude" and not has_claude_frontmatter:
        errors.append("Claude package is missing Claude Code frontmatter")
    if host != "claude" and any(field in text for field in claude_fields):
        errors.append(f"{host} package contains Claude Code-only frontmatter")
    if host == "codex" and not (package / "agents/openai.yaml").is_file():
        errors.append("Codex package is missing agents/openai.yaml")
    if host != "codex" and (package / "agents/openai.yaml").exists():
        errors.append(f"{host} package contains Codex-only agents/openai.yaml")

    return {
        "host": host,
        "package": str(package),
        "valid": not errors,
        "resources": resources,
        "errors": errors,
    }


def build_packages(root: Path = ROOT) -> dict[str, object]:
    root = root.resolve()
    package_parent = root / "packages"
    package_parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="research-tree-packages-", dir=root) as raw:
        staging_root = Path(raw)
        for host, relative in PACKAGE_RELATIVES.items():
            staged = staging_root / relative
            staged.mkdir(parents=True)
            (staged / "SKILL.md").write_text(
                _render_skill(host, root), encoding="utf-8", newline="\n"
            )
            _copy_files(root, staged, COMMON_FILES)
            if host == "hermes":
                _copy_files(root, staged, HERMES_FILES)
            _copy_mapped_files(root, staged, HOST_FILE_MAP[host])
            validation = validate_package(staged, host, root)
            if not validation["valid"]:
                raise ValueError("; ".join(validation["errors"]))

            target = root / relative
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged, target)
            results.append(validate_package(target, host, root))

    return {"packages": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate without rebuilding")
    args = parser.parse_args()
    if args.check:
        result = {
            "packages": [
                validate_package(package_source(host), host)
                for host in PACKAGE_RELATIVES
            ]
        }
    else:
        result = build_packages()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(item["valid"] for item in result["packages"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
