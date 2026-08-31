## Why

Alpha2 needs a trustworthy comparison point for the defects observed in the
`0.0.1-a1` release. The current repository has a generic evaluation case file,
but it does not preserve a pinned Alpha1 failure corpus, its replay contract, or
the boundary between worker-visible inputs and evaluator-owned expected
outcomes. Without that baseline, later quality gates can claim improvement
without proving that a known unsafe behavior was actually tested.

## What Changes

- Add a versioned Alpha1 adversarial baseline manifest pinned to the immutable
  `0.0.1-a1` release commit and its three host packages.
- Register representative Alpha1 failures across evidence closure, report
  quality, recursive research, alignment, host completion, provider recovery,
  and crash recovery.
- Add a baseline evaluator that validates manifest structure, classifies
  reproduced, inconclusive, and evidence-backed fixed outcomes, and keeps the
  expected unsafe behavior outside the worker-visible manifest.
- Define durable, machine-readable result receipts that bind a case to the
  baseline revision, observed result, command, and evidence references.
- Add TDD coverage for malformed manifests, hidden-oracle separation,
  classification semantics, and deterministic aggregate results.

## Capabilities

### New Capabilities

- `alpha1-adversarial-baseline`: A pinned, replayable, evaluator-governed
  corpus of Alpha1 failure cases and result receipts used by later Alpha2
  evaluation gates.

### Modified Capabilities

None.

## Impact

- Adds evaluation fixtures beneath `evaluation/cases/`, an evaluator module
  beneath `src/research_tree/`, and tests under `tests/`.
- Does not alter runtime completion behavior, host packages, or public CLI
  contracts in this issue.
- Establishes task group 1 in the Alpha2 execution registry; later storage,
  quality, benchmark, and black-box work consume this baseline.
