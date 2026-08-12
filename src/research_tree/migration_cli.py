"""Explicit command boundary for non-destructive Alpha1 migration work."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .migration import Alpha1MigrationError, Alpha1MigrationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inventory")
    commands.add_parser("project")
    cutover = commands.add_parser("cutover")
    cutover.add_argument("--release-gate", type=Path, required=True)
    commands.add_parser("rollback")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    service = Alpha1MigrationService(arguments.workspace)
    try:
        if arguments.command == "inventory":
            inventory = service.inventory()
            result = {
                "items": [asdict(item) for item in inventory.items],
                "inventory_fingerprint": inventory.fingerprint,
                "completion_authority": "coordinator_only",
            }
        elif arguments.command == "project":
            result = service.write_compatibility_projection()
        elif arguments.command == "cutover":
            gate = json.loads(arguments.release_gate.read_text(encoding="utf-8"))
            result = service.cut_over(gate)
        else:
            result = service.rollback()
    except (Alpha1MigrationError, OSError, json.JSONDecodeError) as error:
        print(str(error), file=__import__("sys").stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
