#!/usr/bin/env python3
"""Run the source checkout without requiring an ambient PYTHONPATH.

This launcher is intentionally tiny: it resolves the repository root from its
own location, prepends ``src`` for this process only, and delegates to the
canonical CLI entry point. Installed users should use the ``research-tree``
console script instead.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    source = root / "src"
    if not source.is_dir():
        print(f"source checkout is missing package root: {source}", file=sys.stderr)
        return 2
    source_text = str(source)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
    from research_tree.cli import main as cli_main

    return int(cli_main(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
