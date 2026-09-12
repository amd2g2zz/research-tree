# Tasks: user-response-contract-signals

## 1. SDD

- [x] 1.1 Proposal, design (strategy-selection comparison with decision +
  `impact_scope` + `rejected_designs`), capability spec delta from the
  issue's scenarios.
- [x] 1.2 GitNexus index rebuild in the worktree (branch tip `a2a81a0`) +
  upstream impact per touched symbol (all LOW — see `design.md`).

## 2. Policy table (RED first)

- [x] 2.1 RED: correction after an ask lowers the next cost cap and
  re-opens the corrected node (taboo removal, `reopen` directive, gap
  target = corrected node, move typed `generation`).
- [x] 2.2 RED: repeated correction (previous category supplied) drops the
  ceiling to the one-sentence `discrimination` floor.
- [x] 2.3 RED: answer marks the asked node answered (taboo addition) and
  advances target-gap selection away from it; move typed `discrimination`.
- [x] 2.4 RED: interruption redirects target-gap selection toward the new
  material (interrupted node demoted, not tabooed) and raises the cap.
- [x] 2.5 RED: neutral turns leave contract terms unchanged (no spurious
  drift); a correction carrying `+continuation` semantics also leaves terms
  unchanged; adjustments never raise an emitted cap.

## 3. Hook plumbing (RED first)

- [x] 3.1 RED: alignment-phase prompt on a run whose latest turn record
  carries contract terms produces a `user_move_policy` verdict on the hook
  result/record and feeds an `alignment_user_move` run-scoped record with
  the typed move and verdict.
- [x] 3.2 RED: outside the alignment phase (research, no run) no verdict is
  produced and no feed happens; #503 re-entry and #497 refresh unchanged;
  the hook stays fail-open.

## 4. Implementation (GREEN)

- [x] 4.1 `src/research_tree/decision_frame.py`: additive policy table
  (`USER_SIGNAL_CATEGORIES`, `resolve_user_response_policy`,
  `UserMoveVerdict`) reusing `turn_contract` vocabulary; existing symbols
  untouched.
- [x] 4.2 `src/research_tree/lifecycle_hook.py`: defensive imports, the
  fail-open `_observe_user_move_policy` helper, wiring in
  `_observe_prompt_signal` (verdict on record/result +
  `alignment_user_move` feed).
- [x] 4.3 GREEN: sections 2-3 pass; existing suites (prompt-signal,
  turn-record, re-entry, decision-frame) stay green.

## 5. Comparison deliverable

- [x] 5.1 RED: the design document exists, compares policy table vs bandit
  vs full MDP, names the decision (policy table), and records the rejected
  alternatives.
- [x] 5.2 The comparison lives in this change's `design.md` ("Strategy-
  selection design comparison" + "Rejected Designs").

## 6. Gates and evidence

- [x] 6.1 Full local gates green: pytest (no new failures), ruff check +
  format check, `check_delivery_workflow.py validate`,
  `check_openspec_governance.py`, `build_skill_packages.py --check`.
- [x] 6.2 `packages/**` regenerated via `build_skill_packages.py` in a
  generated-only commit (lifecycle_hook is a canonical generation input).
- [x] 6.3 GitNexus `detect-changes` reconciled with this `impact_scope`
  via `check_impact_scope.py`; reports stored in `evidence/`.
