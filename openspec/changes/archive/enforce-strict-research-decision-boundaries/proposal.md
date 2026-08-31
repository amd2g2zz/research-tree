## Why

Alpha2 now has a canonical evidence foundation (#111), but the research state
can still be changed through a digest-map resolver, a legacy Finding Pack, or
a worker's self-reported validation. The former prototype also accepted
reversed fragment ranges and did not fail closed when a repository source
revision was unavailable. This change makes the public research decision
boundary require exact, resolvable evidence.

## What Changes

- Add a ledger-backed strict `EvidenceResolver` that validates exact
  artifact identity, CAS binding, lifecycle, current revision, repository
  source revision, scope, and selector bounds.
- Make strict Finding Packs use canonical RunLedger storage and include exact
  evidence parent lineage; legacy Finding Packs remain explicit historical
  compatibility data.
- Add a canonical Decision compiler and strict readiness mode so
  non-authoritative evidence cannot close an Alpha2 research decision.
- Add focused fault-injection and public-path regression coverage.

## Capabilities

### New Capabilities

- `strict-evidence-decision-boundary`: Defines the canonical resolver and
  Finding Pack/Decision/Readiness transition boundary.

### Modified Capabilities

- None.

## Impact

- `src/research_tree/evidence.py`, `ledger.py`, and `readiness.py` gain the
  strict boundary.
- Focused resolver and canonical public-path tests accompany the change.
- Evidence persistence (#111), Delivery rendering (#110), group-3 registry
  (#112), OracleRun, and coordinator lifecycle APIs remain out of scope.
