"""Run one registered Alpha2 task command and write a JSON receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_tree.verification_receipts import generate_receipt, local_verification_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--group", type=int, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repo.resolve()
    registry = (
        repository / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries" / "task-execution-v1.json"
    )
    receipt_path = local_verification_path(repository, args.receipt)
    receipt = generate_receipt(repository, registry, args.group, args.output)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if receipt["exit_code"] == 0 else int(receipt["exit_code"] or 1)


if __name__ == "__main__":
    raise SystemExit(main())
