"""Reserved command boundary for the canonical research runtime."""

from __future__ import annotations

import argparse
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="research-tree",
        description="Reserved command boundary for the canonical research runtime.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.error("no canonical research-tree commands are registered")
    return 2
