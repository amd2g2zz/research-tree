# stage-scheduler

## Why

Issue #550 (T0 row 5, docs 01 偏航 + 02 §递归阶段化): Stage = kill-graph factor cluster; the open-loop condition (已决 ∥ EVSI 饱和 ∥ 预算尽) → ROLLUP + belief propagation (append-only reopen); dependency-aware dispatch; global 12h hard cap → forced convergence + PARK fallback. Orphan threads park, never block the critical path.

## What changes

- `scheduler/engine.ts` — **pure functions** over a plain state model (the #551 state machine owns the ledger/graph wiring):
  - `evaluateStage`: open-loop triggers (all-decided / EVSI-saturated / budget-exhausted → ROLLUP; else drill-down);
  - `propagateRefutation`: refuted premise → descendants marked stale (append-only reopen counter — 翻案靠重开不靠删除);
  - `checkGlobalCap`: 12h hard cap → forced convergence + PARK;
  - `selectDispatchable`: **dependency-aware ready-set cutting** (≤4 concurrency, worker-class round-robin, retry→park) — the mechanically testable inversion of the #531 greedy-cut failure mode;
  - EVSI scorer signature fixed to the 01 A3 shape (EVSI/cost), placeholder implementation `TODO(issue-557)`.

## impact_scope

- `rt-core/src/scheduler/engine.ts` (new, pure — no I/O)
- tests: `rt-core/test/scheduler.test.ts`
