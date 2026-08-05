"""Check that normative documentation points to existing canonical sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def check(root: Path) -> dict[str, object]:
    registry = root / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries" / "documentation-authority-v1.json"
    errors: list[str] = []
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"valid": False, "errors": [str(exc)]}
    entries = data.get("entries", data.get("documents", []))
    if not isinstance(entries, list):
        errors.append("documentation registry must expose entries")
        entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("documentation registry contains a non-object entry")
            continue
        locator = entry.get("path") or entry.get("canonical_source") or entry.get("locator")
        if entry.get("lifecycle") not in {None, "historical", "superseded", "active-per-change", "active-or-superseded", "historical-unless-indexed", "rebuildable"} and locator and not ((root / str(locator)).is_file() or (root / str(locator)).is_dir()):
            errors.append(f"missing active documentation source: {locator}")
    return {"schema": 1, "errors": errors, "valid": not errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    result = check(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
