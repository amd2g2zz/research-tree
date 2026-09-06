# Tasks: emit-turn-contract

## 1. SDD

- [ ] 1.1 Proposal, design (canonical-loop wiring + `impact_scope` +
  `rejected_designs`), capability spec delta from the issue scenarios.
- [ ] 1.2 GitNexus index rebuild in the worktree (branch tip `4fbe239`) +
  upstream impact per touched symbol (`_materialize` MEDIUM and untouched;
  see `design.md`).

## 2. Emission (RED first)

- [ ] 2.1 RED: a `plan()` call emits contract terms whose `target_gap` is
  ranked from the graph — active divergence axis outranks, exhausted/taboos
  excluded — and carries the action, gap id, and question keys unchanged
  (additive surface).
- [ ] 2.2 RED: the #490 policy applies the observed user move — an
  interruption redirects target-gap selection to the next candidate; an
  answer advances past the answered node; a correction re-opens the corrected
  node as `guess-statement`-shaped target.
- [ ] 2.3 RED: `required_traces` derive from gap shape and cost-cap class —
  proposal-shaped gaps require `possibility-survey` (generation) or
  `option-set` (discrimination); a misunderstood-intent gap requires
  `guess-statement`.
- [ ] 2.4 RED: `cost_cap` reflects the user-move class — correction lowers
  (never raising an emitted cap; repeated correction hits the floor), neutral
  keeps the previous cap.

## 3. Verification + persistence (RED first)

- [ ] 3.1 RED: a recorded turn missing a required trace fails verification
  naming the exact term (via `turn_contract.verify_traces()`), before any
  state mutation; a legacy `record()` call without traces still succeeds.
- [ ] 3.2 RED: a recorded turn carrying the traces passes, reports the
  satisfied terms, and persists terms + traces + user-move in the #497 turn
  record (`AlignmentTurnRecordStore`).

## 4. Implementation (GREEN)

- [ ] 4.1 `src/research_tree/alignment_graph.py`: additive emission helpers
  (`_emit_contract_terms`, `_emission_taboos`, trace derivation, base cap,
  feed reader) + `plan(user_signal=…, previous_category=…)` /
  `record(traces=…, user_move=…)` wiring; `_materialize` untouched.
- [ ] 4.2 GREEN: sections 2-3 pass; `test_alignment_controller`,
  `test_alignment_graph_record`, `test_alignment_exit_policy`,
  `test_alignment_divergence`, `test_user_response_contract_signals`,
  `test_turn_contract`, `test_alignment_turn_record` stay green.

## 5. Prompt-layer craft

- [ ] 5.1 `references/alignment-craft.md` (NEW): the 13-candidate strategy
  list as composer teaching material with the explicit rejected-design note
  (never engine enums or fixed selection ladders); registered in
  `scripts/build_skill_packages.py` COMMON_FILES.
- [ ] 5.2 `skill-src/SKILL.template.md`: Protocol 1 reframed to the
  contract-emission loop (terms → compose → verify → persist); reading list
  points at the craft reference.
- [ ] 5.3 Seam modules shipped (`turn_contract.py`, `decision_frame.py`,
  `domain.py` in COMMON_FILE_MAP + Hermes closure; decision_frame gains the
  relative-then-bare import fallback); `packages/**` regenerated in a
  generated-only commit.

## 6. Gates and evidence

- [ ] 6.1 Full local gates green: pytest, ruff check + format check,
  `check_delivery_workflow.py validate`, `check_openspec_governance.py`,
  `build_skill_packages.py --check`.
- [ ] 6.2 GitNexus `detect-changes` reconciled with this `impact_scope` via
  `check_impact_scope.py`; reports stored in `evidence/`.
