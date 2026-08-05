#!/usr/bin/env python3
"""Codex-native entrypoint for the shared execution/event runtime."""

from __future__ import annotations

import sys

from native_execution_adapter import main as _runtime_main


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--host" in arguments:
        index = arguments.index("--host")
        if index + 1 >= len(arguments) or arguments[index + 1] != "codex":
            raise SystemExit("codex adapter only accepts --host codex")
    else:
        arguments = ["--host", "codex", *arguments]
    return _runtime_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
