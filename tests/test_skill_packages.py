from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_skill_packages.py"


def _skill_dir(package: Path) -> Path:
    return package / "skills" / "research-tree" if "claude-code" in package.parts else package


def test_claude_code_plugin_registration_manifests_are_present() -> None:
    marketplace = ROOT / ".claude-plugin" / "marketplace.json"
    plugin = ROOT / "packages" / "claude-code" / "research-tree" / ".claude-plugin" / "plugin.json"
    skill = ROOT / "packages" / "claude-code" / "research-tree" / "skills" / "research-tree" / "SKILL.md"

    assert marketplace.is_file()
    assert plugin.is_file()
    assert skill.is_file()

    marketplace_data = json.loads(marketplace.read_text(encoding="utf-8"))
    plugin_data = json.loads(plugin.read_text(encoding="utf-8"))
    entry = next(item for item in marketplace_data["plugins"] if item["name"] == "research-tree")
    assert marketplace_data["owner"]["name"]
    assert entry["source"] == "./packages/claude-code/research-tree"
    assert plugin_data["name"] == "research-tree"
    assert entry["version"] == plugin_data["version"] == marketplace_data["version"]


def test_checked_in_host_packages_are_current_and_isolated() -> None:
    completed = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert {item["host"] for item in result["packages"]} == {
        "codex",
        "claude",
        "hermes",
    }
    assert all(item["valid"] for item in result["packages"])
    assert result["marketplace"]["valid"]

    codex = ROOT / "packages" / "codex" / "research-tree"
    claude = ROOT / "packages" / "claude-code" / "research-tree"
    hermes = ROOT / "packages" / "hermes" / "research-tree"
    assert codex.is_dir() and claude.is_dir() and hermes.is_dir()
    skill_bodies = {
        (codex / "SKILL.md").read_bytes(),
        (_skill_dir(claude) / "SKILL.md").read_bytes(),
        (hermes / "SKILL.md").read_bytes(),
    }
    assert len(skill_bodies) == 3


def test_only_hermes_package_contains_hermes_compatibility_material() -> None:
    codex = ROOT / "packages" / "codex" / "research-tree"
    claude = ROOT / "packages" / "claude-code" / "research-tree"
    hermes = ROOT / "packages" / "hermes" / "research-tree"

    for package in (codex, claude):
        skill_root = _skill_dir(package)
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        assert "Hermes runtime adapter" not in skill
        assert not (skill_root / "references" / "hermes-agent-compatibility.md").exists()
        assert not (skill_root / "references" / "hermes-native-orchestration.md").exists()
        assert not (skill_root / "scripts" / "hermes_runtime_hook.py").exists()
        assert not (skill_root / "scripts" / "hermes_skill_adapter.py").exists()
        assert not (skill_root / "scripts" / "hermes_event_adapter.py").exists()

    hermes_skill = (hermes / "SKILL.md").read_text(encoding="utf-8")
    assert "Hermes runtime adapter" in hermes_skill
    assert "Do not assume LangGraph" in hermes_skill
    assert (hermes / "references" / "hermes-agent-compatibility.md").is_file()
    assert (hermes / "references" / "hermes-native-orchestration.md").is_file()
    assert (hermes / "scripts" / "hermes_runtime_hook.py").is_file()
    assert (hermes / "scripts" / "hermes_skill_adapter.py").is_file()
    assert (hermes / "scripts" / "host_event_protocol.py").read_bytes() == (
        ROOT / "scripts" / "host_event_protocol.py"
    ).read_bytes()
    assert (hermes / "scripts" / "hermes_event_adapter.py").read_bytes() == (
        ROOT / "scripts" / "hermes_event_adapter.py"
    ).read_bytes()
    assert (hermes / "scripts" / "hermes_execution_adapter.py").read_bytes() == (
        ROOT / "scripts" / "hermes_execution_adapter.py"
    ).read_bytes()
    assert len(hermes_skill) <= 20_000
    for phase in (
        "hermes-alignment.md",
        "hermes-research-execution.md",
        "hermes-delivery.md",
    ):
        assert (hermes / "references" / phase).is_file()


def test_only_claude_package_contains_claude_compatibility_material() -> None:
    codex = ROOT / "packages" / "codex" / "research-tree"
    claude = ROOT / "packages" / "claude-code" / "research-tree"
    hermes = ROOT / "packages" / "hermes" / "research-tree"

    for package in (codex, hermes):
        skill = (package / "SKILL.md").read_text(encoding="utf-8")
        assert "Claude Code runtime adapter" not in skill
        assert not (package / "references" / "claude-code-compatibility.md").exists()
        assert not (package / "references" / "claude-native-orchestration.md").exists()
        if package == hermes:
            assert not (package / "scripts" / "native_execution_adapter.py").exists()

    claude_skill_root = _skill_dir(claude)
    claude_skill = (claude_skill_root / "SKILL.md").read_text(encoding="utf-8")
    assert "Claude Code runtime adapter" in claude_skill
    assert (claude_skill_root / "references" / "claude-code-compatibility.md").is_file()
    assert (claude_skill_root / "references" / "claude-native-orchestration.md").is_file()
    assert (claude_skill_root / "scripts" / "native_execution_adapter.py").is_file()


def test_only_codex_package_contains_codex_compatibility_material() -> None:
    codex = ROOT / "packages" / "codex" / "research-tree"
    claude = ROOT / "packages" / "claude-code" / "research-tree"
    hermes = ROOT / "packages" / "hermes" / "research-tree"

    for package in (claude, hermes):
        skill_root = _skill_dir(package)
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        assert "Codex CLI runtime adapter" not in skill
        assert not (skill_root / "references" / "codex-cli-compatibility.md").exists()
        assert not (skill_root / "references" / "codex-native-orchestration.md").exists()

    codex_skill = (codex / "SKILL.md").read_text(encoding="utf-8")
    assert "Codex CLI runtime adapter" in codex_skill
    codex_ref = codex / "references" / "codex-cli-compatibility.md"
    assert codex_ref.is_file()
    assert (codex / "references" / "codex-native-orchestration.md").is_file()
    assert (codex / "scripts" / "native_execution_adapter.py").is_file()
    assert "request_user_input" in codex_ref.read_text(encoding="utf-8")


def test_codex_and_claude_expose_distinct_native_orchestration() -> None:
    codex = (
        ROOT
        / "packages"
        / "codex"
        / "research-tree"
        / "references"
        / "codex-native-orchestration.md"
    ).read_text(encoding="utf-8")
    claude = (
        _skill_dir(ROOT / "packages" / "claude-code" / "research-tree")
        / "references"
        / "claude-native-orchestration.md"
    ).read_text(encoding="utf-8")

    for marker in ("AGENTS.md", "update_plan", "collaboration subagents", "fork"):
        assert marker in codex
    for marker in ("CLAUDE.md", "background agent", "agent team", "auto-memory"):
        assert marker in claude
    assert "CLAUDE.md" not in codex
    assert "update_plan" not in claude

    for package_name in ("codex", "claude-code"):
        adapter = (
            _skill_dir(ROOT / "packages" / package_name / "research-tree")
            / "scripts"
            / "native_execution_adapter.py"
        ).read_text(encoding="utf-8")
        assert '"observations"' in adapter
        assert '"option_effects"' in adapter
        assert '"attempt_id"' in adapter
        assert 'task["status"] = "submitted"' in adapter


def test_host_question_references_name_only_their_native_capability() -> None:
    codex = ROOT / "packages" / "codex" / "research-tree"
    claude = ROOT / "packages" / "claude-code" / "research-tree"
    hermes = ROOT / "packages" / "hermes" / "research-tree"

    assert "AskUserQuestion" in (
        _skill_dir(claude) / "references" / "claude-code-compatibility.md"
    ).read_text(encoding="utf-8")
    assert "clarify" in (
        hermes / "references" / "hermes-agent-compatibility.md"
    ).read_text(encoding="utf-8")
    assert "Do not assume Claude's `AskUserQuestion`" in (
        codex / "references" / "codex-cli-compatibility.md"
    ).read_text(encoding="utf-8")


def test_feedback_reopens_research_and_requires_evidence_progress() -> None:
    template = (ROOT / "skill-src" / "SKILL.template.md").read_text(
        encoding="utf-8"
    )
    claude = (
        _skill_dir(ROOT / "packages" / "claude-code" / "research-tree") / "SKILL.md"
    ).read_text(encoding="utf-8")

    for body in (template, claude):
        assert '"I don\'t know"' in body
        assert "evidence-bearing" in body
        assert "Never end a requested investigation" in body
        assert "A worker may report a blocker only after" in body
        assert "Alignment Checkpoint" in body
        assert '"okay", or "continue" is not alignment evidence' in body

    assert "Do not create or display a Research Tree before this boundary" in claude


def test_all_host_packages_expose_opt_in_debug_tracing() -> None:
    packages = (
        ROOT / "packages" / "codex" / "research-tree",
        ROOT / "packages" / "claude-code" / "research-tree",
        ROOT / "packages" / "hermes" / "research-tree",
    )

    for package in packages:
        skill_root = _skill_dir(package)
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        assert "research-tree-debug" in skill
        assert (skill_root / "references" / "debug-tracing.md").is_file()


def test_host_adapters_direct_the_native_question_capability() -> None:
    codex = (ROOT / "packages" / "codex" / "research-tree" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    claude = (
        _skill_dir(ROOT / "packages" / "claude-code" / "research-tree") / "SKILL.md"
    ).read_text(encoding="utf-8")
    hermes = (ROOT / "packages" / "hermes" / "research-tree" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "request_user_input" in codex
    assert "AskUserQuestion" in claude
    assert "native `clarify`" in hermes


def test_long_horizon_policy_is_cost_tolerant_and_resumable() -> None:
    template = (ROOT / "skill-src" / "SKILL.template.md").read_text(
        encoding="utf-8"
    )
    playbook = (ROOT / "references" / "research-quality-playbook.md").read_text(
        encoding="utf-8"
    )
    assert "cost-tolerant" in template
    assert "monetary cost is non-gating" in playbook
    for body in (template, playbook):
        assert "resumable" in body
        assert "Autonomy envelope" in body

    for host in ("codex", "claude", "hermes"):
        skill = (
            _skill_dir(
                ROOT / "packages" / ("claude-code" if host == "claude" else host)
                / "research-tree"
            )
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "cost-tolerant" in skill
        assert "Autonomy envelope after strategy handoff" in skill


def test_intent_understanding_remains_live_during_research() -> None:
    product = (ROOT / "PRODUCT.md").read_text(encoding="utf-8")
    template = (ROOT / "skill-src" / "SKILL.template.md").read_text(
        encoding="utf-8"
    )
    playbook = (ROOT / "references" / "research-quality-playbook.md").read_text(
        encoding="utf-8"
    )

    assert "Intent understanding is a continuous product loop" in product
    assert "Intent understanding remains active throughout the round" in template
    assert "Intent understanding is never a one-time pre-research gate" in playbook
    for host in ("codex", "claude", "hermes"):
        package = "claude-code" if host == "claude" else host
        skill = (
            _skill_dir(ROOT / "packages" / package / "research-tree") / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "Intent understanding remains active throughout the round" in skill


def test_strategy_handoff_requires_coevolutionary_debate() -> None:
    product = (ROOT / "PRODUCT.md").read_text(encoding="utf-8")
    template = (ROOT / "skill-src" / "SKILL.template.md").read_text(
        encoding="utf-8"
    )
    playbook = (ROOT / "references" / "research-quality-playbook.md").read_text(
        encoding="utf-8"
    )

    assert "decision equilibrium" in product
    assert "Co-evolve cognition before strategy handoff" in template
    assert "co-evolve their models" in playbook
    assert "not at user acquiescence" in playbook


def test_early_communication_is_human_centered_and_confusion_driven() -> None:
    product = (ROOT / "PRODUCT.md").read_text(encoding="utf-8")
    template = (ROOT / "skill-src" / "SKILL.template.md").read_text(
        encoding="utf-8"
    )
    playbook = (ROOT / "references" / "research-quality-playbook.md").read_text(
        encoding="utf-8"
    )

    assert "Human-centered communication" in product
    assert "question-only" in template
    assert "teaching reconnaissance cycle" in template
    assert "question-only turn" in playbook
    assert "smallest useful web, repository, or supplied-material sources" in playbook


def test_vague_briefs_trigger_short_guided_communication() -> None:
    product = (ROOT / "PRODUCT.md").read_text(encoding="utf-8")
    template = (ROOT / "skill-src" / "SKILL.template.md").read_text(
        encoding="utf-8"
    )
    playbook = (ROOT / "references" / "research-quality-playbook.md").read_text(
        encoding="utf-8"
    )

    for body in (product, template, playbook):
        assert "1000" in body
        assert "vague" in body
        assert "short" in body
    assert "progress -> new" in playbook


def test_intent_elicitation_is_open_ended_and_context_first() -> None:
    product = (ROOT / "PRODUCT.md").read_text(encoding="utf-8")
    template = (ROOT / "skill-src" / "SKILL.template.md").read_text(
        encoding="utf-8"
    )
    playbook = (ROOT / "references" / "research-quality-playbook.md").read_text(
        encoding="utf-8"
    )

    for body in (product, template, playbook):
        assert "open-ended" in body
        assert "current" in body and "context" in body
        assert "in their own words" in body
    assert "never make a menu the default" in product
    assert "Do not use multiple-choice menus as the default" in template
    assert "does not inherit" in playbook


def test_alignment_turns_are_traceable_without_transcripts() -> None:
    brief = (ROOT / "assets" / "brief-template.md").read_text(encoding="utf-8")
    human_brief = (ROOT / "assets" / "human-brief-template.md").read_text(
        encoding="utf-8"
    )
    playbook = (ROOT / "references" / "research-quality-playbook.md").read_text(
        encoding="utf-8"
    )

    assert "Alignment Turn Ledger" in brief
    assert "Human/agent belief delta" in brief
    assert "Alignment Trace" in human_brief
    assert "not a transcript" in playbook


def test_each_package_uses_only_its_hosts_metadata_format() -> None:
    codex = ROOT / "packages" / "codex" / "research-tree"
    claude = ROOT / "packages" / "claude-code" / "research-tree"
    hermes = ROOT / "packages" / "hermes" / "research-tree"

    codex_skill = (codex / "SKILL.md").read_text(encoding="utf-8")
    claude_skill = (_skill_dir(claude) / "SKILL.md").read_text(encoding="utf-8")
    hermes_skill = (hermes / "SKILL.md").read_text(encoding="utf-8")

    assert (codex / "agents" / "openai.yaml").is_file()
    assert "$research-tree" in (
        codex / "agents" / "openai.yaml"
    ).read_text(encoding="utf-8")
    assert "argument-hint:" not in codex_skill
    assert "argument-hint:" in claude_skill
    assert "disable-model-invocation: false" in claude_skill
    assert "user-invocable: true" in claude_skill
    assert (claude / ".claude-plugin" / "plugin.json").is_file()
    assert (_skill_dir(claude) / "SKILL.md").is_file()
    assert not (claude / "SKILL.md").exists()
    assert not (claude / "agents" / "openai.yaml").exists()
    assert not (codex / ".claude-plugin").exists()
    assert not (hermes / ".claude-plugin").exists()
    assert "argument-hint:" not in hermes_skill
    assert not (hermes / "agents" / "openai.yaml").exists()


def test_packages_expose_runtime_depth_and_insight_contract() -> None:
    for package_name in ("codex", "claude-code", "hermes"):
        skill = (
            _skill_dir(ROOT / "packages" / package_name / "research-tree") / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "plan-to-execute" in skill
        assert "Insight Digest" in skill
        assert "Do not hand a broad track to" in skill
        assert "workers re-delegate" in skill
