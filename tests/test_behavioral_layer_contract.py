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


def test_skill_template_has_all_four_protocol_sections() -> None:
    text = _document_text(SKILL_TEMPLATE)
    for section, markers in PROTOCOL_SECTIONS.items():
        for marker in markers:
            assert marker in text, f"SKILL.template.md protocol section '{section}' must cite {marker}"


def test_playbook_cites_correction_and_contradiction_protocols() -> None:
    text = _document_text(PLAYBOOK)
    assert "apply_correction" in text, "playbook must teach the interruption protocol"
    assert "apply_contradiction" in text, "playbook must teach the contradiction protocol"
    assert "research-tree status" in text, "playbook must teach the status-echo protocol"


def test_all_three_host_adapters_cite_protocol_entry_points() -> None:
    for adapter in HOST_ADAPTERS:
        text = _document_text(ROOT / adapter)
        assert "apply_correction" in text, f"{adapter} must reference the correction protocol"
        assert "apply_contradiction" in text, f"{adapter} must reference the contradiction protocol"


def test_every_cited_name_is_covered_by_a_protocol_reference() -> None:
    """The citation set must not drift: every CITED_APIS key appears in at least one doc."""
    corpus = "\n".join(_document_text(path) for path in BEHAVIORAL_DOCS)
    for name in CITED_APIS:
        assert name in corpus, f"citation set drift: {name} documented nowhere"


def test_skill_template_line_budget_300() -> None:
    """C1: the forced-loaded skill body stays at or under 300 lines."""

    line_count = _document_text(SKILL_TEMPLATE).count("\n")
    assert line_count <= SKILL_LINE_BUDGET, f"SKILL.template.md is {line_count} lines, budget is {SKILL_LINE_BUDGET}"


def test_forced_doc_word_budget_5000() -> None:
    """C2: the whole forced-load doc set stays at or under 5000 words."""

    total_words = sum(len(_document_text(path).split()) for path in BEHAVIORAL_DOCS)
    assert total_words <= FORCED_DOC_WORD_BUDGET, (
        f"forced-load doc set is {total_words} words, budget is {FORCED_DOC_WORD_BUDGET}"
    )


def test_slot_only_dispatch_contract_present() -> None:
    """C3: the slot-only dispatch contract appears verbatim in SKILL + all three adapters."""

    for path in (SKILL_TEMPLATE, *(ROOT / relative for relative in HOST_ADAPTERS)):
        text = _document_text(path)
        for anchor in SLOT_ONLY_DISPATCH_CONTRACT:
            assert anchor in text, f"{path.name} must carry the slot-only dispatch contract anchor verbatim"


def test_runtime_api_mentions_have_availability_gate() -> None:
    """C4: every runtime-API mention carries the checkout availability gate nearby."""

    before_lines, after_lines = 2, 3
    for path in GATE_SCANNED_DOCS:
        lines = _document_text(path).splitlines()
        for index, line in enumerate(lines):
            if not any(token in line for token in RUNTIME_API_TOKENS):
                continue
            context = lines[max(0, index - before_lines) : index + after_lines + 1]
            assert any(AVAILABILITY_GATE in context_line for context_line in context), (
                f"{path.name}:{index + 1} cites {next(t for t in RUNTIME_API_TOKENS if t in line)} "
                f"without the '{AVAILABILITY_GATE}' gate nearby"
            )


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
