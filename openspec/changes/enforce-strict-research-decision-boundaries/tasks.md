## 1. Strict resolver contract and red tests

- [x] 1.1 Add strict resolver tests for restart, exact refs, stale revisions,
  repository source revisions, scope escapes, and selector bounds.
- [x] 1.2 Reject reversed fragments and missing semantic selector metadata.

## 2. Canonical Finding/Decision/Readiness contract and red tests

- [x] 2.1 Add public-path tests proving strict evidence survives
  Finding Pack -> Decision -> Readiness and generic legacy evidence cannot
  satisfy the strict path.
- [x] 2.2 Add regression that the legacy compiler cannot advertise strict
  evidence using a caller-owned resolver.

## 3. Strict-boundary implementation

- [x] 3.1 Implement ledger-backed strict evidence resolution and fail-closed
  bounds/source-revision checks.
- [x] 3.2 Implement canonical Finding Pack and Decision compilers with exact
  evidence parent lineage.
- [x] 3.3 Implement canonical strict readiness revalidation and legacy
  non-authoritative handling.

## 4. Verification and handoff

- [ ] 4.1 Run focused resolver and canonical-boundary tests plus relevant
  regression suite.
- [ ] 4.2 Run strict OpenSpec validation, full repository regression, and
  delivery workflow checks for issue #108.
- [ ] 4.3 Commit/push the scoped work on the #108 branch and open its only PR.
