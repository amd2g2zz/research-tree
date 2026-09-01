"""Run the gate-7 failure-injection matrix and emit one canonical receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from host_matrix import HOSTS, SCENARIOS, build_receipt, run_scenario  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True, help="directory for the matrix run workspaces")
    parser.add_argument("--result", type=Path, required=True, help="path for the canonical receipt JSON")
    parser.add_argument("--hosts", default=",".join(HOSTS), help="comma-separated subset of hosts")
    parser.add_argument("--scenarios", default=",".join(SCENARIOS), help="comma-separated subset of scenarios")
    arguments = parser.parse_args(argv)

    hosts = tuple(item.strip() for item in arguments.hosts.split(",") if item.strip())
    scenarios = tuple(item.strip() for item in arguments.scenarios.split(",") if item.strip())
    unknown = [item for item in (*hosts, *scenarios) if item not in (*HOSTS, *SCENARIOS)]
    if unknown:
        parser.error(f"unknown host/scenario selection: {unknown}")

    cells = [run_scenario(scenario, host, arguments.workspace) for host in hosts for scenario in scenarios]
    receipt = build_receipt(cells)
    arguments.result.parent.mkdir(parents=True, exist_ok=True)
    arguments.result.write_text(
        json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": receipt["status"], "cells": len(receipt["cells"])}, ensure_ascii=True))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
