## Context

The evidence foundation persists canonical artifact identity, but older paths
still allow a caller-owned digest map, generic anchors, or worker-provided
validation to influence decision state. The strict boundary has to be a
single public path: exact ledger evidence -> canonical Finding Pack ->
canonical Decision -> strict readiness. OracleRun and closure-token schemas
remain separate Alpha2 work and are not invented here.

## Goals / Non-Goals

**Goals:**

- Resolve canonical anchors only through the RunLedger and its bound CAS
  content.
- Fail closed for missing, stale, out-of-scope, reversed, out-of-range, or
  source-revision-unverifiable evidence.
- Make RunStore Finding Pack compilation explicitly legacy-only; canonical
  strict compilation and decision convergence use RunLedger.
- Make strict readiness re-resolve every consequential observation before it
  can report a pass.

**Non-Goals:**

- Define OracleRun, evaluator receipts, or SlotClosureAssessment.
- Change evidence persistence (#111), Delivery rendering (#110), or group-3
  governance (#112).

## Decisions

### Strict resolution is ledger-only

`EvidenceResolver.from_ledger()` is the only strict resolver construction.
It requires an exact `ArtifactRef`, verifies the immutable evidence payload,
the bound CAS content, and the latest artifact revision. Repository locators
require both an evidence source revision and a caller-supplied current
revision oracle. That oracle is a trusted host/repository-adapter boundary:
the resolver compares against it but does not itself prove a filesystem or VCS
revision. Selector validation is fail-closed when its declared bounds are
absent.

The legacy in-memory resolver is retained only for historic readers. It cannot
be used by the canonical Finding/Decision/Readiness path.

### Strict research state uses canonical artifacts

`CanonicalFindingPackCompiler` and `CanonicalDecisionLedgerCompiler` append
to the same RunLedger using an expected revision. A strict Finding Pack stores
typed anchors and adds every exact evidence reference to its parent lineage.
Every selected or conditional canonical Decision requires at least one strict
Finding Pack for its exact Target and Slot, with a support effect for the chosen
option and exact evidence parent. The canonical decision rejects any supplied
finding that is not strict or lacks its evidence parent. The legacy RunStore compiler remains compatible
but always emits `legacy_unverified` evidence and can never enter this path.

### Strict readiness rechecks evidence

`CanonicalReadinessVerifier` uses RunLedger plus a matching strict resolver.
It re-resolves non-empty findings in the technical package, and verifies that
every selected or conditional Decision retains matching Findings, selected-option
support, and exact evidence parents. Any evidence failure turns closure/readiness into a failure.
This closes the historical bypass where a generic legacy anchor could appear in
an otherwise passing readiness record.

## Risks / Trade-offs

- [Risk] Slots remain open longer because a self-report or unresolvable anchor
  no longer closes them.
  -> Mitigation: add a bounded, deduplicated validation continuation.
- [Risk] The current DeliveryCompiler cannot yet render a strict canonical
  package. -> Mitigation: this slice accepts typed anchors during readiness
  validation; #110 owns canonical delivery compilation and rendering.

## Migration Plan

Existing persisted RunStore history remains readable through explicit legacy
mode. Strict canonical artifacts are appended-only; rollback means stopping
use of the strict compiler, not deleting evidence.

## Open Questions

- Canonical Delivery compilation and rendering are owned by #110.
