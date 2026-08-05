"""Verify the minimum immutable alpha2 release manifest shape."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = {"source_revision", "host_packages", "schema_versions", "test_commands", "gate_results", "limitations"}


def verify(path: Path) -> dict[str, object]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"valid": False, "errors": [str(exc)]}
    if not isinstance(data, dict):
        errors.append("manifest must be an object")
    else:
        errors.extend(f"missing manifest field: {key}" for key in sorted(REQUIRED - set(data)))
        if data.get("gate_results", {}).get("false_completion") is not False:
            errors.append("false_completion gate must be explicitly false")
    return {"schema": 1, "errors": errors, "valid": not errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = verify(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
