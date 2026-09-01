#!/usr/bin/env python3
"""Build isolated Codex, Claude Code, and Hermes skill packages."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "skill-src" / "SKILL.template.md"
HERMES_TEMPLATE = ROOT / "skill-src" / "hermes-SKILL.template.md"
HERMES_ADAPTER = ROOT / "skill-src" / "hermes-adapter.md"
CLAUDE_ADAPTER = ROOT / "skill-src" / "claude-adapter.md"
CODEX_ADAPTER = ROOT / "skill-src" / "codex-adapter.md"
TOKEN = "<!-- HOST_ADAPTER -->"
FRONTMATTER_TOKEN = "<!-- HOST_FRONTMATTER -->"
RESOURCE_RE = re.compile(r"`((?:references|templates|scripts|assets)/[^`\r\n]+)`")
PACKAGE_RELATIVES = {
    "codex": Path("packages/codex/research-tree"),
    "claude": Path("packages/claude-code/research-tree"),
    "hermes": Path("packages/hermes/research-tree"),
}
ACTIVATION_MARKERS = {
    "codex": "research-tree-activation-contract:v1:codex",
    "claude": "research-tree-activation-contract:v1:claude",
    "hermes": "research-tree-activation-contract:v1:hermes",
}
CLAUDE_SKILL_ROOT = Path("skills") / "research-tree"
CLAUDE_PLUGIN_SOURCE = Path("skill-src/claude-plugin.json")
CLAUDE_MARKETPLACE_SOURCE = Path("skill-src/claude-marketplace.json")
COMMON_FILES = (
    Path("assets/brief-template.md"),
    Path("assets/human-brief-template.md"),
    Path("assets/research-strategy-template.md"),
    Path("assets/technical-research-package-template.md"),
    Path("references/blueprint-generation-research.md"),
    Path("references/debug-tracing.md"),
    Path("references/product-contracts.md"),
    Path("references/research-tree-architecture.md"),
    Path("references/research-quality-playbook.md"),
    Path("references/alignment-controller.md"),
    Path("references/skill-activation.md"),
    Path("scripts/lifecycle_hook_launcher.py"),
)
COMMON_FILE_MAP = (
    (Path("src/research_tree/alignment_graph.py"), Path("scripts/alignment_controller.py")),
    (Path("src/research_tree/skill_activation.py"), Path("scripts/skill_activation.py")),
    (Path("src/research_tree/lifecycle_hook.py"), Path("scripts/lifecycle_hook.py")),
    (Path("src/research_tree/origins.py"), Path("scripts/origins.py")),
    (Path("src/research_tree/host_capabilities.py"), Path("scripts/native_workflow_contract.py")),
    (Path("src/research_tree/project_workspace.py"), Path("scripts/project_workspace_contract.py")),
)
HERMES_FILES = (
    Path("references/hermes-alignment.md"),
    Path("references/hermes-agent-compatibility.md"),
    Path("references/hermes-delivery.md"),
    Path("references/hermes-native-orchestration.md"),
    Path("references/hermes-research-execution.md"),
    Path("scripts/hermes_runtime_hook.py"),
    Path("scripts/hermes_skill_adapter.py"),
    Path("scripts/hermes_execution_adapter.py"),
    Path("scripts/host_event_protocol.py"),
    Path("scripts/hermes_event_adapter.py"),
    Path("scripts/context_ledger_contract.py"),
    Path("scripts/hermes_executable_closure.json"),
)
CLAUDE_FILES = (
    Path("references/claude-code-compatibility.md"),
    Path("references/claude-native-orchestration.md"),
    Path("scripts/native_execution_adapter.py"),
    Path("scripts/host_event_protocol.py"),
    Path("scripts/context_ledger_contract.py"),
)
CODEX_FILES = (
    Path("references/codex-cli-compatibility.md"),
    Path("references/codex-native-orchestration.md"),
    Path("scripts/native_execution_adapter.py"),
    Path("scripts/host_event_protocol.py"),
    Path("scripts/context_ledger_contract.py"),
)
HOST_FILE_MAP = {
    "codex": ((Path("skill-src/codex-openai.yaml"), Path("agents/openai.yaml")),),
    "claude": (),
    "hermes": (),
}


def _skill_root(package: Path, host: str) -> Path:
    return package / CLAUDE_SKILL_ROOT if host == "claude" else package


def _skill_relative(host: str, relative: Path) -> Path:
    return CLAUDE_SKILL_ROOT / relative if host == "claude" else relative


def _project_version(root: Path) -> str:
    project_file = root / "pyproject.toml"
    try:
        project = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]
        version = project["version"]
    except (FileNotFoundError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"could not read project version from {project_file}") from exc
    if not isinstance(version, str) or not version:
        raise ValueError("pyproject.toml project.version must be a non-empty string")
    return version


def _load_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def _hermes_executable_closure(root: Path) -> tuple[Path, ...]:
    manifest = _load_json(root / "scripts" / "hermes_executable_closure.json", "Hermes executable closure")
    files = manifest.get("files")
    if manifest.get("schema") != 1 or not isinstance(files, list) or not files:
        raise ValueError("Hermes executable closure must contain schema 1 and non-empty files")
    closure: list[Path] = []
    for item in files:
        if not isinstance(item, str) or not item:
            raise ValueError("Hermes executable closure files must be non-empty strings")
        relative = Path(item)
        if relative.is_absolute() or ".." in relative.parts or relative.parts[:1] != ("scripts",):
            raise ValueError(f"Hermes executable closure path is invalid: {item}")
        closure.append(relative)
    if len(set(closure)) != len(closure):
        raise ValueError("Hermes executable closure files must be unique")
    return tuple(closure)


def _hermes_executable_source_map() -> dict[Path, Path]:
    source_map = {
        relative: relative
        for relative in HERMES_FILES
        if relative.parent == Path("scripts") and relative != Path("scripts/hermes_executable_closure.json")
    }
    for source_relative, target_relative in COMMON_FILE_MAP:
        if target_relative in source_map:
            raise ValueError(f"duplicate Hermes executable package path: {target_relative.as_posix()}")
        source_map[target_relative] = source_relative
    return source_map


def _hermes_executable_mappings(root: Path) -> tuple[tuple[Path, Path], ...]:
    closure = _hermes_executable_closure(root)
    source_map = _hermes_executable_source_map()
    closure_set = set(closure)
    expected_set = set(source_map)
    missing = sorted(expected_set - closure_set)
    unexpected = sorted(closure_set - expected_set)
    if missing:
        raise ValueError(
            "Hermes executable closure is missing packaged dependency: "
            + ", ".join(relative.as_posix() for relative in missing)
        )
    if unexpected:
        raise ValueError(
            "Hermes executable closure has unknown packaged dependency: "
            + ", ".join(relative.as_posix() for relative in unexpected)
        )
    return tuple((source_map[relative], relative) for relative in closure)


def _hermes_non_executable_files() -> tuple[Path, ...]:
    executable_paths = set(_hermes_executable_source_map())
    return tuple(relative for relative in HERMES_FILES if relative not in executable_paths)


def _validate_hermes_executable_package(package: Path) -> list[str]:
    adapter = package / "scripts" / "hermes_skill_adapter.py"
    if not adapter.is_file():
        return []
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="research-tree-hermes-package-check-") as raw_directory:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-E",
                "-S",
                str(adapter),
                "validate",
                "--skill-dir",
                str(package),
                "--mode",
                "external-dir",
            ],
            cwd=raw_directory,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
    if completed.returncode == 0:
        return []
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ["Hermes executable package validation failed without JSON diagnostics"]
    failures = result.get("errors") if isinstance(result, dict) else None
    if not isinstance(failures, list) or not all(isinstance(error, str) for error in failures):
        return ["Hermes executable package validation failed without error diagnostics"]
    return ["Hermes executable package validation failed: " + error for error in failures]


def package_source(host: str, root: Path = ROOT) -> Path:
    try:
        relative = PACKAGE_RELATIVES[host]
    except KeyError as exc:
        raise ValueError(f"unsupported host package: {host}") from exc
    return root / relative


def _render_skill(host: str, root: Path) -> str:
    template_path = HERMES_TEMPLATE if host == "hermes" else TEMPLATE
    template = (root / template_path.relative_to(ROOT)).read_text(encoding="utf-8")
    if host == "hermes":
        return template.rstrip() + "\n"
    if template.count(TOKEN) != 1:
        raise ValueError(f"template must contain exactly one {TOKEN!r} marker")
    if template.count(FRONTMATTER_TOKEN) != 1:
        raise ValueError(f"template must contain exactly one {FRONTMATTER_TOKEN!r} marker")
    frontmatter = ""
    if host == "claude":
        frontmatter = (root / "skill-src" / "claude-frontmatter.yaml").read_text(encoding="utf-8").strip()
    adapter = ""
    if host == "codex":
        adapter = (root / CODEX_ADAPTER.relative_to(ROOT)).read_text(encoding="utf-8").strip()
    elif host == "hermes":
        adapter = (root / HERMES_ADAPTER.relative_to(ROOT)).read_text(encoding="utf-8").strip()
    elif host == "claude":
        adapter = (root / CLAUDE_ADAPTER.relative_to(ROOT)).read_text(encoding="utf-8").strip()
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


def _copy_mapped_files(root: Path, target: Path, mappings: tuple[tuple[Path, Path], ...]) -> None:
    for source_relative, target_relative in mappings:
        source = root / source_relative
        if not source.is_file():
            raise ValueError(f"package source file is missing: {source_relative.as_posix()}")
        destination = target / target_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _validate_plugin_manifest(package: Path, root: Path, project_version: str | None) -> list[str]:
    errors: list[str] = []
    manifest = package / ".claude-plugin" / "plugin.json"
    source = root / CLAUDE_PLUGIN_SOURCE
    if not manifest.is_file():
        return ["missing .claude-plugin/plugin.json"]
    if not source.is_file():
        errors.append(f"missing package source: {CLAUDE_PLUGIN_SOURCE.as_posix()}")
    elif manifest.read_bytes() != source.read_bytes():
        errors.append("stale package file: .claude-plugin/plugin.json")
    try:
        data = _load_json(manifest, "Claude plugin manifest")
    except ValueError as error:
        return [str(error)]
    if data.get("name") != "research-tree":
        errors.append("Claude plugin manifest name must be research-tree")
    if project_version is not None and data.get("version") != project_version:
        errors.append("Claude plugin manifest version differs from pyproject.toml")
    for field in ("description", "repository"):
        if not isinstance(data.get(field), str) or not data[field]:
            errors.append(f"Claude plugin manifest requires {field}")
    author = data.get("author")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str):
        errors.append("Claude plugin manifest requires author.name")
    return errors


def validate_marketplace(root: Path = ROOT) -> dict[str, object]:
    root = root.resolve()
    errors: list[str] = []
    manifest = root / ".claude-plugin" / "marketplace.json"
    source = root / CLAUDE_MARKETPLACE_SOURCE
    if not manifest.is_file():
        errors.append("missing .claude-plugin/marketplace.json")
        data: dict[str, object] = {}
    else:
        if not source.is_file():
            errors.append(f"missing marketplace source: {CLAUDE_MARKETPLACE_SOURCE.as_posix()}")
        elif manifest.read_bytes() != source.read_bytes():
            errors.append("stale .claude-plugin/marketplace.json")
        try:
            data = _load_json(manifest, "Claude marketplace manifest")
        except ValueError as error:
            errors.append(str(error))
            data = {}
    try:
        project_version = _project_version(root)
    except ValueError as error:
        errors.append(str(error))
        project_version = None
    if data.get("name") != "research-tree":
        errors.append("Claude marketplace name must be research-tree")
    if project_version is not None and data.get("version") != project_version:
        errors.append("Claude marketplace version differs from pyproject.toml")
    owner = data.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("name"), str) or not owner["name"]:
        errors.append("Claude marketplace requires owner.name")
    plugins = data.get("plugins")
    entry = None
    if not isinstance(plugins, list):
        errors.append("Claude marketplace plugins must be an array")
    else:
        matching_entries = [item for item in plugins if isinstance(item, dict) and item.get("name") == "research-tree"]
        if not matching_entries:
            errors.append("Claude marketplace is missing the research-tree plugin")
        elif len(matching_entries) != 1:
            errors.append("Claude marketplace defines research-tree more than once")
        else:
            entry = matching_entries[0]
    package = root / PACKAGE_RELATIVES["claude"]
    expected_source = "./packages/claude-code/research-tree"
    if isinstance(entry, dict):
        if entry.get("source") != expected_source:
            errors.append("Claude marketplace research-tree source is incorrect")
        if project_version is not None and entry.get("version") != project_version:
            errors.append("Claude marketplace plugin version differs from pyproject.toml")
        source_value = entry.get("source")
        if not isinstance(source_value, str):
            errors.append("Claude marketplace plugin source must be a string")
        else:
            try:
                resolved_source = (root / Path(source_value)).resolve()
                resolved_source.relative_to(root)
                if resolved_source != package.resolve():
                    errors.append("Claude marketplace source does not resolve to the Claude package")
            except ValueError:
                errors.append("Claude marketplace plugin source escapes the repository")
    errors.extend(_validate_plugin_manifest(package, root, project_version))
    plugin_path = package / ".claude-plugin" / "plugin.json"
    if plugin_path.is_file() and isinstance(entry, dict):
        try:
            plugin_data = _load_json(plugin_path, "Claude plugin manifest")
        except ValueError as error:
            errors.append(str(error))
        else:
            if entry.get("name") != plugin_data.get("name"):
                errors.append("Claude marketplace and plugin names differ")
            if entry.get("version") != plugin_data.get("version"):
                errors.append("Claude marketplace and plugin versions differ")
    return {
        "marketplace": str(manifest),
        "valid": not errors,
        "errors": errors,
    }


def validate_package(package: Path, host: str, root: Path = ROOT) -> dict[str, object]:
    root = root.resolve()
    package = package.resolve()
    skill_root = _skill_root(package, host)
    skill_file = skill_root / "SKILL.md"
    skill_relative = _skill_relative(host, Path("SKILL.md"))
    errors: list[str] = []
    if not skill_file.is_file():
        errors.append(f"missing package file: {skill_relative.as_posix()}")
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
        expected_marker = ACTIVATION_MARKERS[host]
        foreign_markers = [marker for candidate, marker in ACTIVATION_MARKERS.items() if candidate != host]
        if text.count(expected_marker) != 1 or any(marker in text for marker in foreign_markers):
            errors.append(f"wrong activation marker for {host}")

    expected_sources: dict[Path, Path] = {}
    for relative in COMMON_FILES:
        expected_sources[_skill_relative(host, relative)] = relative
    if host == "hermes":
        for relative in _hermes_non_executable_files():
            expected_sources[relative] = relative
        try:
            executable_mappings = _hermes_executable_mappings(root)
        except ValueError as error:
            errors.append(str(error))
        else:
            for source_relative, target_relative in executable_mappings:
                expected_sources[target_relative] = source_relative
    else:
        for source_relative, target_relative in COMMON_FILE_MAP:
            expected_sources[_skill_relative(host, target_relative)] = source_relative
    if host == "codex":
        for relative in CODEX_FILES:
            expected_sources[_skill_relative(host, relative)] = relative
    if host == "claude":
        for relative in CLAUDE_FILES:
            expected_sources[_skill_relative(host, relative)] = relative
        expected_sources[Path(".claude-plugin/plugin.json")] = CLAUDE_PLUGIN_SOURCE
    for source_relative, target_relative in HOST_FILE_MAP[host]:
        expected_sources[_skill_relative(host, target_relative)] = source_relative
    expected_files = {skill_relative, *expected_sources}
    actual_files = {path.relative_to(package) for path in package.rglob("*") if path.is_file()}
    for relative in sorted(expected_files - actual_files):
        errors.append(f"missing package file: {relative.as_posix()}")
    for relative in sorted(actual_files - expected_files):
        errors.append(f"unexpected package file: {relative.as_posix()}")
    for relative, source_relative in expected_sources.items():
        package_file = package / relative
        source_file = root / source_relative
        if package_file.is_file() and source_file.is_file():
            if package_file.read_bytes() != source_file.read_bytes():
                errors.append(f"stale package file: {relative.as_posix()}")
    if host == "claude":
        try:
            project_version = _project_version(root)
        except ValueError as error:
            errors.append(str(error))
            project_version = None
        errors.extend(_validate_plugin_manifest(package, root, project_version))

    resources = sorted(set(RESOURCE_RE.findall(text)))
    for relative in resources:
        if not (skill_root / relative).is_file():
            errors.append(f"missing referenced resource: {relative}")

    has_hermes_material = (
        "Hermes runtime adapter" in text
        or (skill_root / "references/hermes-agent-compatibility.md").exists()
        or (skill_root / "references/hermes-native-orchestration.md").exists()
        or (skill_root / "scripts/hermes_runtime_hook.py").exists()
        or (skill_root / "scripts/hermes_skill_adapter.py").exists()
    )
    if host == "hermes" and not has_hermes_material:
        errors.append("Hermes package is missing its compatibility adapter")
    if host != "hermes" and has_hermes_material:
        errors.append(f"{host} package contains Hermes-only compatibility material")

    has_claude_material = (
        "Claude Code runtime adapter" in text
        or (skill_root / "references/claude-code-compatibility.md").exists()
        or (skill_root / "references/claude-native-orchestration.md").exists()
    )
    if host == "claude" and not has_claude_material:
        errors.append("Claude package is missing its host adapter")
    if host != "claude" and has_claude_material:
        errors.append(f"{host} package contains Claude-only compatibility material")

    has_codex_material = (
        "Codex CLI runtime adapter" in text
        or (skill_root / "references/codex-cli-compatibility.md").exists()
        or (skill_root / "references/codex-native-orchestration.md").exists()
    )
    if host == "codex" and not has_codex_material:
        errors.append("Codex package is missing its host adapter")
    if host != "codex" and has_codex_material:
        errors.append(f"{host} package contains Codex-only compatibility material")

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
    if host == "codex" and not (skill_root / "agents/openai.yaml").is_file():
        errors.append("Codex package is missing agents/openai.yaml")
    if host != "codex" and (skill_root / "agents/openai.yaml").exists():
        errors.append(f"{host} package contains Codex-only agents/openai.yaml")
    if host == "hermes" and not errors:
        errors.extend(_validate_hermes_executable_package(package))

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
            skill_staged = _skill_root(staged, host)
            skill_staged.mkdir(parents=True)
            (skill_staged / "SKILL.md").write_text(_render_skill(host, root), encoding="utf-8", newline="\n")
            _copy_files(root, skill_staged, COMMON_FILES)
            if host == "codex":
                _copy_mapped_files(root, skill_staged, COMMON_FILE_MAP)
                _copy_files(root, skill_staged, CODEX_FILES)
            if host == "claude":
                _copy_mapped_files(root, skill_staged, COMMON_FILE_MAP)
                _copy_files(root, skill_staged, CLAUDE_FILES)
                plugin_manifest = staged / ".claude-plugin" / "plugin.json"
                plugin_manifest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / CLAUDE_PLUGIN_SOURCE, plugin_manifest)
            if host == "hermes":
                _copy_files(root, skill_staged, _hermes_non_executable_files())
                _copy_mapped_files(root, skill_staged, _hermes_executable_mappings(root))
            _copy_mapped_files(root, skill_staged, HOST_FILE_MAP[host])
            validation = validate_package(staged, host, root)
            if not validation["valid"]:
                raise ValueError("; ".join(validation["errors"]))

            target = root / relative
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged, target)
            results.append(validate_package(target, host, root))

    marketplace_manifest = root / ".claude-plugin" / "marketplace.json"
    marketplace_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / CLAUDE_MARKETPLACE_SOURCE, marketplace_manifest)
    return {"marketplace": validate_marketplace(root), "packages": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate without rebuilding")
    args = parser.parse_args()
    if args.check:
        result = {
            "marketplace": validate_marketplace(),
            "packages": [validate_package(package_source(host), host) for host in PACKAGE_RELATIVES],
        }
    else:
        result = build_packages()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    packages_valid = all(item["valid"] for item in result["packages"])
    marketplace_valid = result["marketplace"]["valid"]
    return 0 if packages_valid and marketplace_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
