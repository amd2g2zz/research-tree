"""Run the redacted alpha2 Claude/GLM fixture against a sanitized trace JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.harness.claude_glm52_fixture import evaluate_trace


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.trace.read_text(encoding="utf-8"))
    trace = value.get("trace") if isinstance(value, dict) else value
    if not isinstance(trace, list):
        parser.error("trace JSON must be a list or an object containing trace")
    result = evaluate_trace(trace)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
