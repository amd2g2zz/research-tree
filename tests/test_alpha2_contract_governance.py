from __future__ import annotations

from pathlib import Path

from scripts.generate_delivery_matrix import generate


ROOT = Path(__file__).parents[1]
CHANGE = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2"


def test_alpha2_architecture_decisions_are_explicit_and_supersede_alpha1() -> None:
    adr_root = ROOT / "docs" / "adr"
    alpha1 = (adr_root / "ADR-001-runtime-foundation.md").read_text(encoding="utf-8")
    assert "Status: Superseded" in alpha1
    assert "ADR-004" in alpha1
    assert "鏂" not in alpha1

    expected = {
        "ADR-002-single-completion-authority.md",
        "ADR-003-separate-graph-boundaries.md",
        "ADR-004-sqlite-and-content-addressed-storage.md",
        "ADR-005-host-adapters-as-event-translators.md",
    }
    for name in expected:
        text = (adr_root / name).read_text(encoding="utf-8")
        assert "Status: Accepted" in text
        for heading in (
            "## Context",
            "## Decision",
            "## Consequences",
            "## Rejected Alternatives",
            "## Migration",
        ):
            assert heading in text, f"{name} lacks {heading}"


def test_every_openspec_requirement_has_issue_owner_and_black_box_oracle() -> None:
    rows = generate(CHANGE)["rows"]
    assert rows
    assert not [row["requirement_id"] for row in rows if not row["github_issue"]]
    assert not [row["requirement_id"] for row in rows if not row["owner"]]
    assert not [row["requirement_id"] for row in rows if not row["black_box_cases"]]


def test_shared_contract_registry_validates_registered_positive_and_negative_examples() -> None:
    from research_tree import ContractRegistry

    counts = ContractRegistry.from_repository(ROOT).validate_examples()
    assert counts["valid_examples"] == counts["invalid_examples"]
    assert counts["valid_examples"] >= 20
