# Proposal: wire-behavioral-protocols

## Why

issue #332: alpha2's governance machine (apply_correction, apply_contradiction,
5-outcome acceptance, status) has zero behavioral-layer callers — SKILL/playbook
/adapters cite none of it, so interruptions fall back to alpha1-era prose.

## What Changes

1. SKILL.template.md gains "Runtime governance protocols" (4 rules:
   interruption→CorrectionEvent/apply_correction + record_same_round_replan
   light path; contradiction→apply_contradiction stale-marking; acceptance→
   ACCEPTANCE_DECISIONS via DeliveryAcceptance; status echo from
   research-tree status; alignment claims typed).
2. Playbook gains "Runtime governance protocol binding" + rewrites the
   whole-graph-handoff row to branch-and-correct semantics.
3. Three adapters gain governance entry-point bullets.
4. tests/test_behavioral_layer_contract.py (10 tests): whitelist-driven
   citation contract — every cited API importable+signature-checked; every
   protocol section present in SKILL/playbook/adapters; no citation-set drift.
5. `ACCEPTANCE_DECISIONS` exported from package root (docs cite it; contract
   requires importability).

## Impact

- skill-src/*.md, references/research-quality-playbook.md, packages/ (rebuilt),
  src/research_tree/__init__.py (one export), tests/test_behavioral_layer_contract.py.
- No runtime semantics change; export-only addition.
