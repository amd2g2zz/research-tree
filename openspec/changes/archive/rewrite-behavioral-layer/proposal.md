# Rewrite Behavioral Layer

## Why

Every research session force-loads ~14.5k words (~19k tokens) of behavior docs
(SKILL.template 5,462 words / 703 lines, playbook 4,180 words, orchestration
refs, adapters). SKILL.template.md alone carried ~40 product rules across 703
lines — a spec document, not behavior; the measured consequence is
rule-skipping. The installed skill package contains no Python runtime, yet the
"Runtime governance protocols" section mandated `apply_correction` /
`apply_contradiction` / `research-tree status` with no availability check, so
in a host session without the checkout the governance layer trained models to
ignore the governance layer. Dispatch scoping was unstated: nothing forbade
leaking the confirmed projection digest or primary-goal text into worker
prompts, and the G-series goal wiring (#441-#443) assumes slot-only worker
visibility.

## What Changes

- SKILL.template.md rewritten to 257 lines / 2,018 words: the activation state
  machine (`verified_load -> bounded_reconnaissance -> alignment_question ->
  explicit_handoff -> autonomous_dispatch`), the goal model (confirmed
  StrategyProjection = primary goal; slots = secondary with required `serves`
  links), and the alignment loop essentials, with the ~40 product rules folded
  into six named protocol sections (elicitation/alignment loop, claims and
  feasibility and cost, strategy lifecycle and goal wiring, assistance and
  correction, dispatch and the slot-only contract, delivery and completion
  gates).
- Strategy lifecycle documented as shipped by #441: `research-tree strategy
  propose` (draft), `research-tree strategy display` (falsifiability review
  via `validate_falsifiability` before display), `research-tree strategy
  confirm` (digest-quoting confirmation; a bare "yes" is a rubber stamp and
  changes nothing). Downstream basis is `latest_confirmed`, fail-closed.
- Slot-only dispatch contract added verbatim to SKILL.template.md and all
  three host adapters: worker prompt carries only the Decision Slot, its
  source boundary, stop condition, and Finding Pack schema; a worker MUST NOT
  receive the strategy projection digest, primary goal text, or other slots.
- Every runtime-API mention (`apply_correction`, `apply_contradiction`,
  `research-tree status`) carries the checkout availability gate
  ("when the checkout runtime is available … otherwise persist the equivalent
  intent in workspace artifacts") in the adjacent context, including the
  hermes host template that renders Hermes' SKILL.md.
- `references/research-quality-playbook.md` rewritten as a ~560-word quality
  manual (alpha1's byte-identical 4,180-word copy retired) complementary to
  the SKILL protocols: alignment quality, evidence quality, cost and
  autonomy, goal quality, and the runtime protocol binding.
- hermes-SKILL.template.md rewritten to mirror the new body so the Hermes host
  loads the same protocol set (it renders Hermes' SKILL.md directly).
- `tests/test_behavioral_layer_contract.py` extended with the named contracts:
  `test_skill_template_line_budget_300`, `test_forced_doc_word_budget_5000`,
  `test_slot_only_dispatch_contract_present`,
  `test_runtime_api_mentions_have_availability_gate`, and
  `test_doc_names_only_real_runtime_apis` covering the #441-#443 surface
  (`strategy propose/display/confirm`, `write_goal_satisfaction`,
  `latest_confirmed`, `assess_goal_contribution`, `validate_falsifiability`).
- All host packages regenerated from skill-src (generated-only commit).

## Impact

- specs/behavioral-layer/spec.md (new capability spec with the C1-C5 deltas)
