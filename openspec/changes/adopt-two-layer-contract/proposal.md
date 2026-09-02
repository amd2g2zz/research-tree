# Proposal: adopt-two-layer-contract

## Why

Issue #501 (root-cause architecture ruling, 2026-09-03): several open issues
(#489, #498, #499) risk being implemented as engine-side behavior
enumeration — new action-vocabulary entries, new checklist gates for
open-ended qualities like "teaching" or "expert judgment". The maintainer
ruled 通过词表肯定是无法覆盖的，很多需要通过 prompt 来解: open-ended behaviors
(how to teach a novice, how to survey a possibility space, how to construct a
counterexample) are unbounded natural-language generation and belong to the
prompt layer. The engine must gate only on *structural traces* — artifacts
whose existence and schema it can verify — and never enumerate *what* the
agent may say. Six open issues (#489, #490, #493, #498, #499, #500) already
cite this contract as their direction revision, so the contract needs a
ratified ADR, a verifiable seam module, and a mechanical audit helper before
those issues implement against it.

## What Changes

1. `docs/adr/ADR-008-two-layer-contract.md`: the architecture ruling. Engine
   layer gates ONLY on structural traces (state persistence #497, phase
   discipline #492, turn-shape #493, composition checks #499, structural-trace
   gates); prompt layer carries all open-ended behavior strategy. Includes the
   design test ("if it adds an enum entry for something the model should say,
   it violates the contract; if it adds a trace type the engine can verify, it
   conforms"), the canonical contract-emission loop (emit terms → prompt layer
   composes freely → engine verifies traces → persist turn-record), and the
   rejected design (behavior enumeration in engine vocabulary: 13-action
   menus, fixed selection ladders).
2. `src/research_tree/turn_contract.py` (NEW, seam only): contract-terms
   schema (`target_gap` alignment-graph node reference, `required_traces`
   finite set, `cost_cap` user-response-production ceiling with
   discrimination-vs-generation kinds, `taboos` already-answered nodes / spent
   asks), a frozen append-only trace-type registry seeded with the six initial
   types (option-set, concept-card, guess-statement, counterargument,
   possibility-survey, evidence-delta; duplicate registration rejected), and
   the `verify_traces()` primitive that fails naming the exact missing term —
   presence and schema checks only, never content quality. NOT wired into
   `alignment_graph.py`, `decision_frame.py`, or `lifecycle_hook.py` (that
   rewiring is #489/#490's; this PR delivers the seam).
3. `scripts/check_impact_scope.py` (NEW): deterministic, offline quality-gate
   helper that reconciles a GitNexus `detect-changes` JSON report (or, when
   the CLI cannot emit machine-readable output non-interactively, a
   `git diff --name-only <base>...HEAD` file-level cross-reference) against a
   declared `impact_scope` sidecar and FAILS when changed symbols/files fall
   outside the declared scope.
4. `.github/PULL_REQUEST_TEMPLATE.md` (NEW): mandatory checklist —
   `Closes #N`, OpenSpec change id, GitNexus impact report (symbols / blast
   radius / risk; HIGH/CRITICAL flagged), detect-changes consistency with
   impact_scope, scenario→test mapping table, local gate results.
5. `.gitignore`: one line `plan.md` under "# Local configuration" (local
   planning file stays untracked).
6. `tests/test_turn_contract.py` and `tests/test_check_impact_scope.py`
   (NEW): schema-validation RED tests, missing-trace naming, duplicate
   trace-type registration, registry contents, and pass/fail audit cases
   against tmp dirs.

## Capabilities

### New Capabilities

- `turn-contract`: the two-layer contract seam — contract-terms schema,
  frozen append-only trace-type registry, and the `verify_traces()`
  presence/schema gate primitive.

### Modified Capabilities

- None.

## Impact

- Entirely additive: 2 new source/test-bearing files, 2 new docs/config
  files, 1 new openspec change folder, 1 `.gitignore` line. Zero existing
  symbols modified (GitNexus impact on the seam's new symbols: no upstream
  callers — it is deliberately uncalled until #489/#490 wire it;
  detect-changes reconciliation recorded in `evidence/` before push).
- No changes to `alignment_graph.py`, `decision_frame.py`,
  `lifecycle_hook.py`, `tree_state.py`, `search_portfolio.py`,
  `cross_comparison.py`, `recursive_search.py`, `skill-src/**`,
  `references/**`, or `packages/**`.
