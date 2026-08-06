#!/usr/bin/env python3
"""Verify a host package's activation contract and write a safe receipt.

This script validates package identity, not model behavior.  A receipt proves
that an activated instruction asked the current host to use this package; it
does not prove that every later model response followed those instructions.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Sequence


SKILL_NAME = "research-tree"
SENTINELS = {
    "codex": "RT-ACTIVE-V1-CODEX",
    "claude": "RT-ACTIVE-V1-CLAUDE",
    "hermes": "RT-ACTIVE-V1-HERMES",
}
MARKER_RE = re.compile(
    r"<!--\s*research-tree-activation:\s*([a-z]+):([A-Z0-9-]+)\s*-->"
)
REQUIRED_RESOURCES = (
    "references/research-quality-playbook.md",
    "references/alignment-controller.md",
)


class ActivationReceiptError(ValueError):
    """Raised when the selected package cannot prove its own contract."""


def default_skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def verify(skill_dir: Path, host: str) -> dict[str, object]:
    """Return stable package evidence or raise a bounded diagnostic error."""
    skill_dir = skill_dir.expanduser().resolve()
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        raise ActivationReceiptError(f"missing SKILL.md: {skill_file}")
    raw = skill_file.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ActivationReceiptError("SKILL.md has a UTF-8 BOM before frontmatter")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ActivationReceiptError("SKILL.md is not UTF-8") from exc
    if not text.startswith("---"):
        raise ActivationReceiptError("SKILL.md must start with YAML frontmatter")
    if not re.search(r"(?m)^name:\s*research-tree\s*$", text):
        raise ActivationReceiptError("SKILL.md does not declare name: research-tree")

    expected = SENTINELS[host]
    markers = MARKER_RE.findall(text)
    if markers != [(host, expected)]:
        raise ActivationReceiptError("SKILL.md activation marker does not match host")
    if "--activation-probe" not in text:
        raise ActivationReceiptError("SKILL.md is missing the activation probe contract")
    missing = [
        relative for relative in REQUIRED_RESOURCES if not (skill_dir / relative).is_file()
    ]
    if missing:
        raise ActivationReceiptError("missing activation resource(s): " + ", ".join(missing))

    return {
        "schema_version": 1,
        "skill": SKILL_NAME,
        "host": host,
        "sentinel": expected,
        "skill_dir": str(skill_dir),
        "skill_sha256": hashlib.sha256(raw).hexdigest(),
        "required_resources": list(REQUIRED_RESOURCES),
    }


def write_receipt(workspace: Path, evidence: dict[str, object]) -> Path:
    """Atomically persist non-sensitive activation evidence under the workspace."""
    workspace = workspace.expanduser().resolve()
    destination = workspace / ".research-tree" / "activation" / "receipt.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **evidence,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "scope": "package-contract-only",
        "does_not_prove": [
            "that a particular host injected the full SKILL.md body",
            "that a model followed every instruction after activation",
        ],
    }
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(destination)
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, choices=tuple(SENTINELS))
    parser.add_argument("--skill-dir", type=Path, default=default_skill_dir())
    parser.add_argument("--workspace", type=Path)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="validate the package without creating a workspace receipt",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        evidence = verify(arguments.skill_dir, arguments.host)
        receipt = None
        if not arguments.verify_only:
            if arguments.workspace is None:
                raise ActivationReceiptError("--workspace is required unless --verify-only is set")
            receipt = write_receipt(arguments.workspace, evidence)
    except (ActivationReceiptError, OSError) as exc:
        print(json.dumps({"verified": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "verified": True,
                "evidence": evidence,
                "receipt": str(receipt) if receipt is not None else None,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
