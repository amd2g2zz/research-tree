"""Replay a retained, redacted Alpha2 release manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research_tree import ReleaseManifest, evaluate_release


def run(path: Path) -> dict[str, Any]:
    retained = json.loads(path.read_text(encoding="utf-8"))
    decision = evaluate_release(ReleaseManifest.from_mapping(retained["release_manifest"]))
    return decision.to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=Path("evaluation/results/alpha2-release-candidate-v1.json"),
    )
    args = parser.parse_args()
    result = run(args.manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
