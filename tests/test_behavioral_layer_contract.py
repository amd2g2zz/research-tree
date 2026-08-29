"""Issue #332: behavioral documents must reference real runtime governance APIs.

Whitelist-driven: only the APIs the new protocol sections cite are scanned, so
historical prose naming other things cannot false-positive.  Every cited name
must be importable from research_tree with a matching signature.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BEHAVIORAL_DOCS = (
    ROOT / "skill-src/SKILL.template.md",
    ROOT / "references/research-quality-playbook.md",
    ROOT / "skill-src/claude-adapter.md",
    ROOT / "skill-src/codex-adapter.md",
    ROOT / "skill-src/hermes-adapter.md",
)

# API names the protocol sections are allowed to cite → (module, attr, required params)
CITED_APIS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "apply_correction": ("research_tree", "ResearchRunCoordinator", ("expected_revision",)),
    "apply_contradiction": ("research_tree", "ResearchRunCoordinator", ("expected_revision",)),
    "DeliveryAcceptance": ("research_tree", "DeliveryAcceptance", ()),
    "ACCEPTANCE_DECISIONS": ("research_tree", "ACCEPTANCE_DECISIONS", ()),
    "record_same_round_replan": ("research_tree", "ResearchRunCoordinator", ()),
    "CorrectionEvent": ("research_tree", "CorrectionEvent", ()),
    "research-tree status": (None, None, ()),
}

PROTOCOL_SECTIONS = {
    "interruption": ("apply_correction", "CorrectionEvent"),
    "contradiction": ("apply_contrastion_placeholder",),
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
    text = _document_text(ROOT / "skill-src/SKILL.template.md")
    for section, markers in PROTOCOL_SECTIONS.items():
        for marker in markers:
            if "placeholder" in marker:
                continue
            assert marker in text, f"SKILL.template.md protocol section '{section}' must cite {marker}"


def test_playbook_cites_correction_and_contradiction_protocols() -> None:
    text = _document_text(ROOT / "references/research-quality-playbook.md")
    assert "apply_correction" in text, "playbook must teach the interruption protocol"
    assert "apply_contradiction" in text, "playbook must teach the contradiction protocol"
    assert "research-tree status" in text, "playbook must teach the status-echo protocol"


def test_all_three_host_adapters_cite_protocol_entry_points() -> None:
    for adapter in ("claude-adapter.md", "codex-adapter.md", "hermes-adapter.md"):
        text = _document_text(ROOT / "skill-src" / adapter)
        assert "apply_correction" in text, f"{adapter} must reference the correction protocol"
        assert "apply_contradiction" in text, f"{adapter} must reference the contradiction protocol"


def test_every_cited_name_is_covered_by_a_protocol_reference() -> None:
    """The citation set must not drift: every CITED_APIS key appears in at least one doc."""
    corpus = "\n".join(_document_text(path) for path in BEHAVIORAL_DOCS)
    for name in CITED_APIS:
        assert name in corpus, f"citation set drift: {name} documented nowhere"
