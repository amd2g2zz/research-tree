"""Enforce evidence-bearing Definition-of-Done records for alpha2 tasks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


REQUIRED = ("task_id", "code", "focused_tests", "regression", "documentation", "migration_notes", "evidence_refs")


def check_task(record: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for field in REQUIRED:
        value = record.get(field)
        if field == "task_id":
            if not isinstance(value, str) or not value.strip():
                errors.append("task_id is required")
        elif not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
            errors.append(f"{field} must be a nonempty string array")
    acceptance = record.get("acceptance")
    if not isinstance(acceptance, Mapping) or acceptance.get("status") not in {"passed", "not_applicable"} or not acceptance.get("command"):
        errors.append("acceptance.command and a passed/not_applicable status are required")
    return {"schema_version": 1, "task_id": record.get("task_id"), "valid": not errors, "errors": errors}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    args = parser.parse_args(argv)
    result = check_task(json.loads(args.record.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
