#!/usr/bin/env python3
"""Validate or stage the isolated research-tree package for Hermes Agent."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


HERMES_VERSION = "v2026.7.30"
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_SKILL_CHARS = 100_000
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
RESOURCE_RE = re.compile(
    r"`((?:references|templates|scripts|assets)/[^`\r\n]+)`"
)


def _default_skill_dir() -> Path:
    script = Path(__file__).resolve()
    package_candidate = script.parents[1]
    if (package_candidate / "SKILL.md").is_file():
        return package_candidate
    return package_candidate / "packages" / "hermes" / "research-tree"


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        raise ValueError("SKILL.md must start with --- at byte zero")

    match = re.search(r"\n---\s*\n", text[3:])
    if not match:
        raise ValueError("SKILL.md frontmatter is not closed")

    raw = text[3 : match.start() + 3]
    body = text[match.end() + 3 :].strip()
    if not body:
        raise ValueError("SKILL.md body is empty")

    values: dict[str, str] = {}
    for line in raw.splitlines():
        parsed = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*):\s*(.+?)\s*$", line)
        if parsed:
            values[parsed.group(1)] = parsed.group(2).strip("'\"")
    return values, body


def validate(skill_dir: Path, mode: str) -> dict[str, object]:
    skill_dir = skill_dir.resolve()
    skill_file = skill_dir / "SKILL.md"
    errors: list[str] = []
    warnings: list[str] = []
    description = ""
    resources: list[str] = []

    if not skill_file.is_file():
        errors.append(f"missing {skill_file}")
    else:
        raw_bytes = skill_file.read_bytes()
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            errors.append("SKILL.md has a UTF-8 BOM before frontmatter")
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"SKILL.md is not UTF-8: {exc}")
            text = ""

        if text:
            if len(text) > MAX_SKILL_CHARS:
                errors.append(
                    f"SKILL.md has {len(text)} characters; Hermes limit is "
                    f"{MAX_SKILL_CHARS}"
                )
            try:
                metadata, _ = _frontmatter(text)
            except ValueError as exc:
                errors.append(str(exc))
                metadata = {}

            name = metadata.get("name", "")
            description = metadata.get("description", "")
            if not name:
                errors.append("frontmatter is missing name")
            elif len(name) > MAX_NAME_LENGTH or not NAME_RE.fullmatch(name):
                errors.append("frontmatter name is not Hermes-compatible")
            if not description:
                errors.append("frontmatter is missing description")
            elif len(description) > MAX_DESCRIPTION_LENGTH:
                errors.append("frontmatter description exceeds 1024 characters")

            resources = sorted(set(RESOURCE_RE.findall(text)))
            for relative in resources:
                target = (skill_dir / relative).resolve()
                try:
                    target.relative_to(skill_dir)
                except ValueError:
                    errors.append(f"resource escapes skill directory: {relative}")
                    continue
                if not target.is_file():
                    errors.append(f"referenced resource is missing: {relative}")

            if "ask_user_question" in text and not (
                "ordinary dialogue" in text and "Never call a named tool" in text
            ):
                errors.append("host-specific question tool lacks a portable fallback")

    if mode == "single-file" and resources:
        errors.append(
            "Hermes direct-URL installation is single-file but this skill "
            "requires bundled resources"
        )

    compact_description = (
        description if len(description) <= 60 else description[:57] + "..."
    )
    if description and not compact_description.lower().startswith("use "):
        warnings.append("put the activation trigger in the first 60 characters")

    return {
        "compatible": not errors,
        "hermes_version": HERMES_VERSION,
        "mode": mode,
        "skill_dir": str(skill_dir),
        "compact_description": compact_description,
        "resources": resources,
        "errors": errors,
        "warnings": warnings,
    }


def stage(source: Path, output: Path) -> Path:
    source = source.resolve()
    output = output.resolve()
    target = output / "skills" / "research-tree"
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"refusing to overwrite non-empty target: {target}")

    result = validate(source, "external-dir")
    if not result["compatible"]:
        raise ValueError("source validation failed: " + "; ".join(result["errors"]))

    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "SKILL.md", target / "SKILL.md")
    for relative in result["resources"]:
        src = source / relative
        dst = target / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--skill-dir", type=Path, default=_default_skill_dir())
    validate_parser.add_argument(
        "--mode",
        choices=("external-dir", "github-bundle", "single-file"),
        default="external-dir",
    )

    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("output", type=Path)
    stage_parser.add_argument("--skill-dir", type=Path, default=_default_skill_dir())

    args = parser.parse_args()
    if args.command == "validate":
        result = validate(args.skill_dir, args.mode)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["compatible"] else 1

    try:
        target = stage(args.skill_dir, args.output)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    result = validate(target, "github-bundle")
    print(json.dumps({"staged_to": str(target), "validation": result}, indent=2))
    return 0 if result["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
