# mock-e2e-research-loop

## Why

Issue #607 (user directive 2026-10-31: "现在开始做mock e2e测试"): the T0 modules are unit-pinned individually, but the **research loop internals** — scheduler rounds dispatching workers, providers feeding evidence into claims, belief propagation on refutation, retry→park — had no integrated test. This change adds the mock e2e: the complete stack (event log, ledger, versions, state machine, scheduler, pi-subagents dispatch, audited providers, headless runner, MCP) driven through full research runs with every external boundary mocked (LLM/CLIs/network: zero real calls).

## What changes

- `test/e2e_mock_research.test.ts`: three scenario runs over a research-loop harness (scheduler rounds + pi-subagents dispatch + audited evidence search + dual-write claim updates — the loop the #552 pi extension drives in production, with every boundary faked):
  1. **GO**: rounds until rollup (all-decided), GO commit, audit trail (transitions/provider.actions/claim.upserts), graph rebuild == live, MCP verdict GO;
  2. **NO-GO**: make-or-break refutes → belief propagation reopens descendants → hard gate PAUSE → resume continue → stage reopens → re-verified → NO-GO commit; bury path → converge;
  3. **PARK**: worker fails ×3 → retry→park → converge → PARK commit.
- `scheduler/engine.ts`: **vacuous-truth fix** — a stage with no open claims rolls up (all-decided vacuously); previously an empty-claim stage drilled forever.

## impact_scope

- `rt-core/test/e2e_mock_research.test.ts` (new), `rt-core/src/scheduler/engine.ts` (vacuous-truth fix, pinned)
- docs-governance registry: rt-core/pi-extension/README.md entry (follow-up to #606)
