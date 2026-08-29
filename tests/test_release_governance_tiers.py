"""Issue #331: release-governance claims must be tiered, per-issue, and rolling-Alpha aligned."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TIERS = ("published", "alpha-pilot-suitable", "org-rollout-ready", "unattended-final-authority")
AUTHORITY = ROOT / "docs/governance/documentation-authority.md"
GATE_DECLARATION = re.compile(
    r"(?m)^\s*-\s+#\d+[^\n]*$",
)
GATE_TIER_LIST = re.compile(
    r"gates\s+((?:[a-z-]+)(?:,\s*[a-z-]+)*)",
    re.IGNORECASE,
)


def test_authority_document_defines_all_four_claim_tiers() -> None:
    text = AUTHORITY.read_text(encoding="utf-8")
    for tier in TIERS:
        assert tier in text, f"documentation-authority.md must define the '{tier}' claim tier"


def test_open_evaluation_issues_declare_gate_boundaries() -> None:
    gate_section = AUTHORITY.read_text(encoding="utf-8").split("## Release claim tiers")[-1]
    for issue in ("#67", "#84", "#292", "#323"):
        assert re.search(rf"{issue}\b[^\n]*\b[Gg]ates\b", gate_section), (
            f"{issue} must have a 'gates ...' declaration line in the tier section"
        )
        assert re.search(rf"{issue}\b[^\n]*\bdoes not gate\b", gate_section, re.IGNORECASE), (
            f"{issue} must declare which claims it does not gate"
        )


def test_gate_declarations_reference_only_known_tiers() -> None:
    text = AUTHORITY.read_text(encoding="utf-8")
    section = text.split("## Release claim tiers")[-1]
    for line in GATE_DECLARATION.finditer(section):
        for match in GATE_TIER_LIST.finditer(line.group(0)):
            for tier in re.split(r",\s*", match.group(1)):
                assert tier.strip().lower() in TIERS, f"unknown tier: {tier}"


def test_absolute_blocking_language_is_absent_from_active_governance() -> None:
    for path in (
        AUTHORITY,
        ROOT / "docs/governance/evaluation-assets.md",
        ROOT / "docs/evaluation/README.md",
    ):
        text = path.read_text(encoding="utf-8")
        for phrase in (
            "releasable only when all",
            "cannot release until",
            "blocks any release",
            "no release until",
        ):
            assert phrase not in text, f"{path.name} still contains '{phrase}'"
