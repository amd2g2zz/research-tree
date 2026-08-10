## 1. Contract and red tests

- [x] 1.1 Add a strict-delivery fixture with one canonical RunLedger, matching EvidenceResolver, validated readiness projection, strict Finding Pack, and Decision.
- [x] 1.2 Add a failing round-trip test for the canonical facade, including exact evidence refs in both output lineages and typed-anchor Markdown rendering.
- [x] 1.3 Add failing tests for a foreign resolver, malformed readiness projection, stale or missing evidence, missing evidence parent, and foreign Target/Slot lineage.
- [x] 1.4 Add a failing atomicity test proving a stale expected run revision or injected second-write failure leaves no output pair.
- [x] 1.5 Add a regression test proving the existing RunStore compiler remains compatible and rejects canonical-only controls.

## 2. Atomic ledger primitive

- [x] 2.1 Implement a small `RunLedger` batch-append primitive that validates all existing and intra-batch parents under one expected revision.
- [x] 2.2 Make batch append write artifact rows, parent rows, events, and the run revision in one transaction with rollback on any failure.
- [x] 2.3 Add focused ledger tests for parent ordering, revision conflict, duplicate artifact identity, and rollback.

## 3. Canonical strict delivery

- [x] 3.1 Add the `CanonicalDeliveryCompiler` facade and enforce matching ledger/resolver construction.
- [x] 3.2 Validate the existing readiness projection mapping and use it during the canonical document build without introducing a Readiness artifact cycle.
- [x] 3.3 Re-resolve every strict Finding observation, verify exact current evidence and direct parent lineage, and collect deterministic evidence refs.
- [x] 3.4 Preserve resolved strict evidence through output parent lineage and typed-anchor rendering without changing the legacy delivery schema or human-brief kind.
- [x] 3.5 Compile the two outputs only after complete preflight and append them through the atomic ledger primitive.
- [x] 3.6 Export the canonical facade and stable errors from the public package surface.

## 4. Verification and handoff

- [x] 4.1 Run focused strict-delivery, ledger, readiness, evidence, and delivery regression tests.
- [x] 4.2 Run the complete `uv run pytest -q`, OpenSpec strict validation, package/build checks, and repository delivery gate.
- [x] 4.3 Update the issue-scoped evidence receipt and mark only these tasks complete with command evidence.
- [ ] 4.4 Create one signed-off PR targeting `dev`, link only #110, and keep the diff within review limits.
