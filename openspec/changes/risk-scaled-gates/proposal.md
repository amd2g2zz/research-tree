# Proposal: risk-scaled-gates

## Why

Issue #528: every decision slot runs the same six closure blockers
(coordinator assessment, independent evidence >= 2, validation oracle, source
depth, mechanism artifacts, no frontier remnants) plus the digest-bound
quality review — a trivial P2 task pays the same deep-research toll as a P0
architecture decision. The scaling lever already exists and is unused: slot
`priority` (P0/P1/P2) today influences ranking and `validation_required` but
never the blocker set, and `RecursiveSearchConfig` constants do not scale with
task size.

## What Changes

1. `recursive_search.py` — `evaluate_research_stop` selects the blocker
   subset per slot from the existing `priority` field:
   - P0: full gate set (today's behavior, regression-pinned);
   - P1: validation oracle + evidence floor + coordinator assessment — the
     landscape-depth, mechanism, and frontier-coverage blockers are dropped
     (selection-grade checks), unless the slot opts back in via
     `landscape_gates: true`;
   - P2: validation oracle + evidence floor only.
   The #494/#495 blocker producers stay unconditional: shallow-depth and
   mechanism computations and the mandatory drill-down scheduler run exactly
   as today; the subset selection only decides which produced blockers attach
   to the slot's `closure_blockers`.
2. `recursive_search.py` — `RecursiveSearchConfig` gains
   `profile: small|standard|deep` (default `standard`, which preserves
   today's constants) plus a profile-scaled `minimum_evidence` floor. The
   profile defaults `minimum_evidence`, `max_depth`, and `transition_budget`;
   explicitly passed fields win over the profile, and an unknown profile is
   rejected at construction.
3. ADR (design.md): the irreversible/authority/forgery gates never scale —
   authority fingerprint, phase transitions, digest binding, and evidence
   strict mode ignore slot priority; a test asserts representative members
   still fire on a P2-only tree.

## Capabilities

### New Capabilities

- `risk-scaled-gates`: closure blocker subsets scale by slot priority, the
  recursive search config scales by task profile, and the never-scaling gate
  list is pinned.

### Modified Capabilities

- None (the slot state gains one additive `landscape_gates` flag and the
  config gains two additive fields; version-1 readers remain valid).

## Impact

- src/research_tree/recursive_search.py: `evaluate_research_stop` blocker
  subset selection; `_slot_state` compiles `landscape_gates`;
  `RecursiveSearchConfig` gains `profile`/`minimum_evidence` with profile
  defaults; the evidence-floor helpers take the floor as a parameter
  (defaulting to today's module constant).
- tests/test_risk_scaled_gates.py: scenario-named RED/GREEN tests mapping 1:1
  to the spec scenarios.
- No changes to alignment_graph.py, alignment_turn_record.py,
  turn_contract.py, tree_state.py, lifecycle_hook.py, ledger.py,
  decision_map.py, skill-src/**, references/**, or packages/**.
