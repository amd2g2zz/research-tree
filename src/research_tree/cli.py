"""Explicit local command boundary for the runtime foundation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from . import application
from .domain import RuntimeStoreError
from .storage import RunStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-tree")
    commands = parser.add_subparsers(dest="command", required=True)

    create_round = commands.add_parser("create-round", help="create an isolated research round")
    create_round.add_argument("--store", type=Path, required=True, help="explicit run-store root")
    create_round.add_argument("--round-id", help="stable round identifier")
    create_round.add_argument("--parent-round", help="existing parent round identifier")

    show_round = commands.add_parser("show-round", help="show a reconstructed round")
    show_round.add_argument("--store", type=Path, required=True, help="explicit run-store root")
    show_round.add_argument("--round-id", required=True, help="stored round identifier")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    store = RunStore(arguments.store)
    try:
        if arguments.command == "create-round":
            record = application.create_round(
                store,
                arguments.round_id,
                parent_round_id=arguments.parent_round,
            )
            output = record.to_dict()
        else:
            output = application.load_round(store, arguments.round_id).to_dict()
    except RuntimeStoreError as error:
        parser.error(str(error))
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
