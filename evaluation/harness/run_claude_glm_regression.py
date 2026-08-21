"""Run the deterministic synthetic Claude Code and GLM regression fixture."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

DEFAULT_CASE = Path("evaluation/cases/claude-glm-regression-synthetic-v1.json")


def _fixture_module():
    path = Path(__file__).with_name("claude_glm_regression.py")
    spec = importlib.util.spec_from_file_location("claude_glm_regression", path)
    if spec is None or spec.loader is None:
        raise ValueError("unable to load the Claude/GLM fixture harness")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_mapping(path: Path, field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must be a JSON object")
    return payload


def _load_trace(path: Path) -> list[dict[str, Any]]:
    payload = _load_mapping(path, "trace")
    trace = payload.get("trace")
    if not isinstance(trace, list) or not all(isinstance(record, dict) for record in trace):
        raise ValueError("trace must be an object containing a list of event objects")
    return trace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--expect-status", choices=("passed", "failed", "unavailable"))
    args = parser.parse_args(argv)
    try:
        fixture = _fixture_module()
        case = fixture.load_case(args.case)
        trace = _load_trace(args.trace) if args.trace else fixture.synthetic_control_trace()
        comparison = (
            _load_mapping(args.comparison, "comparison") if args.comparison else fixture.unavailable_comparison()
        )
        result = fixture.evaluate_fixture(case, trace, comparison)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.expect_status:
        return 0 if result["status"] == args.expect_status else 1
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
