# Proposal: emit-turn-contract

## Why

Issue #489: the alignment controller is still "pick an action from a table" —
`AlignmentGraph.plan()` ranks nodes deterministically and emits one of three
actions, while the two-layer contract seam (#504: contract terms, trace-type
registry, `verify_traces()`) and the divergence/exit/response-class plumbing
(#496/#491/#490/#497) sit unwired beside it. The 2026-09-03 architecture
ruling (issue body, revising the original direction) is explicit: the original
"extend the engine action vocabulary with clarify/exemplify/mirror/
counterexample" is **rejected** — enumerating behavior as engine actions just
replaces one rigid template with several. Policy selection becomes **contract
emission**: each turn the engine issues structured contract terms
(`target_gap` / `required_traces` / `cost_cap` / `taboos`), the prompt layer
composes the turn freely, the engine verifies the recorded traces, and the
turn record persists terms + traces + user-response class. The 13-candidate
strategy list (echo-guess, example-anchor, constraint-menu, possibility-survey,
teach-then-verify, open-question, mirror, reconnaissance, counterexample,
proportionality-challenge, consequence-warning, ask, await) is prompt-layer
craft guidance, never engine vocabulary.

## What Changes

1. `src/research_tree/alignment_graph.py` — additive contract-emission layer
   on the existing `plan()`/`record()` surface:
   - `plan()` output gains `contract_terms` (the emitted
     `turn_contract.ContractTerms` payload) and, when a user-move signal
     resolved, `user_move_policy` (the #490 verdict). The existing action
     outputs (`ask_one` / `reconnaissance` / `await_human_confirmation` /
     `alignment_incomplete`) are unchanged — the terms ride along.
   - `target_gap` is ranked from the graph: active divergence axes outrank
     (#496), exhausted asks / locally stalled nodes are excluded into
     `taboos` (MAX_ASKS_PER_NODE migrates into the term), and the #490 policy
     (`resolve_user_response_policy`) applies the observed user-move class —
     answer advances past the answered node, correction re-opens the corrected
     node, interruption redirects selection, insight/neutral keep.
   - `required_traces` derive deterministically from the gap shape and the
     emitted `cost_cap` class: proposal-shaped gaps require
     `possibility-survey` (generation cap) or `option-set` (discrimination
     cap); misunderstood-intent gaps (disputed node, or a correction-driven
     reopen) require `guess-statement`. All names come from the frozen
     `turn_contract` registry — no new trace vocabulary.
   - `cost_cap`: open-ended elicitation emits unbounded generation; a handoff
     confirmation emits the one-sentence discrimination cap; the #490 verdict
     adjusts it (correction lowers, never raises an emitted cap; neutral
     keeps the previous cap).
   - The observed signal is read (fail-open, bounded) from the run's persisted
     `alignment_user_move` feed records (#490's declared #489 input surface),
     or passed explicitly via the new `user_signal` / `previous_category`
     parameters.
   - `record()` gains `traces` and `user_move` parameters: when traces are
     supplied, the turn is verified against the last plan's emitted terms via
     `turn_contract.verify_traces()` BEFORE any state mutation — a missing
     required trace fails naming the exact term — and the traces + typed user
     move are persisted in the `response_recorded` event details.
2. `src/research_tree/decision_frame.py` — packaging-only: the `domain`
   import gains the repository's relative-then-bare fallback idiom so the
   module can be shipped beside the packaged single-file controller. No
   behavioral change.
3. `references/alignment-craft.md` (NEW, canonical generation input): the
   13-candidate strategy list as teaching material for the prompt-layer
   composer, WITH the explicit rejected-design note that these strategies
   must never become engine enums or fixed selection ladders (ADR-008).
   Registered in `scripts/build_skill_packages.py` COMMON_FILES and referenced
   from the skill template.
4. `skill-src/SKILL.template.md` — Protocol 1 reframed from the "one more
   question" script to the canonical contract-emission loop (terms → compose →
   verify → persist), pointing the composer at the craft reference.
5. Seam modules shipped to the packages (`turn_contract.py`,
   `decision_frame.py`, `domain.py` via COMMON_FILE_MAP + the Hermes
   executable closure) so the packaged controller emits and verifies the full
   contract loop; `packages/**` regenerated in a generated-only commit.
6. `tests/test_contract_emission.py` (NEW): scenario-named RED tests for the
   emission ranking, trace derivation, cost-cap classes, named-term
   verification failure, and #497 turn-record persistence.

## Capabilities

### New Capabilities

- `contract-emission`: the alignment controller emits structured contract
  terms per turn (target gap ranked with divergence awareness and the
  user-move policy, required traces from the frozen registry, response-cost
  cap, taboos), verifies recorded traces against them at record time, and
  the turn record persists terms + traces + user-response class.

### Modified Capabilities

- None. The existing action vocabulary, `ClarificationPolicy`, the
  alignment-exit policy, and the turn-record schema are unchanged.

## Impact

- `AlignmentGraphStore.plan`/`.record` grow additive keyword parameters and
  additive output keys; `_materialize` (the state-projection hub) is NOT
  modified — the terms ride the existing `last_decision_json` surface.
  Existing alignment suites stay green as regression guardrails.
- 13-candidate strategies exist ONLY in `references/alignment-craft.md` as
  composer teaching material (rejected design: engine enums / fixed ladders).
- No changes to `recursive_search.py`, `independent_review.py`,
  `tree_state.py`, `lifecycle_hook.py`, `search_portfolio.py`,
  `cross_comparison.py`.
