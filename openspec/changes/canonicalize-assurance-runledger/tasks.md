## H. Canonical Assurance

- [x] 1.1 Add a focused RED assurance suite using canonical fixture lineage.
- [x] 1.2 Define the direct RunLedger and expected-revision contract.

- [x] H.1 Replace RunStore assurance classes with canonical implementations.
- [x] H.2 Route blocked decisions through the canonical decision compiler.
- [x] H.3 Remove the legacy assurance public exports and fixture only after no
  remaining test or runtime consumer references them.

## I. Canonical Authoring Graph

- [ ] I.1 Replace direct RunStore intake, intent, blueprint, and work-item writers.
- [ ] I.2 Migrate their direct tests without a compatibility fixture or store.
- [ ] I.3 Retire legacy authoring exports only after all direct consumers move.

## J. Canonical Delivery and Evaluation

- [x] J.1 Eliminate legacy Finding Pack and Decision Ledger compiler consumers.
- [x] J.2 Retire legacy delivery/readiness branches after their canonical paths pass.
- [x] J.3 Split evaluation to a canonical-only ledger implementation.

## K. Feedback and Tree State

- [x] K.1a Define and test the restricted cross-run successor transaction.
- [x] K.1 Replace feedback successor-copy behavior with direct ledger artifacts.
- [x] K.2 Replace tree-state persistence and migrate recursive-search consumers.
- [x] K.3 Rewrite alignment handoff after canonical tree state exists.

## L. Active Contracts and Generated Hosts

- [ ] L.1 Remove active RunStore claims from exports, README, references, ADRs, and registries.
- [ ] L.2 Regenerate host packages from their authoritative sources.
- [ ] L.3 Preserve historical specs, archived changes, and source-bound receipts.

## M. Final Absence Proof

- [ ] M.1 Add a RED structural absence test across runtime, tests, active docs, schemas, CLI, and packages.
- [ ] M.2 Delete remaining legacy source, exports, fixtures, and tests without aliases.
- [ ] M.3 Run the full #165 gate, record ignored local evidence, and verify the diff with GitNexus.
