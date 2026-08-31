## Why

The strict SearchPortfolio and intent-derived planner identify method/provider
boundaries but do not yet represent execution outcomes or make a typed next
research decision. A failed or shallow batch can therefore be mistaken for
completed independent evidence.

## What Changes

- Add immutable method execution outcomes and dependency-ready portfolio batch
  values bound to the selected method/provider boundary and stable query refs.
- Add typed 404, no-result, parser-failure, rate-limit, and shallow outcomes;
  choose a fallback boundary when one is available and report degraded
  capability when the registry cannot provide independent boundaries.
- Assess coverage, novelty, contradiction, source quality, provenance
  independence, and unresolved decision risk after every batch.
- Return only typed stop, rewrite, switch, deepen, experiment, pivot, or
  blocked decisions as a pure projection for later coordinator integration.
- Register group 75 / issue #186 without changing the #83 parent acceptance or
  introducing durable coordinator state.

## Non-Goals

- Do not redefine the #163 SearchPortfolio or MethodRegistry contract.
- Do not persist portfolio state, source captures, checkpoints, or assessments
  through the coordinator; #187 owns canonical runtime lineage.
- Do not change worker-finish gating, AdaptiveResearchPolicy persistence, CLI
  routing, or close #83.
