## 1. Contract Tests

- [x] 1.1 Add failing tests for workspace initialization, SQLite durability
  settings, and schema migration idempotency.
- [x] 1.2 Add failing tests for immutable artifacts, parent integrity, stale
  expected revisions, idempotent events, and conflicting event retries.
- [x] 1.3 Add failing reconstruction, interrupted-write, and concurrent
  reader/writer tests.

## 2. Ledger Implementation

- [x] 2.1 Implement the RunLedger protocol, schema initialization, and typed
  SQLite error boundary.
- [x] 2.2 Implement transactional run creation and immutable artifact append
  with parent references and optimistic revisions.
- [x] 2.3 Implement idempotent event append and validated deterministic run
  reconstruction.

## 3. Verification And Scope Control

- [x] 3.1 Run focused storage tests, OpenSpec strict validation, package
  validation, and complete regression tests.
- [x] 3.2 Record verification evidence and mark group 2 in progress without
  claiming CAS or legacy import completion.
- [x] 3.3 Create or update follow-on issue plans for CAS and legacy import so
  the original #53 acceptance scope remains traceable without enlarging this PR.
