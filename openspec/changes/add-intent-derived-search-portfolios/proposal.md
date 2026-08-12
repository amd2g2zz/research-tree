## Why

Alpha2 can capture sources and checkpoints, but acquisition still lacks one
canonical plan that derives search work from intent, records method boundaries,
and decides whether a batch is deep enough to close a Decision Slot. Without
that contract, repeated queries through one backend can look like independent
research and shallow evidence can move directly to delivery.

## What Changes

- Add a SearchPortfolio contract that binds intent, working brief, strategy,
  Decision Slot, evidence deficit, subquestions, method choices, and stop/replan
  criteria.
- Add method/provider boundary semantics so query diversity, provider
  diversity, direct retrieval, repository inspection, documentation lookup,
  scholarly lookup, and experiments are distinct and auditable.
- Add post-batch coverage assessment that can stop, deepen, broaden, switch
  method, run an experiment, create a successor strategy, or record a typed
  blocker.
- Register group-27 ownership, focused tests, and source-bound evidence for
  #83 without changing #80 capture/checkpoint authority or #58 policy ownership.

## Capabilities

### New Capabilities

- `search-portfolios`: Intent-derived research acquisition plans, method
  boundaries, post-batch coverage assessment, and strategy pivot lineage.

### Modified Capabilities

- `research-acquisition`: Require acquisition work to consume SearchPortfolio
  lineage and preserve #80 source capture/checkpoint bindings.

## Impact

- Adds SearchPortfolio runtime contracts and tests under `src/research_tree/`
  and `tests/`.
- Updates the umbrella Alpha2 registries/tasks for group 27 evidence.
- May update package exports, host-neutral references, or CLI surfaces only when
  needed to expose the typed contract.
