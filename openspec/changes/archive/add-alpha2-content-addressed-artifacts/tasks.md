## 1. Contract and tests

- [x] 1.1 Add tests for digest deduplication, metadata registration, binding,
  tamper detection, invalid paths, and orphan quarantine.
- [x] 1.2 Define the CAS layout, SQLite metadata schema, availability states,
  idempotency rules, and failure boundary.

## 2. Implementation

- [x] 2.1 Implement staged, fsynced, digest-verified immutable publication and
  verified reads.
- [x] 2.2 Add SQLite schema version 2 content metadata and artifact bindings.
- [x] 2.3 Add typed metadata conflict, binding conflict, and quarantine paths.

## 3. Verification

- [x] 3.1 Run focused tests, strict OpenSpec validation, full regression, and
  package checks.
- [x] 3.2 Record evidence without claiming legacy import or remote storage.
