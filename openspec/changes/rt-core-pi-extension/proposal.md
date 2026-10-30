# rt-core-pi-extension

## Why

Issue #552 (T0 row 6, 产品不变式: **pi 是家**). rt = pi native application — extension + subagent pool + session tree. Per the 2026-10-30 amendment: **subagent dispatch rides the official pi-subagents extension** (pi.dev catalog) — rt-core does NOT build session/fleet management; it maps the 4 worker classes onto custom agent types and expresses the dispatch policy as extension invocations.

## What changes

- `pi/dispatch.ts`:
  - **WORKER_AGENT_TYPES**: one custom agent type per worker class (rt-retrieval / rt-code-reading / rt-experiment / rt-verification) — compiler-checked mapping;
  - **buildAgentDefinitions**: agent definitions carry each class's contract (two-layer contract: prompts carry the open-ended strategy);
  - **dispatchStage**: stage work dispatched onto the mapped agent type via the structural `PiSubagentsApi` port (≤4 concurrency cut comes from the scheduler's ready set; fresh-context blind verification is the rt-verification contract);
  - claim context (state, posterior, premises) rides the dispatch prompt — the worker knows what it stands on.
- `PiSubagentsApi` is the structural port the extension satisfies; tests inject fakes.

## impact_scope

- `rt-core/src/pi/dispatch.ts` (new)
- tests: `rt-core/test/pi_dispatch.test.ts`
