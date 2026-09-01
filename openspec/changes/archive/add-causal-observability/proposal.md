## Why

Alpha2 has a single SQLite-backed lifecycle authority, but operators still cannot reconstruct why a transition or action occurred from a stable causal view. Existing opt-in debug files are safe but non-authoritative and cannot prove replay or explain completion blockers.

## What Changes

- Project canonical lifecycle artifacts into bounded, schema-versioned causal traces.
- Add deterministic replay and state-digest verification from immutable ledger lineage.
- Add run, action, non-completion, and host-reconciliation explanations that cite exact artifacts.
- Keep provider diagnostics sanitized and host completion claims non-authoritative.
- Make focused pytest, Ruff lint, and Ruff formatting checks one TDD acceptance gate.

## Capabilities

### New Capabilities

- `runtime-observability`: Causal transition projections, deterministic replay, evidence-backed explanations, privacy-preserving diagnostics, and read-only host reconciliation.

### Modified Capabilities

- None.

## Impact

The change affects `research_tree.debug_trace`, the coordinator's explanation boundary, the `research-tree-debug` CLI, focused debug/replay tests, and Alpha2 group-11 execution and verification records. It adds no dependency and does not grant traces or hosts lifecycle authority.
