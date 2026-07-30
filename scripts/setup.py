"""Reproducible local setup and verification for research-tree.

This is intentionally a repository bootstrap, not a Python packaging
``setup.py``.  It uses only the standard library so it can run before project
dependencies are installed.  By default it performs no writes; ``--sync`` is
the explicit opt-in that asks uv to create or update the local environment.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MINIMUM_PYTHON = (3, 11)
REQUIRED_FILES = (
    "pyproject.toml",
    "uv.lock",
    "SKILL.md",
    "scripts/engine.py",
    "scripts/project.py",
    "scripts/research_orchestrator.py",
)


def inspect_environment() -> dict[str, Any]:
    """Return a serialisable readiness report without changing local state."""

    missing = [relative for relative in REQUIRED_FILES if not (ROOT / relative).is_file()]
    uv_path = shutil.which("uv")
    python_version = tuple(sys.version_info[:3])
    return {
        "project_root": str(ROOT),
        "python_version": ".".join(map(str, python_version)),
        "python_supported": python_version >= MINIMUM_PYTHON,
        "uv_path": uv_path,
        "required_files_present": not missing,
        "missing_files": missing,
    }


def readiness_errors(report: dict[str, Any]) -> list[str]:
    """Translate a readiness report into stable, user-actionable failures."""

    errors = []
    if not report["python_supported"]:
        errors.append("Python 3.11 or newer is required")
    if not report["required_files_present"]:
        errors.append("required project files are missing: " + ", ".join(report["missing_files"]))
    if not report["uv_path"]:
        errors.append("uv was not found on PATH; install uv before running --sync or --verify")
    return errors


def run_uv(uv_path: str, arguments: list[str]) -> None:
    """Run a fixed uv command without shell interpolation or user command text."""

    environment = os.environ.copy()
    environment.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    subprocess.run([uv_path, *arguments], cwd=ROOT, env=environment, check=True)


def _print_report(report: dict[str, Any], errors: list[str], as_json: bool) -> None:
    if as_json:
        print(json.dumps({"ready": not errors, "checks": report, "errors": errors}, ensure_ascii=False, indent=2))
        return
    print("research-tree setup check")
    print(f"  project root: {report['project_root']}")
    print(f"  Python: {report['python_version']}")
    print(f"  uv: {report['uv_path'] or 'not found'}")
    if errors:
        for error in errors:
            print(f"  error: {error}", file=sys.stderr)
    else:
        print("  status: ready")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="setup",
        description="check, synchronise, and verify a local research-tree checkout",
    )
    parser.add_argument("--check", action="store_true", help="perform readiness checks only (the default)")
    parser.add_argument("--sync", action="store_true", help="run `uv sync --locked` after checks pass")
    parser.add_argument("--verify", action="store_true", help="run the unit-test suite through `uv run --locked`")
    parser.add_argument("--json", action="store_true", help="print the readiness result as JSON")
    args = parser.parse_args(argv)

    report = inspect_environment()
    errors = readiness_errors(report)
    _print_report(report, errors, args.json)
    if errors:
        return 1

    uv_path = report["uv_path"]
    assert isinstance(uv_path, str)  # Established by readiness_errors above.
    if args.sync:
        print("Synchronising locked dependencies...")
        run_uv(uv_path, ["sync", "--locked"])
    if args.verify:
        print("Running unit tests against the locked environment...")
        run_uv(uv_path, ["run", "--locked", "python", "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py", "-v"])
    if args.sync or args.verify:
        print("research-tree setup completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
