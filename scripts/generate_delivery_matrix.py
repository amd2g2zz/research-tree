"""Generate a requirement-level delivery matrix from OpenSpec requirements."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIREMENT_RE = re.compile(r"^### Requirement:\s*(.+?)\s*$", re.MULTILINE)


def generate(change_dir: Path) -> dict[str, object]:
    registry_path = change_dir / "registries" / "delivery-matrix-v1.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    default_black_box_cases = list(registry.get("default_black_box_cases", []))
    capabilities = {
        item["capability"]: item for item in registry.get("capability_rows", [])
    }
    overrides = {
        item["requirement_id"]: item
        for item in registry.get("requirement_overrides", [])
    }
    rows: list[dict[str, object]] = []
    for spec in sorted((change_dir / "specs").glob("*/spec.md")):
        text = spec.read_text(encoding="utf-8")
        capability = spec.parent.name
        for title in REQUIREMENT_RE.findall(text):
            slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
            capability_defaults = capabilities.get(capability, {})
            row = {
                "requirement_id": f"{capability}/{slug}",
                "source_modules": capability_defaults.get("source_modules", []),
                "public_surface": capability_defaults.get("public_surface", []),
                "migration_impact": "review",
                "unit_tests": [], "integration_tests": [],
                "black_box_cases": capability_defaults.get(
                    "black_box_cases", default_black_box_cases
                ),
                "evidence_artifact": None,
                "github_issue": capability_defaults.get("github_issue"),
                "owner": capability_defaults.get("owner"),
                "status": "planned",
            }
            override = overrides.pop(row["requirement_id"], None)
            if override is not None:
                row.update({key: value for key, value in override.items() if key != "requirement_id"})
            rows.append(row)
    if overrides:
        raise ValueError(
            "delivery matrix overrides reference unknown requirements: "
            + ", ".join(sorted(overrides))
        )
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
