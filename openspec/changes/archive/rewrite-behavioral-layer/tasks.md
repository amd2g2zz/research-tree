# Rewrite Behavioral Layer — Tasks

## 1. Contract tests (RED)

- [x] 1.1 Extend `tests/test_behavioral_layer_contract.py` with the five named
      contracts (C1 line budget, C2 word budget, C3 anchors, C4 gates, C5 doc
      names resolve to real runtime APIs) and extend the citation whitelist
      with the #441-#443 surface.
- [x] 1.2 Confirm RED: line budget 703>300, word budget 11,625>5,000, anchors
      absent, gates absent, citation drift on the new names.

## 2. SKILL.template.md rewrite (GREEN)

- [x] 2.1 Keep the three-block skeleton (activation state machine, alignment
      loop essentials, delivery gates) and fold the ~40 product rules into six
      protocol sections.
- [x] 2.2 Document the #441-#443 goal wiring: strategy propose/display/confirm
      lifecycle, `serves` requirement, `assess_goal_contribution` verdict
      handling, per-oracle `write_goal_satisfaction` completion gate, R3
      assistance-and-correction protocol with the waiver path.
- [x] 2.3 Land the two slot-only anchors verbatim and gate every
      `apply_correction` / `apply_contradiction` / `research-tree status`
      mention.

## 3. Adapters and playbook

- [x] 3.1 Rewrite claude/codex/hermes adapters as thin layers: host conventions
      preserved, protocol semantics delegated to the SKILL body, anchors and
      gated entry points included.
- [x] 3.2 Rewrite hermes-SKILL.template.md to mirror the new body (it renders
      the Hermes host's SKILL.md).
- [x] 3.3 Rewrite `references/research-quality-playbook.md` as a complementary
      quality manual (no longer a duplicate of the alpha1 rules).

## 4. Packages

- [x] 4.1 Regenerate packages/** via build_skill_packages.py (generated-only
      commit).

## 5. Gates

- [x] 5.1 Behavioral contract suite green; full suite green except the known
      docker-environment test; ruff clean; package check passes; docs/layout
      checkers pass; openspec strict validation passes.
