# Proposal: run-phase-authority

## Why

issue #530 (code-verified): the runtime has no authoritative, machine-readable
answer to "which phase is this run in". `tree_state.py` validates phase
transitions (#492) but no production code ever wrote `payload["phase"]`;
`_resolve_run_phase` falls back to a manifest key nobody writes, so the #503
research re-entry gate never activates; three state vocabularies (alignment
controller, tree status, coordinator workflow) never meet. The phase clock has
no hands.

## What Changes

1. **Owned writers at the owning transitions** (TREE_PHASES vocabulary
   as-is, every write through the gated tree-state graph):
   - alignment handoff confirm (`initialize_research_from_alignment`)
     writes the birth phase `compiled` explicitly;
   - research tree initialization after a confirmed handoff advances
     `compiled -> research` (the coordinator's `handoff_confirmed` wiring
     owns the same edge when the tree exists first);
   - `all_slots_closed` (synthesis complete) writes `validation`;
   - `readiness_passed` (`delivery_pending`) writes `delivery`;
   - `ResearchRunCoordinator.reopen_alignment` owns the reopen-alignment
     re-entry edge (`research -> alignment`).
2. **Authoritative run phase store** (`tree_state.RunPhaseStore`):
   engine-written JSON with a digest over the canonical serialization
   (turn-records state convention) plus an append-only event statement per
   transition, under the run's phase directory.
3. **Hook reads the authority**: `_resolve_run_phase` precedence is explicit
   arg -> phase store (digest-checked) -> env -> manifest; the #503 two-option
   re-entry gate activates for real in `research`.
4. **Phase-aware alignment**: `plan()`/`record()` refuse new alignment asks
   while the run phase is `research` — `plan()` returns a reopen redirect
   without consuming a turn, `record()` raises.
5. **Cache-friendly grounding** (design-constraint ruling): a transition
   emits ONE event statement, announced exactly once through the hook's tail
   channel; the only per-turn surface is a single-line fixed-slot snapshot
   (`phase=... stance=S0 viol=0 topics=0 digest=...`, placeholder defaults);
   never a per-turn state block, never YAML. Full state stays in the store.

## Impact

- src/research_tree/tree_state.py: RunPhaseStore + service.advance_phase
  (additive; the #492 gate is the enforcement path)
- src/research_tree/coordinator.py: additive owner-event wiring +
  reopen_alignment (writer wiring only)
- src/research_tree/alignment_handoff.py: explicit birth phase + store record
- src/research_tree/lifecycle_hook.py: store resolution precedence, snapshot,
  event announcement (fail-open, stdlib-only reader)
- src/research_tree/alignment_graph.py: plan()/record() entry region only;
  `_emit_contract_terms` and `_materialize` untouched
- tests/test_run_phase_authority.py: 13 scenario tests
