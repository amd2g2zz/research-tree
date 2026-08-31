## 1. Lifecycle Authority

- [x] 1.1 Write red tests for initialization, legal/illegal transitions, actor permissions, and terminal idempotency.
- [x] 1.2 Implement versioned run-state artifacts and lifecycle matrix validation.
- [x] 1.3 Add exact alignment/Blueprint lineage and stale-revision rejection.

## 2. Atomic Runtime Operations

- [x] 2.1 Write red tests for dispatch, lease, host-event ingestion, duplicate/conflicting events, and stale writes.
- [x] 2.2 Implement atomic event/state persistence and idempotency.
- [x] 2.3 Implement why-not-complete and the complete obligation conjunction.

## 3. Recovery and Governance

- [x] 3.1 Add crash-prefix replay, unknown lease recovery, correction/supersession, and authority-bypass tests.
- [x] 3.2 Export the coordinator API without granting authority to host projections.
- [x] 3.3 Run focused pytest and Ruff checks, then full regression, strict OpenSpec, package, governance, and delivery checks.
