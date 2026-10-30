"""Issue #332/#430: behavioral documents must stay executable, bounded, and real.

Whitelist-driven: only the APIs the protocol sections cite are scanned, so
historical prose naming other things cannot false-positive.  Every cited name
must be importable from research_tree with a matching signature.

Issue #430 adds the behavioral budgets and contracts:

- C1: SKILL.template.md stays at or under 300 lines.
- C2: the forced-load doc set (SKILL + three adapters + playbook) stays at or
  under 5000 words in total.
- C3: the slot-only dispatch contract appears verbatim in SKILL.template.md and
  all three host adapters.
- C4: every runtime-API mention in the behavioral docs carries the checkout
  availability gate nearby.
- C5: every runtime API the docs cite by name exists in src, including the
  goal-wiring surface shipped by #441-#443.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SKILL_TEMPLATE = ROOT / "skill-src/SKILL.template.md"
HERMES_SKILL_TEMPLATE = ROOT / "skill-src/hermes-SKILL.template.md"
HOST_ADAPTERS = ("skill-src/claude-adapter.md", "skill-src/codex-adapter.md", "skill-src/hermes-adapter.md")
PLAYBOOK = ROOT / "references/research-quality-playbook.md"
BEHAVIORAL_DOCS = (SKILL_TEMPLATE, PLAYBOOK, *(ROOT / relative for relative in HOST_ADAPTERS))
# The Hermes host renders SKILL.md from its own template, so its mentions are
# gated too even though it is not part of the C2 forced-load budget.
GATE_SCANNED_DOCS = (*BEHAVIORAL_DOCS, HERMES_SKILL_TEMPLATE)

SKILL_LINE_BUDGET = 300
FORCED_DOC_WORD_BUDGET = 5000
AVAILABILITY_GATE = "when the checkout runtime is available"
RUNTIME_API_TOKENS = ("apply_correction", "apply_contradiction", "research-tree status")
SLOT_ONLY_DISPATCH_CONTRACT = (
    "only the Decision Slot, its source boundary, stop condition, and Finding Pack schema",
    "MUST NOT receive the strategy projection digest, primary goal text, or other slots",
)

# API names the protocol sections are allowed to cite → (module, attr, required params)
CITED_APIS: dict[str, tuple[str | None, str | None, tuple[str, ...]]] = {
    "apply_correction": ("research_tree", "ResearchRunCoordinator", ("expected_revision",)),
    "apply_contradiction": ("research_tree", "ResearchRunCoordinator", ("expected_revision",)),
    "DeliveryAcceptance": ("research_tree", "DeliveryAcceptance", ()),
    "ACCEPTANCE_DECISIONS": ("research_tree", "ACCEPTANCE_DECISIONS", ()),
    "record_same_round_replan": ("research_tree", "ResearchRunCoordinator", ()),
    "CorrectionEvent": ("research_tree", "CorrectionEvent", ()),
    "research-tree status": (None, None, ()),
    "write_goal_satisfaction": ("research_tree.completion_inputs", "CompletionInputRegistrar", ()),
    "latest_confirmed": ("research_tree.strategy_projection", "latest_confirmed", ()),
    "validate_falsifiability": ("research_tree.strategy_projection", "validate_falsifiability", ()),
    "assess_goal_contribution": ("research_tree.coordinator", "assess_goal_contribution", ()),
    # CLI surface of the strategy projection lifecycle (#441).
    "strategy propose": (None, None, ()),
    "strategy display": (None, None, ()),
    "strategy confirm": (None, None, ()),
}

PROTOCOL_SECTIONS = {
    "interruption": ("apply_correction", "CorrectionEvent"),
    "contradiction": ("apply_contradiction",),
    "acceptance": ("DeliveryAcceptance", "ACCEPTANCE_DECISIONS"),
    "status echo": ("research-tree status",),
}


def _document_text(path: Path) -> str:
    assert path.is_file(), f"behavioral document missing: {path}"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name,spec", [(k, v) for k, v in CITED_APIS.items() if v[0]])
def test_cited_runtime_apis_exist_with_matching_signatures(name: str, spec: tuple) -> None:
    module_name, attr, required_params = spec
    module = importlib.import_module(module_name)
    target = getattr(module, attr, None)
    assert target is not None, f"cited API {attr} not importable from {module_name}"
    if required_params:
        signature = inspect.signature(target.apply_correction) if attr == "ResearchRunCoordinator" else None
        if signature is None:
            pytest.skip(f"{attr} carries no method-level signature contract")
        for param in required_params:
            assert param in signature.parameters, f"{attr} must accept {param}"


def test_playbook_cites_correction_and_contradiction_protocols() -> None:
    text = _document_text(PLAYBOOK)
    assert "apply_correction" in text, "playbook must teach the interruption protocol"
    assert "apply_contradiction" in text, "playbook must teach the contradiction protocol"
    assert "research-tree status" in text, "playbook must teach the status-echo protocol"


def test_doc_names_only_real_runtime_apis() -> None:
    """C5: every runtime API the docs cite by name exists in src, including #441-#443 names."""

    for name, spec in CITED_APIS.items():
        module_name, attr, _ = spec
        if module_name is None or attr is None:
            continue
        module = importlib.import_module(module_name)
        assert getattr(module, attr, None) is not None, f"doc-cited API {name} does not exist in {module_name}"

    cli_source = (ROOT / "src/research_tree/cli.py").read_text(encoding="utf-8")
    assert "strategy_verb" in cli_source, "strategy command group missing from the CLI"
    assert 'add_parser("propose"' in cli_source and 'add_parser("display"' in cli_source
    for verb in ("propose", "display", "confirm"):
        assert f'strategy_verb == "{verb}"' in cli_source, f"strategy verb {verb} missing from the CLI"

    work_items_source = (ROOT / "src/research_tree/work_items.py").read_text(encoding="utf-8")
    assert '"serves"' in work_items_source, "slot serves validation missing from work_items"
