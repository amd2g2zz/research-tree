## 1. Strategy Projection Contract

- [ ] 1.1 Add failing schema/domain tests for required fields, canonical round trip, deterministic digest, revisions, and invalid projections.
- [ ] 1.2 Implement the immutable StrategyProjection model, schema, examples, and SQLite migration.

## 2. Coordinator Handoff Boundary

- [ ] 2.1 Add failing tests for display receipts, contextual confirmation, generic/stale/incomplete rejection, duplicate replay, and transactional rollback.
- [ ] 2.2 Implement coordinator-owned projection persistence, display, confirmation, dispatch guards, and stable diagnostics.
- [ ] 2.3 Add strategy revision versus material successor behavior and correction invalidation tests/implementation.

## 3. Lifecycle and Host Parity

- [ ] 3.1 Add macro-stage mapping and pause/resume/delivery-resume replay tests and implementation.
- [ ] 3.2 Add Codex, Claude Code, and Hermes semantic projection parity fixtures with honest unavailable capability handling.
- [ ] 3.3 Prove legacy alignment, RunStore, host task/report, and direct dispatch paths cannot bypass the canonical handoff.

## 4. Verification and Delivery Evidence

- [ ] 4.1 Update lifecycle, schema, task-execution, delivery, and verification registries for group 28.
- [ ] 4.2 Run focused pytest plus Ruff lint/format checks, full regression, both strict OpenSpec validations, package parity, governance, delivery, and git diff checks.
- [ ] 4.3 Record the source-bound group 28 receipt and mark canonical group 28 tasks complete only from verified evidence.
