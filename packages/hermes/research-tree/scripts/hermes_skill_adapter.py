#!/usr/bin/env python3
"""Validate, diagnose, or stage research-tree for Hermes Agent."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


HERMES_VERSION = "v2026.8.3"
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_SKILL_CHARS = 100_000
RECOMMENDED_SKILL_CHARS = 20_000
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
RESOURCE_RE = re.compile(r"`((?:references|templates|scripts|assets)/[^`\r\n]+)`")
NATIVE_REFERENCE = Path("references/hermes-native-orchestration.md")
RUNTIME_HOOK = Path("scripts/hermes_runtime_hook.py")
EXECUTABLE_CLOSURE = Path("scripts/hermes_executable_closure.json")
NATIVE_MARKERS = (
    "delegate_task(tasks=[...])",
    "session_search",
    "workspace checkpoint",
    "live/<delegation_id>",
    "in-flight attempt `unknown`",
    "cronjob",
)
PROVIDER_FAILURE_MARKERS = {
    "context_limit": (
        "context length",
        "context_length_exceeded",
        "input too long",
        "maximum context",
        "max context",
        "too many tokens",
        "request too large",
        "prompt is too long",
    ),
    "authentication": (
        "authentication failed",
        "incorrect api key",
        "invalid api key",
        "unauthorized",
        "http 401",
        "status code: 401",
    ),
    "rate_limit": (
        "rate limit",
        "rate_limit",
        "too many requests",
        "http 429",
        "status code: 429",
    ),
    "provider_policy": (
        "content policy",
        "safety policy",
        "request rejected",
        "moderation",
    ),
    "network_or_timeout": (
        "connection reset",
        "connection closed",
        "connection failed",
        "timed out",
        "timeout",
        "broken pipe",
        "end of file",
    ),
    "malformed_or_empty_stream": (
        "malformed streaming",
        "empty response stream",
        "empty content after retries",
        "no content after retries",
    ),
}


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


def _safe_executable_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("Hermes executable closure paths must be non-empty strings")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or relative.parts[:1] != ("scripts",):
        raise ValueError(f"Hermes executable closure path is invalid: {value}")
    return relative


def _load_executable_closure(skill_dir: Path) -> tuple[list[str], list[dict[str, object]], list[str]]:
    errors: list[str] = []
    manifest = skill_dir / EXECUTABLE_CLOSURE
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [], [f"invalid Hermes executable closure: {exc}"]
    if not isinstance(value, dict) or value.get("schema") != 1:
        return [], [], ["Hermes executable closure must contain schema 1"]
    raw_files = value.get("files")
    raw_entrypoints = value.get("entrypoints")
    if not isinstance(raw_files, list) or not raw_files:
        errors.append("Hermes executable closure must contain non-empty files")
        raw_files = []
    if not isinstance(raw_entrypoints, list) or not raw_entrypoints:
        errors.append("Hermes executable closure must contain non-empty entrypoints")
        raw_entrypoints = []

    closure: list[str] = []
    for raw_file in raw_files:
        try:
            relative = _safe_executable_path(raw_file)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        normalized = relative.as_posix()
        if normalized in closure:
            errors.append(f"duplicate Hermes executable dependency: {normalized}")
            continue
        closure.append(normalized)

    entrypoints: list[dict[str, object]] = []
    entrypoint_paths: set[str] = set()
    for raw_entrypoint in raw_entrypoints:
        if not isinstance(raw_entrypoint, dict):
            errors.append("Hermes executable entrypoints must be objects")
            continue
        try:
            relative = _safe_executable_path(raw_entrypoint.get("path"))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        arguments = raw_entrypoint.get("arguments")
        if not isinstance(arguments, list) or not all(isinstance(argument, str) for argument in arguments):
            errors.append(f"Hermes executable entrypoint arguments are invalid: {relative.as_posix()}")
            continue
        normalized = relative.as_posix()
        if normalized not in closure:
            errors.append(f"Hermes executable entrypoint is outside closure: {normalized}")
            continue
        if normalized in entrypoint_paths:
            errors.append(f"duplicate Hermes executable entrypoint: {normalized}")
            continue
        entrypoint_paths.add(normalized)
        entrypoints.append({"path": normalized, "arguments": list(arguments)})
    missing_entrypoints = sorted(set(closure) - entrypoint_paths)
    if missing_entrypoints:
        errors.append("Hermes executable closure is missing entrypoint: " + ", ".join(missing_entrypoints))
    return closure, entrypoints, errors


def _cold_start_errors(skill_dir: Path, entrypoints: list[dict[str, object]]) -> list[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="research-tree-hermes-cold-start-") as raw_directory:
        working_directory = Path(raw_directory) / "unrelated-working-directory"
        working_directory.mkdir()
        for entrypoint in entrypoints:
            relative = str(entrypoint["path"])
            arguments = [str(argument) for argument in entrypoint["arguments"]]
            try:
                completed = subprocess.run(
                    [sys.executable, "-B", "-E", "-S", str(skill_dir / relative), *arguments],
                    cwd=working_directory,
                    env=environment,
                    text=True,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(f"Hermes executable cold start failed: {relative} ({type(exc).__name__})")
                continue
            if completed.returncode != 0:
                errors.append(f"Hermes executable cold start failed: {relative} (exit {completed.returncode})")
    return errors


def validate(skill_dir: Path, mode: str) -> dict[str, object]:
    skill_dir = skill_dir.resolve()
    skill_file = skill_dir / "SKILL.md"
    errors: list[str] = []
    warnings: list[str] = []
    description = ""
    resources: list[str] = []
    executable_closure: list[str] = []
    executable_entrypoints: list[dict[str, object]] = []
    skill_chars = 0

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
            skill_chars = len(text)
            if len(text) > MAX_SKILL_CHARS:
                errors.append(f"SKILL.md has {len(text)} characters; Hermes limit is {MAX_SKILL_CHARS}")
            elif len(text) > RECOMMENDED_SKILL_CHARS:
                warnings.append(
                    f"SKILL.md has {len(text)} characters; split it below "
                    f"{RECOMMENDED_SKILL_CHARS} characters to reduce provider "
                    "context failures when Hermes loads the full skill"
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

            resources = sorted(set(RESOURCE_RE.findall(text)) | {RUNTIME_HOOK.as_posix()})
            for relative in resources:
                target = (skill_dir / relative).resolve()
                try:
                    target.relative_to(skill_dir)
                except ValueError:
                    errors.append(f"resource escapes skill directory: {relative}")
                    continue
                if not target.is_file():
                    errors.append(f"referenced resource is missing: {relative}")

            native_path = skill_dir / NATIVE_REFERENCE
            if not native_path.is_file():
                errors.append(f"missing Hermes native contract: {NATIVE_REFERENCE}")
            else:
                native = native_path.read_text(encoding="utf-8")
                for marker in NATIVE_MARKERS:
                    if marker not in native:
                        errors.append(f"Hermes native contract is missing: {marker}")
                for unsupported in (
                    "delegate_task(background=",
                    "delegate_task(toolsets=",
                    "delegate_task(max_iterations=",
                ):
                    if unsupported in native:
                        errors.append("Hermes native contract uses unsupported model argument: " + unsupported)

            if not (skill_dir / RUNTIME_HOOK).is_file():
                errors.append(f"missing Hermes runtime hook: {RUNTIME_HOOK}")

            executable_closure, executable_entrypoints, closure_errors = _load_executable_closure(skill_dir)
            errors.extend(closure_errors)
            for relative in executable_closure:
                target = skill_dir / relative
                if not target.is_file():
                    errors.append(f"missing executable dependency: {relative}")
            if mode in {"external-dir", "github-bundle"} and not errors:
                errors.extend(_cold_start_errors(skill_dir, executable_entrypoints))

            if "ask_user_question" in text and not ("ordinary dialogue" in text and "Never call a named tool" in text):
                errors.append("host-specific question tool lacks a portable fallback")

    if mode == "single-file" and resources:
        errors.append("Hermes direct-URL installation is single-file but this skill requires bundled resources")

    compact_description = description if len(description) <= 60 else description[:57] + "..."
    if description and not compact_description.lower().startswith("use "):
        warnings.append("put the activation trigger in the first 60 characters")

    activation_payload_estimate = skill_chars + sum(2 * len(relative) + 12 for relative in resources) + 500

    return {
        "compatible": not errors,
        "hermes_version": HERMES_VERSION,
        "mode": mode,
        "skill_dir": str(skill_dir),
        "compact_description": compact_description,
        "prompt_risk": {
            "skill_chars": skill_chars,
            "recommended_skill_chars": RECOMMENDED_SKILL_CHARS,
            "activation_payload_estimate_chars": activation_payload_estimate,
            "level": "high" if skill_chars > RECOMMENDED_SKILL_CHARS else "low",
        },
        "resources": resources,
        "executable_closure": executable_closure,
        "executable_entrypoints": executable_entrypoints,
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

    bundle_files = {Path("SKILL.md"), EXECUTABLE_CLOSURE}
    bundle_files.update(Path(relative) for relative in result["resources"])
    bundle_files.update(Path(relative) for relative in result["executable_closure"])
    target.mkdir(parents=True, exist_ok=True)
    for relative in sorted(bundle_files):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
    return target


def _yaml_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_hooks(skill_dir: Path, python: Path | None = None) -> str:
    skill_dir = skill_dir.resolve()
    hook = (skill_dir / RUNTIME_HOOK).resolve()
    if not hook.is_file():
        raise ValueError(f"runtime hook is missing: {hook}")
    executable = (python or Path(sys.executable)).resolve()
    command = f'"{executable}" "{hook}"'
    quoted = _yaml_single_quote(command)
    lines = ["hooks:"]
    for event in (
        "on_session_start",
        "on_session_end",
        "on_session_finalize",
        "on_session_reset",
        "subagent_start",
        "subagent_stop",
    ):
        lines.extend(
            [
                f"  {event}:",
                f"    - command: {quoted}",
                "      timeout: 10",
            ]
        )
    lines.extend(
        [
            "  post_tool_call:",
            '    - matcher: "^delegate_task$"',
            f"      command: {quoted}",
            "      timeout: 10",
            "hooks_auto_accept: false",
        ]
    )
    return "\n".join(lines) + "\n"


def _hermes_version(executable: str | None) -> dict[str, object]:
    if executable is None:
        return {"found": False, "path": None, "version": None}
    try:
        completed = subprocess.run(
            [executable, "--version"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"found": True, "path": executable, "version": None, "error": str(exc)}
    output = (completed.stdout or completed.stderr).strip()
    return {
        "found": True,
        "path": executable,
        "version": output or None,
        "returncode": completed.returncode,
    }


def diagnose_gateway_log(log_path: Path) -> dict[str, object]:
    """Classify recent provider failures without returning raw log content."""
    log_path = log_path.expanduser().resolve()
    result: dict[str, object] = {
        "path": str(log_path),
        "exists": log_path.is_file(),
        "category": None,
        "matched_marker": None,
    }
    if not log_path.is_file():
        return result

    try:
        with log_path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 256_000))
            text = handle.read().decode("utf-8", errors="replace").lower()
    except OSError as exc:
        result["read_error"] = type(exc).__name__
        return result

    best: tuple[int, str, str] | None = None
    for category, markers in PROVIDER_FAILURE_MARKERS.items():
        for marker in markers:
            position = text.rfind(marker)
            if position >= 0 and (best is None or position > best[0]):
                best = (position, category, marker)
    if best:
        result["category"] = best[1]
        result["matched_marker"] = best[2]
    elif any(token in text for token in ("provider failed", "api call failed")):
        result["category"] = "unclassified_provider_failure"
    return result


def doctor(skill_dir: Path, hermes_home: Path) -> dict[str, object]:
    skill_dir = skill_dir.resolve()
    hermes_home = hermes_home.expanduser().resolve()
    validation = validate(skill_dir, "external-dir")
    executable = shutil.which("hermes") or shutil.which("hermes-agent")
    config = hermes_home / "config.yaml"
    gateway_log = hermes_home / "logs" / "gateway.log"
    config_text = config.read_text(encoding="utf-8") if config.is_file() else ""
    skill_path = str(skill_dir).replace("\\", "/")
    hook_path = str((skill_dir / RUNTIME_HOOK).resolve()).replace("\\", "/")
    return {
        "healthy": bool(validation["compatible"] and executable),
        "baseline": HERMES_VERSION,
        "skill": validation,
        "cli": _hermes_version(executable),
        "config": {
            "path": str(config),
            "exists": config.is_file(),
            "skill_path_mentioned": skill_path in config_text.replace("\\", "/"),
            "runtime_hook_mentioned": hook_path in config_text.replace("\\", "/"),
        },
        "gateway_log": diagnose_gateway_log(gateway_log),
        "next_actions": [
            "install Hermes CLI" if not executable else None,
            "merge the render-hooks output into ~/.hermes/config.yaml"
            if hook_path not in config_text.replace("\\", "/")
            else None,
            "run /reload-skills after installation or configuration changes",
        ],
    }


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

    hooks_parser = subparsers.add_parser("render-hooks")
    hooks_parser.add_argument("--skill-dir", type=Path, default=_default_skill_dir())
    hooks_parser.add_argument("--python", type=Path)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--skill-dir", type=Path, default=_default_skill_dir())
    doctor_parser.add_argument("--hermes-home", type=Path, default=Path("~/.hermes"))

    args = parser.parse_args()
    if args.command == "validate":
        result = validate(args.skill_dir, args.mode)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["compatible"] else 1

    if args.command == "render-hooks":
        try:
            print(render_hooks(args.skill_dir, args.python), end="")
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.command == "doctor":
        result = doctor(args.skill_dir, args.hermes_home)
        result["next_actions"] = [action for action in result["next_actions"] if action is not None]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["healthy"] else 1

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
