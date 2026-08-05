"""Validate alpha2 JSON schema assets and encoding invariants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate(root: Path) -> dict[str, object]:
    schema_root = root / "openspec" / "changes" / "unify-research-runtime-alpha2" / "schemas"
    checked: list[str] = []
    errors: list[str] = []
    for path in sorted(schema_root.glob("*.json")):
        try:
            raw = path.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                errors.append(f"{path.name}: UTF-8 BOM")
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict) or "$schema" not in value:
                errors.append(f"{path.name}: missing JSON Schema declaration")
            checked.append(path.relative_to(root).as_posix())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
    return {"schema": 1, "checked": checked, "errors": errors, "valid": not errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    result = validate(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
