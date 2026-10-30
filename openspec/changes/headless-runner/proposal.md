# headless-runner

## Why

Issue #579 (user add, T0; docs 02 产品层 CLI headless --json): one headless entry driving the product state machine from a declarative launch script — scripting/CI entry, the vehicle for the T0 exit walk, and the data source for the terminal UI (#580).

## What changes

- `headless/runner.ts`: runHeadless —
  - **launch script** (declarative steps + pre_signed policy) drives the #551 state machine;
  - **JSON Lines event mirror** (emit) + **detailed human-readable log** (log) — transitions with reasons, correlations by task_id;
  - **consent fail-closed**: verdicts/early-termination choices only from pre_signed policy; an unhandled mid-run gate PAUSEs with outcome "paused-pending-decision" + a **resume token** (same ledger, no fork);
  - exit outcomes: success / paused-pending-decision / fail-closed / park (12h-cap matrix consistent — cap=park-class).
- Script `open-draft` step: the commit path opens the working draft explicitly (A7: writes happen on drafts).

## impact_scope

- `rt-core/src/headless/runner.ts` (new)
- tests: `rt-core/test/headless.test.ts`
