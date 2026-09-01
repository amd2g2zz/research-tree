## Why

The Alpha2 design, lifecycle matrix, and issue registry describe the intended
runtime, but `dev` lacks the four accepted ADRs that make the architectural
boundaries reviewable and enforceable. Those missing decisions leave later
runtime work able to reinterpret authority, graph, storage, or host boundaries.

## What Changes

- Add ADRs for the single completion authority, separate graph boundaries,
  SQLite plus content-addressed storage, and host adapters as event translators.
- Add a compact contract-ratification specification that requires each ADR to
  resolve to the Alpha2 design, lifecycle matrix, capability specs, and issue
  registry.
- Add a deterministic documentation/registry test that prevents an incomplete
  ADR set or stale issue-to-change mapping from passing review.
- Update contributor-facing architecture links to make the ratified contract
  discoverable without treating generated host copies as the source of truth.

## Capabilities

### New Capabilities
- `alpha2-contract-ratification`: Reviewable architectural decisions and
  traceability required before dependent Alpha2 runtime implementation.

### Modified Capabilities
- None.

## Impact

Adds normative documents under `docs/adr/`, a focused OpenSpec specification,
and validation tests. It does not alter runtime behavior, migration data, host
package semantics, or release status.
