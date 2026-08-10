## Context

Alpha2 persists canonical artifact identity, but legacy digest maps, generic
anchors, and worker validation can still influence decisions. The public path
must be exact ledger evidence -> Finding Pack -> Decision -> strict readiness.
OracleRun and closure-token schemas remain separate work.

## Goals and Boundaries

- Resolve strict anchors only through RunLedger and its bound CAS content.
- Fail closed for missing, stale, out-of-scope, reversed, out-of-range, or
  source-revision-unverifiable evidence.
- Keep RunStore compilation legacy-only; canonical Finding, Decision, and
  Readiness use RunLedger.
- Do not change evidence persistence (#111), Delivery rendering (#110),
  group-3 governance (#112), OracleRun, or coordinator lifecycle APIs.

## Decisions

### Strict resolution is ledger-only

`EvidenceResolver.from_ledger()` is the only strict resolver construction. It
requires an exact `ArtifactRef`, verifies the immutable evidence payload, bound
CAS content, and latest revision. Repository locators also require a source
revision and a caller-supplied current revision oracle. That oracle is a
trusted host/repository-adapter boundary; the resolver compares against it but
does not prove a filesystem or VCS revision. Missing selector bounds fail
closed. The in-memory resolver remains for historic readers only.

### Canonical artifacts carry the evidence closure

`CanonicalFindingPackCompiler` and `CanonicalDecisionLedgerCompiler` append to
the same RunLedger with an expected revision. Strict Findings store typed
anchors and every exact evidence parent. Selected or conditional Decisions
require a strict Finding for the exact Target and Slot, a support effect for
the selected option, and that Finding's evidence parents. Non-strict Findings
are rejected. The compatible RunStore compiler always emits
`legacy_unverified` and cannot enter this path.

### Readiness rechecks semantic relevance

`CanonicalReadinessVerifier` uses a matching strict resolver, re-resolves
non-empty Findings, and checks that each selected/conditional Decision keeps
matching Target/Slot Findings, selected-option support, and exact evidence
parents. Any failure makes closure/readiness fail.

## Risks, Migration, and Ownership

- Unresolvable evidence can leave slots open; use a bounded validation
  continuation rather than weakening the gate.
- Existing RunStore history remains readable through compatibility mode.
- Canonical artifacts are append-only; rollback stops the strict compiler.
- DeliveryCompiler support for canonical packages remains owned by #110.
