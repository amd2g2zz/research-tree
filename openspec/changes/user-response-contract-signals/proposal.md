# Proposal: user-response-contract-signals

## Why

Issue #490: user intent entering via the prompt is not classified ahead of
strategy selection in a way the engine can act on. The hook persists
sanitized prompt-signal categories (`correction` / `interruption` / `insight`
/ `answer` / `neutral`, `lifecycle_hook.py`) as metadata only;
`ClarificationPolicy.evaluate` reads only hypothesis dispositions; the
controller's `plan()` ranks nodes by impact/ask_count only. The agent cannot
distinguish "user answered my question" from "user redirected the topic"
from "user pushed back on an assumption" — so it re-asks, or proceeds as if
nothing happened.

The 2026-09-03 scope ruling (issue comment, per #501) reframes the decision
surface: what remains decision-shaped is **contract emission and trace
verification**, closer to rule-governed bookkeeping than sequential
optimization. The user-response classification is the load-bearing
prerequisite, now consumed by **contract-term selection** instead of action
selection. The realistic design space is (a) a small policy table over
contract-term selection, (b) at most a bandit for cost-cap tuning, (c) a
full MDP — with (c) expected to be over-engineered. Deliverable: a written
comparison + decision, then implement (a).

## What Changes

1. `src/research_tree/decision_frame.py` (additive): a small **user-response
   policy table** over the five persisted prompt-signal classes.
   `resolve_user_response_policy()` maps an observed signal (category /
   confidence / rule from `classify_prompt_signal`) plus the contract terms
   of the turn just answered onto a typed verdict:
   - `user_move` — the move typed into the `alignment_turn_record` field,
     in the `turn_contract` seam's `RESPONSE_CLASSES` vocabulary
     (answer → `discrimination`; free-text moves → `generation`);
   - `cost_cap` adjustment — a correction after an ask lowers the
     response-production ceiling (first correction → bounded generation;
     repeated corrections → the one-sentence `discrimination` floor);
     an interruption/new material raises it; adjustments never raise an
     emitted cap;
   - `taboos` refresh — an answered node becomes taboo; a corrected node is
     re-opened (taboo removal + `reopen` directive);
   - `target_gap` directive — `advance` (away from the answered node),
     `reopen` (back to the corrected node), `redirect` (demote the
     interrupted node toward the new material), `keep`.
   Rule-governed bookkeeping, not an MDP. `ClarificationPolicy` and the
   controller's action vocabulary are untouched (#489 owns contract
   emission; this change prepares its input basis).
2. `src/research_tree/lifecycle_hook.py` (plumbing): on an alignment-phase
   `UserPromptSubmit`, resolve the policy verdict against the latest
   persisted turn record's `contract_terms` (reuse
   `alignment_turn_record.AlignmentTurnRecordStore` — consumed read-only)
   and feed a routed run signal (`route="alignment_user_move"`) carrying
   the typed user move and the verdict, so the turn-record `user_move`
   field and contract-term selection at the seam are fed. Fail-open like
   every lifecycle observation; the #503 re-entry protocol and #497 refresh
   are untouched.
3. Written strategy-selection comparison (this change's `design.md`): policy
   table vs bandit vs full MDP, with the decision and rationale; bandit and
   MDP recorded as rejected designs.
4. `tests/test_user_response_contract_signals.py` (NEW): the issue's
   scenarios, named after them.

## Capabilities

### New Capabilities

- `user-response-contract-signals`: the persisted user-response class is an
  input to contract-term selection (cost_cap adjustment, taboos refresh,
  target_gap directive) via a small policy table; the typed user move feeds
  the alignment-turn-record field and the run-scoped signal surface;
  the strategy-selection design comparison is written with a decision.

### Modified Capabilities

- None. (`lifecycle-facade` stays fail-open with additive observation; the
  `alignment-turn-record` capability is consumed read-only.)

## Impact

- Additive: one policy table (additive symbols in `decision_frame.py`),
  one hook helper + wiring, one new test file, one openspec change folder.
- GitNexus upstream impact (worktree index, 15,422 nodes / 31,576 edges,
  branch tip `a2a81a0`): `lifecycle_hook.observe` LOW (2 impacted),
  `_observe_prompt_signal` LOW (3 impacted), `_feed_run_signal` LOW (3),
  `_active_run` LOW (6), `_resolve_run_phase` LOW (4) — all reused, only
  `_observe_prompt_signal` modified. Policy-table symbols are new (no
  upstream callers). Risk level: **LOW** overall.
- No changes to `alignment_graph.py` (plan() untouched — #489),
  `turn_contract.py` and `alignment_turn_record.py` (consumed read-only),
  `tree_state.py`, `skill-src/**`, `references/**`.
- `lifecycle_hook.py` is a canonical generation input: `packages/**`
  regenerated via `build_skill_packages.py` in a generated-only commit.
