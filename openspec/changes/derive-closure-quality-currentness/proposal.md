## Why

Issue #160 makes a closure input graph durable and exact, but the assessor
still accepts caller-supplied quality claims and cannot prove that a persisted
closure token still reflects the current graph. Favorable caller strings can
therefore make an insufficient graph appear complete, while stale or tampered
stored assessments have no replay check.

## What Changes

- Derive method/provider independence and selected-option contradiction
  coverage only from the current canonical Finding, evidence, receipt, capture,
  and OracleRun graph.
- Replace the established `assess()` argument shape with exact graph inputs.
  Caller quality arguments are removed rather than accepted or persisted.
- Replace the prior closure-assessment payload with one current contract and
  deterministic `is_current()` replay that rejects malformed, stale,
  tampered, or non-replayable assessments. No compatibility reader, migration,
  or legacy schema remains available.
- Register Alpha2 group 47 / GitHub issue #161 as a planned, independently
  verifiable child slice.

## Capabilities

### New Capabilities

- `closure-quality-currentness`: Conservatively derive closure quality and
  prove that a stored closure assessment remains current for its exact graph.

### Modified Capabilities

- None.

## Impact

This change affects `research_tree.closure`, focused closure tests, the
versioned closure-assessment schema, and the Alpha2 execution, verification,
issue, delivery, and umbrella task registries. It does not change durable
content admission, generic writer registration, completion consumption,
correction propagation, CLI routing, or parent group-39 verification.
