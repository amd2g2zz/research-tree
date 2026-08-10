## 1. Contract tests

- [x] 1.1 Add valid, repeat, malformed, collision, and dry-run import fixtures.
- [x] 1.2 Define source digest, receipt, historical disposition, conflict, and
  quarantine semantics.

## 2. Implementation

- [x] 2.1 Add SQLite import receipt schema and idempotent receipt operations.
- [x] 2.2 Implement read-only RunStore import and lineage mapping.
- [x] 2.3 Quarantine invalid input and preserve legacy claims as unverified.

## 3. Verification

- [x] 3.1 Run focused import/storage tests, strict OpenSpec validation, full
  regression, and package checks.
- [x] 3.2 Record evidence and preserve remaining migration scope as future work.
