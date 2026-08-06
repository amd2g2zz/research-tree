"""Generate a requirement-level delivery matrix from OpenSpec requirements."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIREMENT_RE = re.compile(r"^### Requirement:\s*(.+?)\s*$", re.MULTILINE)


def generate(change_dir: Path) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for spec in sorted((change_dir / "specs").glob("*/spec.md")):
        text = spec.read_text(encoding="utf-8")
        capability = spec.parent.name
        for title in REQUIREMENT_RE.findall(text):
            slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
            rows.append({
                "requirement_id": f"{capability}/{slug}",
                "source_modules": [], "public_surface": [], "migration_impact": "review",
                "unit_tests": [], "integration_tests": [], "black_box_cases": [],
                "evidence_artifact": None, "github_issue": None, "owner": None, "status": "planned",
            })
    return {"schema_version": 1, "generated_from": "OpenSpec Requirement headings", "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--change", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = generate(args.change.resolve())
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output.resolve()), "row_count": len(value["rows"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
