#!/usr/bin/env python3
"""Claude Code-native entrypoint for the stateless HostEvent translator."""

from __future__ import annotations

import sys

from host_event_adapter import main as _runtime_main


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--host" in arguments:
        index = arguments.index("--host")
        if index + 1 >= len(arguments) or arguments[index + 1] != "claude-code":
            raise SystemExit("Claude Code adapter only accepts --host claude-code")
    else:
        arguments = ["--host", "claude-code", *arguments]
    return _runtime_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
