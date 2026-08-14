## 1. Typed delivery boundary

- [x] 1.1 Add a transactional completion-input batch for dual delivery and
  extend registration reads to canonical delivery roles.
- [x] 1.2 Require canonical pair kinds, exact technical revision binding,
  dedicated delivery and acceptance issuers, and current non-quarantined
  parent lineage.
- [x] 1.3 Route strict `CanonicalDeliveryCompiler` writes through the typed
  pair writer without changing rendering or legacy `RunStore` behavior.

## 2. Acceptance writer

- [x] 2.1 Add a ledger-backed `DeliveryAcceptance` writer with exact revision,
  display digest, manifest digest, actor, and pair-parent checks.
- [x] 2.2 Prove generic lookalikes, mismatched/cross-run/stale/quarantined
  pairs, wrong actors, replacement issuers, and commit faults fail atomically.
- [x] 2.3 Prove duplicate matching pair and acceptance writes are idempotent.

## 3. Verification and handoff

- [x] 3.1 Add focused red/green delivery-registration tests and run the
  adjacent strict delivery/lifecycle regression suite.
- [ ] 3.2 Record the source-bound group-44 receipt after final verification.
- [ ] 3.3 Run delivery governance, open the single Issue #157 PR, and merge it
  to `dev` with PR body `Closes #157` only.
