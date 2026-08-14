## 1. Red boundary tests

- [x] 1.1 Reject the former generic `ingest_event()` payload and prove no
  ledger revision or artifact changes.
- [x] 1.2 Cover inactive/expired leases, causal ordering, exact checkpoint
  digests, orphan references, and atomic worker-finished rejection.
- [x] 1.3 Prove a native adapter emits the explicitly supplied canonical
  revision even after local state revisions advance.

## 2. Canonical implementation

- [x] 2.1 Add causal envelope round-trip and dependency-free protocol support.
- [x] 2.2 Enforce active lease, expiry, binding, revision, sequence, and
  predecessor causation before the transactional batch append.
- [x] 2.3 Resolve committed capture/receipt/checkpoint/finding/produced refs
  and checkpoint digests before accepting worker completion.
- [x] 2.4 Keep duplicate replay idempotent and conflicting event ids rejected.

## 3. Cross-host distribution

- [x] 3.1 Require explicit canonical revision in the native adapter API/CLI.
- [x] 3.2 Update Hermes causation support and recovery event lineage.
- [x] 3.3 Rebuild Codex, Claude, and Hermes generated package copies and run
  source/package checks.

## 4. Evidence and handoff

- [ ] 4.1 Run focused/full tests, Ruff, OpenSpec, package, governance, and
  delivery checks on the final source revision.
- [ ] 4.2 Record immutable command receipts, register group 61 / issue #151,
  run `detect_changes()`, and open one PR with `Closes #151`.
