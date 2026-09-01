from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGE = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2"


def test_required_alpha2_adrs_define_the_architecture_boundaries() -> None:
    expected = {
        "ADR-002-single-completion-authority.md": [
            "## Context",
            "## Decision",
            "## Consequences",
            "## Rejected Alternatives",
            "## Migration",
            "ResearchRunCoordinator",
            "host, worker, hook, or report",
        ],
        "ADR-003-separate-graph-boundaries.md": [
            "## Context",
            "## Decision",
            "## Consequences",
            "## Rejected Alternatives",
            "## Migration",
            "rebuildable projection",
        ],
        "ADR-004-sqlite-and-content-addressed-storage.md": [
            "## Context",
            "## Decision",
            "## Consequences",
            "## Rejected Alternatives",
            "## Migration",
            "SQLite",
            "content-addressed",
        ],
        "ADR-005-host-adapters-as-event-translators.md": [
            "## Context",
            "## Decision",
            "## Consequences",
            "## Rejected Alternatives",
            "## Migration",
            "HostEvent",
            "fail-open",
        ],
    }
    for filename, required_text in expected.items():
        content = " ".join((ROOT / "docs" / "adr" / filename).read_text(encoding="utf-8").split())
        for text in required_text:
            assert text in content, f"{filename} is missing {text!r}"


def test_ratification_registry_and_contract_inputs_remain_aligned() -> None:
    issue_map = json.loads((CHANGE / "registries" / "issue-execution-map-v1.json").read_text(encoding="utf-8"))
    issue_66 = next(item for item in issue_map["issues"] if item["issue"] == 66)

    assert issue_66["primary_group"] == 14
    assert issue_66["openspec_change"] == "ratify-alpha2-runtime-contract"
    assert (CHANGE / "registries" / "lifecycle-matrix-v1.json").is_file()
    for capability in ("canonical-runtime-contract", "durable-research-runtime", "host-event-protocol"):
        assert (CHANGE / "specs" / capability / "spec.md").is_file()
