## Why

The legacy recursive-search ingestion path currently treats a worker-provided
`validation_result.status="passed"` as authoritative slot-closure evidence.
That permits an unverified Finding Pack to close a P0 decision slot and unlock
delivery, contradicting the Alpha2 evidence-verification contract.

## What Changes

- Treat every worker-supplied validation result as an observation rather than
  an authority for `validation_passed`.
- Record a worker-reported pass explicitly as `reported_passed_untrusted` and
  create one mandatory verifier-needed validation continuation.
- Preserve worker failure accounting and the existing independent retry path.
- Add focused regression coverage for passed, failed, missing, malformed, and
  repeated worker validation results.
- Reconcile the #109 tracker relationship: this is a narrow legacy projection
  defense, not completion of the canonical Alpha2 OracleRun migration or a
  retroactive provenance migration for old persisted states.

## Capabilities

### New Capabilities

- `worker-validation-trust`: Prevent worker-authored validation observations
  from authoritatively closing legacy recursive-search decision slots.

### Modified Capabilities

- None.

## Impact

- `src/research_tree/recursive_search.py` changes only at the Finding Pack
  ingestion boundary.
- `tests/test_recursive_search.py` gains trust-boundary regressions.
- No public schema, storage migration, host package, canonical OracleRun, or
  delivery-lineage behavior is introduced by this slice.
