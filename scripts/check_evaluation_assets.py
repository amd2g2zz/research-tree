"""Validate governed evaluation case and result paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def check(root: Path) -> dict[str, object]:
    cases = root / "evaluation" / "cases"
    errors: list[str] = []
    checked: list[str] = []
    if not cases.is_dir():
        errors.append("evaluation/cases is missing")
    else:
        for path in sorted(cases.glob("*.json")):
            checked.append(path.relative_to(root).as_posix())
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cases = data.get("cases", [data]) if isinstance(data, dict) else []
                if not isinstance(cases, list):
                    errors.append(f"{path.name}: cases must be a list")
                    cases = []
                for case in cases:
                    if not isinstance(case, dict):
                        errors.append(f"{path.name}: case is not an object")
                        continue
                    for key in ("id", "corpus_version", "public_materials", "hidden_oracle_id"):
                        if key not in case:
                            errors.append(f"{path.name}: missing {key}")
                    if any(key in case for key in ("patch", "hidden_oracle", "eventual_patch")):
                        errors.append(f"{path.name}: hidden material leaked into public case")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"{path.name}: {exc}")
    return {"schema": 1, "checked": checked, "errors": errors, "valid": not errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    result = check(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
