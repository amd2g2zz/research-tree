#!/usr/bin/env python3
"""Audit the repository for alternate canonical completion authorities."""

from __future__ import annotations

import json
from pathlib import Path

from research_tree.authority_audit import audit_completion_authority


def main() -> int:
    result = audit_completion_authority(Path(__file__).resolve().parents[1])
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
