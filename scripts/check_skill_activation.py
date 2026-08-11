"""Construct or explicitly execute bounded cross-host activation probes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from research_tree.skill_activation import SUPPORTED_HOSTS, build_activation_probe, run_native_probes
from research_tree.skill_setup import resolve_skill_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--host", action="append", choices=("all", *SUPPORTED_HOSTS))
    parser.add_argument("--correlation-prefix", default="activation-check")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="explicitly launch available native hosts; construction alone is side-effect free",
    )
    return parser


def _selected_hosts(values: Sequence[str] | None) -> tuple[str, ...]:
    if not values or "all" in values:
        return SUPPORTED_HOSTS
    return tuple(dict.fromkeys(values))


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    source = arguments.source.expanduser().resolve()
    probes = {
        host: build_activation_probe(
            host,
            resolve_skill_source(source, host),
            correlation_id=f"{arguments.correlation_prefix}-{host}",
        )
        for host in _selected_hosts(arguments.host)
    }
    output: dict[str, object] = {"schema_version": 1, "probes": probes, "executed": arguments.execute}
    if arguments.execute:
        output["results"] = run_native_probes(probes)
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
