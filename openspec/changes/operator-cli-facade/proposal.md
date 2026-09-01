# Proposal: operator-cli-facade

## Why

The senior-user-ux-v2 acceptance record (#468, #292 gate 4) isolated the
prepared-to-initialized gap: `coordinator.initialize` requires the compiled
alignment handoff to appear in the blueprint target's `parent_refs`, but
`CanonicalBlueprintTargetCompiler.compile` only writes the (brief, model)
parents and no CLI verb performs the bind — the run-state can never be
created from an operator surface, so the strategy gates and every downstream
deliverable stay unreachable. The same record found the packaged alignment
controller crashing on `record` (`speech_acts` never ships with the package
and the relative import cannot resolve under direct-script execution) and the
Human Brief operating model (roles/SLA/concurrency/blockers/fallback) locked
inside `delivery.py` with zero CLI exposure.

## What Changes

- `CanonicalBlueprintTargetCompiler.compile` accepts an optional
  `alignment_handoff` parent: when provided, the compiled blueprint target is
  lineage-bound to that exact stored `alignment-handoff` revision in the same
  run, and `coordinator.initialize` accepts it unchanged. Omitted (default)
  behavior is byte-identical to today.
- New operator CLI verb `research-tree initialize`: resolves (or compiles, via
  the existing `initialize_research_from_alignment`) the run's alignment
  handoff, optionally compiles the intent model + working brief from one
  operator document, compiles the blueprint target with the handoff bind from
  one blueprint document, and drives `coordinator.initialize` — bridging
  `prepared` to `initialized` entirely through the CLI.
- `research-tree strategy propose` accepts an optional
  `--alignment-verification` document (registered through the existing
  `CompletionInputRegistrar`) so the #462 display gate is satisfiable from an
  operator surface, and accepts a base projection document (the product still
  computes the display payload, digest, and content hash).
- New operator CLI verb `research-tree operating-model`: renders the Human
  Brief operating model (roles, SLA, concurrency limits, blockers, outcome
  layers, adoption metrics, fallback plan) from `delivery.py`'s compiler as
  markdown — no Python internals required.
- Packaged `record` fix: `speech_acts.py` ships beside the packaged
  alignment controller, and the two lazy `speech_acts` imports in
  `alignment_graph.py` fall back to the sibling module when the package
  context is absent, so `scripts/alignment_controller.py record` reaches
  rc 0 in the shipped layout.

## Impact

- `src/research_tree/decision_map.py`, `src/research_tree/cli.py`,
  `src/research_tree/alignment_graph.py`, `scripts/build_skill_packages.py`,
  and the regenerated host packages (generated-only commit); new tests in
  `tests/test_cli_operator_facade.py`; operator journey log in
  `docs/evaluation/research/v2-followup-cli-journey.md`.
- Existing callers of `compile` and `initialize` are unaffected: the new
  compiler parameter defaults to the current parent_refs, and
  `coordinator.initialize` is untouched. Strategy display/confirm and the
  falsifiability, independent-verification, and digest gates are unchanged.
- No stored-history migration: new writes only (alpha3 zero-compat ruling).
