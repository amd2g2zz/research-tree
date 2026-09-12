"""Impact-scope audit gate: reconcile changed symbols/files with a declared scope.

Plan §三 (issue #501): every openspec change declares an ``impact_scope``
(sidecar JSON under the change's ``evidence/`` directory); before push, the
GitNexus ``detect-changes`` output is reconciled against it — anything changed
outside the declared scope fails the gate.

Machine-readable limitation, verified on the installed GitNexus CLI
(``node .gitnexus/run.cjs detect-changes --help``, v indexed 2026-09-03): the
command supports ``--scope unstaged|staged|all|compare`` / ``--base-ref`` /
``--repo`` but has no ``--json`` (or similar) flag and prints a
human-readable report ("Changed symbols:", "Affected execution flows:",
"Risk level: high"). It therefore cannot emit machine-readable output
non-interactively, and parsing that prose would be version-fragile theater.
Two consumption modes are provided instead:

- ``--detect-changes-report PATH``: a JSON report saved next to the CLI run
  (for future GitNexus versions that gain a JSON flag, or for tooling that
  exports one). Accepted shapes: a top-level object with a list under one of
  ``changed_symbols`` / ``symbols`` / ``changed_files`` / ``files``; list
  entries are either path strings or objects carrying the path under ``file``
  / ``path`` / ``file_path`` / ``filepath``.
- ``--diff-base REF`` (equivalent audit, used on this PR): ``git diff
  --name-only REF...HEAD`` cross-referenced against the declared scope. This
  is a FILE-LEVEL audit, not a symbol-level one — a symbol changed inside a
  declared file is visible to the GitNexus CLI report and the PR-reviewer
  checklist, not to this mode. The limitation is inherent to the CLI gap
  above and is recorded in the PR template checklist.

Deterministic, offline, no MCP dependency. Exit codes: 0 = inside scope,
1 = changed paths outside scope (offenders named), 2 = invalid input.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "impact-scope-v1"
_REPORT_LIST_KEYS = ("changed_symbols", "symbols", "changed_files", "files")
_REPORT_ENTRY_PATH_KEYS = ("file", "path", "file_path", "filepath")


class ImpactScopeError(ValueError):
    """Invalid impact-scope sidecar, detect-changes report, or git input."""


def load_impact_scope(path: Path) -> dict[str, Any]:
    """Load and validate an ``impact-scope-v1`` sidecar."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImpactScopeError(f"invalid impact-scope sidecar: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ImpactScopeError(f"impact-scope sidecar must be an object: {path}")
    if payload.get("schema") != SCHEMA:
        raise ImpactScopeError(f"impact-scope sidecar schema must be {SCHEMA!r}: {path}")
    change = payload.get("change")
    if not isinstance(change, str) or not change:
        raise ImpactScopeError("impact-scope sidecar change must be a non-empty string")
    files = payload.get("files")
    if not isinstance(files, list) or any(not isinstance(item, str) or not item for item in files):
        raise ImpactScopeError("impact-scope sidecar files must be a list of non-empty strings")
    if len(set(files)) != len(files):
        raise ImpactScopeError("impact-scope sidecar files must be unique")
    symbols = payload.get("symbols", [])
    if not isinstance(symbols, list):
        raise ImpactScopeError("impact-scope sidecar symbols must be a list")
    for symbol in symbols:
        if not isinstance(symbol, dict) or not isinstance(symbol.get("name"), str) or not symbol["name"]:
            raise ImpactScopeError("impact-scope sidecar symbol entries need a non-empty name")
        if not isinstance(symbol.get("file"), str) or symbol["file"] not in files:
            raise ImpactScopeError(
                f"impact-scope sidecar symbols entry {symbol.get('name')!r} must reference a declared file"
            )
    return payload


def changed_files_from_report(path: Path) -> tuple[str, ...]:
    """Extract changed file paths from a saved detect-changes JSON report."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImpactScopeError(f"unreadable detect-changes report: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ImpactScopeError(f"unrecognized detect-changes report shape (top level must be an object): {path}")
    entries: list[Any] | None = None
    for key in _REPORT_LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            entries = value
            break
    if entries is None:
        raise ImpactScopeError(f"unrecognized detect-changes report shape (no {_REPORT_LIST_KEYS} list): {path}")
    files: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            files.append(entry)
            continue
        if isinstance(entry, Mapping):
            for key in _REPORT_ENTRY_PATH_KEYS:
                value = entry.get(key)
                if isinstance(value, str) and value:
                    files.append(value)
                    break
            else:
                raise ImpactScopeError(f"detect-changes report entry carries no file path: {entry!r}")
            continue
        raise ImpactScopeError(f"detect-changes report entry must be a path string or object: {entry!r}")
    return tuple(sorted(set(files)))


def changed_files_from_diff(repository: Path, base: str) -> tuple[str, ...]:
    """List files changed in ``base...HEAD`` (documented fallback mode)."""
    command = ["git", "-C", str(Path(repository)), "diff", "--name-only", f"{base}...HEAD"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise ImpactScopeError(f"git diff failed: {' '.join(command)}: {exc}") from exc
    if completed.returncode != 0:
        raise ImpactScopeError(f"git diff failed ({completed.returncode}): {completed.stderr.strip()}")
    return tuple(sorted({line for line in completed.stdout.splitlines() if line}))


def audit_impact_scope(scope: Mapping[str, Any], changed_files: Sequence[str]) -> dict[str, Any]:
    """Reconcile changed paths against the declared scope; fail closed."""
    declared = set(scope["files"])
    undeclared = sorted(path for path in changed_files if path not in declared)
    return {
        "ok": not undeclared,
        "change": scope["change"],
        "changed_files": sorted(set(changed_files)),
        "undeclared": undeclared,
        "declared_files": sorted(declared),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile changed symbols/files with a declared impact scope")
    parser.add_argument("--impact-scope", type=Path, required=True, help="impact-scope-v1 sidecar JSON path")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root for the git-diff fallback")
    parser.add_argument("--detect-changes-report", type=Path, help="saved detect-changes JSON report")
    parser.add_argument("--diff-base", help="git base ref for the documented file-level fallback (e.g. dev)")
    args = parser.parse_args(argv)

    if bool(args.detect_changes_report) == bool(args.diff_base):
        parser.error("provide exactly one change source: --detect-changes-report or --diff-base")
    try:
        scope = load_impact_scope(args.impact_scope)
        if args.detect_changes_report is not None:
            changed = changed_files_from_report(args.detect_changes_report)
            mode = "detect-changes-report"
        else:
            changed = changed_files_from_diff(args.repo, args.diff_base)
            mode = "git-diff"
        report = audit_impact_scope(scope, changed)
    except ImpactScopeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    report["mode"] = mode
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
