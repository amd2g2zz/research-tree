"""Check required authoring, package, and evaluation roots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_ROOTS = ("src", "skill-src", "packages", "openspec", "evaluation", "scripts", "tests")


def check(root: Path) -> dict[str, object]:
    errors = [f"missing required root: {name}" for name in REQUIRED_ROOTS if not (root / name).is_dir()]
    return {"schema": 1, "required_roots": list(REQUIRED_ROOTS), "errors": errors, "valid": not errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    result = check(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
