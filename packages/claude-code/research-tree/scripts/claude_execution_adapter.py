#!/usr/bin/env python3
"""Claude Code-native entrypoint for the shared execution/event runtime."""

from __future__ import annotations

import sys

from native_execution_adapter import main as _runtime_main


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--host" in arguments:
        index = arguments.index("--host")
        if index + 1 >= len(arguments) or arguments[index + 1] != "claude":
            raise SystemExit("Claude Code adapter only accepts --host claude")
    else:
        arguments = ["--host", "claude", *arguments]
    return _runtime_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
