# Tasks: emit-turn-contract

## 1. SDD

- [x] 1.1 Proposal, design (canonical-loop wiring + `impact_scope` +
  `rejected_designs`), capability spec delta from the issue scenarios.
- [x] 1.2 GitNexus index rebuild in the worktree (branch tip `4fbe239`) +
  upstream impact per touched symbol (`_materialize` MEDIUM and untouched).

## 2. Emission (RED first)

- [x] 2.1 RED: `plan()` emits terms with `target_gap` ranked from the graph
  (active axis outranks, exhausted/taboos excluded) with the action keys
  unchanged (additive surface).
- [x] 2.2 RED: the #490 policy applies the observed user move (interruption
  redirects, answer advances past the answered node, correction re-opens the
  corrected node as `guess-statement`-shaped target), from the fed
  `alignment_user_move` record or an explicit signal.
- [x] 2.3 RED: `required_traces` derive from gap shape and cap class
  (`possibility-survey` / `option-set` / `guess-statement`); non-asking
  decisions emit an empty gate.
- [x] 2.4 RED: `cost_cap` reflects the user-move class (correction lowers,
  never raises; repeated correction floors; neutral keeps; interruption
  raises).

## 3. Verification + persistence (RED first)

- [x] 3.1 RED: a recorded turn missing a required trace fails naming the
  exact term before any state mutation; legacy `record()` without traces
  still succeeds.
- [x] 3.2 RED: a recorded turn carrying the traces passes, reports the
  satisfied terms, and persists terms + traces + user move in the #497 turn
  record.

## 4. Implementation (GREEN)

- [x] 4.1 `alignment_graph.py`: additive emission helpers + `plan`/`record`
  wiring; `_materialize` untouched.
- [x] 4.2 GREEN: sections 2-3 pass; existing alignment suites stay green.

## 5. Prompt-layer craft

- [x] 5.1 `references/alignment-craft.md` (NEW): the 13-candidate strategy
  palette with the rejected-design note; registered in COMMON_FILES.
- [x] 5.2 `skill-src/SKILL.template.md`: Protocol 1 reframed to the
  contract-emission loop within the forced-load word budget.
- [x] 5.3 Seam modules shipped (COMMON_FILE_MAP + Hermes closure;
  decision_frame import fallback); `packages/**` regenerated in a
  generated-only commit.

## 6. Gates and evidence

- [x] 6.1 Full local gates green: pytest, ruff check + format check,
  `check_delivery_workflow.py validate`, `check_openspec_governance.py`,
  `build_skill_packages.py --check`.
- [x] 6.2 GitNexus `detect-changes` reconciled with this `impact_scope` via
  `check_impact_scope.py`; reports stored in `evidence/`.
