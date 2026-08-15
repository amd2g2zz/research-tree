## Context

`RunLedger` is the current SQLite authority. `CanonicalFindingPackCompiler`
and `CanonicalDecisionLedgerCompiler` already resolve exact artifact revisions
and require a matching ledger-backed `EvidenceResolver`. The old assurance
classes instead load a `RunStore` snapshot and append JSON artifacts without a
revision precondition.

## Design

`CanonicalAssuranceStrategySelector(ledger)` loads the current run, validates
the exact persisted strategy and blueprint target revisions, and appends one
`assurance-adapter-selection` artifact with the caller-provided
`expected_revision`.

`CanonicalAssuranceAdapterRunner(ledger, resolver)` validates the exact
selection and canonical decision revisions in the same ledger, invokes the
existing selected assurance ports, and appends the unchanged assurance evidence
payload. It advances the expected revision for each follow-up, blocked decision,
and resolution write. A blocked decision is compiled through
`CanonicalDecisionLedgerCompiler(ledger, resolver)`, preserving exact canonical
Finding Pack and evidence parent references.

The source observation remains the existing bounded four-field assurance
record. It is validated directly; no prior-version payload parser is retained.

## Risks

`RunLedger.append_artifact` has a HIGH graph blast radius (25 direct callers,
110 symbols through depth three), so this slice consumes but does not modify it.
The affected assurance classes, legacy decision compiler, canonical decision
compiler, and canonical fixture are each MEDIUM risk; focused behavior and
stale-revision tests run before the full suite.

## Migration

The public assurance class names change without aliases. Consumers must provide
the current run revision and matching resolver. Rollback is a Git revert; it
does not add a RunStore fallback or mutate user-owned data.
