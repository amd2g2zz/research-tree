#!/usr/bin/env python3
"""Fail-open lifecycle hook launcher for host hooks (issue #453).

Runs with plain system Python: no uv, no virtual environment, no project
context required. When the current workspace is not a Research Tree checkout
the launcher exits 0 with a single labeled host response, so a globally
registered hook can never surface an error inside a host session.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

CHECKOUT_MARKERS = ("pyproject.toml", "packages", "skill-src")
LAUNCHER_HOSTS = ("codex", "claude", "hermes")


def _find_checkout(start: Path) -> Path | None:
    """Return the nearest Research Tree checkout containing ``start``."""
    current = start.resolve(strict=False)
    for candidate in (current, *current.parents):
        if all((candidate / marker).exists() for marker in CHECKOUT_MARKERS):
            return candidate
    return None


def _module_dir(root: Path | None) -> Path | None:
    """Return the directory providing the ``lifecycle_hook`` module."""
    sibling = Path(__file__).resolve().parent / "lifecycle_hook.py"
    if sibling.is_file():
        return sibling.parent
    if root is not None:
        candidate = root / "src" / "research_tree"
        if (candidate / "lifecycle_hook.py").is_file():
            return candidate
    return None


def _labeled_response(host: str) -> str:
    """Return one balanced <rt:event> labeled host response."""
    if host == "hermes":
        body = "{}"
    else:
        body = '{"continue": true}'
    opening = f'<rt:event contract="research-tree-hook" schema_version="1" host="{host}">'
    return opening + body + "</rt:event>"


def _host_of(argv: list[str]) -> str:
    for index, value in enumerate(argv):
        if value == "--host" and index + 1 < len(argv):
            host = argv[index + 1]
            return host if host in LAUNCHER_HOSTS else "claude"
    return "claude"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    host = _host_of(argv)
    try:
        root = _find_checkout(Path.cwd())
        module = None
        try:
            module_dir = _module_dir(root)
            if module_dir is not None:
                sys.path.insert(0, str(module_dir))
                module = importlib.import_module("lifecycle_hook")
        except Exception:
            module = None
        if module is not None:
            try:
                module.main(argv)
                return 0
            except SystemExit as exc:
                if exc.code in (0, None):
                    return 0
                raise
    except BaseException:
        pass
    print(_labeled_response(host))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
