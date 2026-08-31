## Why

The three completion-authority child deliveries are now merged, but their
parent tracker has no single, reachable proof that generic ledger artifacts
cannot satisfy completion.  The parent acceptance must bind the child receipts
and exercise the finished manifold boundary before #149 can close.

## What Changes

- Add a parent-level false-completion oracle that verifies group 43, 44, and
  45 receipts are reachable from the parent baseline.
- Prove the completed runtime consumes only registered completion inputs,
  preserves historical completion records, and reports deterministic failure
  after stale or quarantined parents reopen the manifold.
- Register and verify parent group 36, with a source-bound receipt that closes
  only #149.

## Capabilities

### New Capabilities

- `canonical-completion-integrity`: Parent acceptance for the registered,
  revision-bound completion manifold and its false-completion oracle.

### Modified Capabilities

- None.

## Impact

This affects parent-only acceptance tests and Alpha2 execution registries. It
does not add a public API, change child writers, route a CLI command, or create
a compatibility path.
