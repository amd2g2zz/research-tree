# product-state-machine

## Why

Issue #551 (T0 rows 5+exit, docs 02 引擎层新建核心件): the product state machine is the **single phase authority** — the structural answer to the #530 finding (phase authority has no writer). Every transition is an engine fact (task.transition event) consumable by headless (#579), canvas (#559), hooks.

## What changes

- `state/machine.ts`: ProductStateMachine —
  - matrix CHAT→DECOMPOSE→RESEARCH⟲→CONVERGED→COMMITTED→CHAT(继承对齐)→RESEARCH[vN+1]; fork birth;
  - **freeze gate**: committed reachable only from converged through freezeTask (VersionStore.freeze — no bypass); commit is a transient fact, the machine lands in chat (inherit-and-realign);
  - **sign gate**: research requires a confirmed decomposition (#549) + attached run plan;
  - **early-termination hard gate** (run-plan fail-closed): refuted make-or-break → paused; continuation blocked until 埋了/继续挖 (T0 PAUSE primitive — variant search #563);
  - **mid-chain re-entry**: research → chat, ledger intact;
  - **event-sourced**: rehydrate rebuilds phases from task.transition events alone.
- `state/run_plan.ts`: plan = data — parse (12h budget cap invariant, yaw slots/modes) + validate + RunPlanInterpreter (mechanical step advancement).
- Event vocabulary: `task.transition` (flat, from/to/reason; backward-compatible).

## impact_scope

- `rt-core/src/state/{machine,run_plan}.ts` (new), `rt-core/src/events/schema.ts` (task.transition), `rt-core/src/graph/projection.ts` (no-op handler), `rt-core/src/store/engine.ts` (ledgerStore accessor)
- tests: `rt-core/test/state_machine.test.ts`
