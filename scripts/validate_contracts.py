"""Validate alpha2 JSON schema assets and encoding invariants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_tree import ContractRegistry, ContractRegistryError


def validate(root: Path) -> dict[str, object]:
    schema_root = root / "openspec" / "changes" / "unify-research-runtime-alpha2" / "schemas"
    registry = ContractRegistry(schema_root)
    checked: list[str] = []
    errors: list[str] = []
    for schema_name in registry.schema_names():
        try:
            registry.validator(schema_name)
            checked.append((schema_root / schema_name).relative_to(root).as_posix())
        except ContractRegistryError as exc:
            errors.append(str(exc))
    example_counts = {"valid_examples": 0, "invalid_examples": 0}
    if not errors:
        try:
            example_counts = registry.validate_examples()
        except ContractRegistryError as exc:
            errors.append(str(exc))
    return {
        "schema": 1,
        "checked": checked,
        **example_counts,
        "errors": errors,
        "valid": not errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    result = validate(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
