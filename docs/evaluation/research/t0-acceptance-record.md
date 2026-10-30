# T0 Acceptance Record — engine & storage skeleton (rt-core TS)

> Issue #554 · Milestone #5 · 2026-10-30/31 · Capability-based: done = achieved
> Suite: **167/167 rt-core vitest** (tsc strict clean; 179 with the pi-host e2e additions) + **1391 legacy Python** (frozen product, regression guard) — all green.

## Exit criterion (roadmap T0)

引擎级集成测试全绿——手工账本走完全链路（含一次中途分解与一次早终止）+ 外部 MCP 调用成功.

## Checklist (issue #554, verified by `test/t0_acceptance.test.ts` + the suites behind each item)

- [x] #546 dual-store consistency + CI replay test green — `store/ledger.ts` hash chain (v1), `graph/projection.ts` adjacency rebuild (v2), `test/graph*.test.ts` replay-equality
- [x] #547 ledger schema/CRUD green — migration v2 (six tables), `test/ledger.test.ts` + `test/claims.test.ts` dual-write
- [x] #548 freeze-only-channel / immutability / fork-lineage / tamper tests green — migration v3, `test/versions.test.ts`
- [x] #549 provenance-drop + checklist-interception pinned green — `test/decomposition.test.ts`
- [x] #550 two-stage recursive walk + ROLLUP + belief propagation + simulated 12h cap green — `test/scheduler.test.ts`
- [x] #551 full-chain walk (对话→计划→两阶段递归→裁决→渲染) incl. mid-chain decomposition + early termination — `test/state_machine.test.ts` + `test/t0_acceptance.test.ts` (headless-driven)
- [x] #552 pi-subagents dispatch substrate + **pi-host end-to-end** — `test/pi_dispatch.test.ts` (agent-type mapping) + the real pi session walk (see below)
- [x] #584 provider port live: anysearch adapter contract tests; audit events carry provider identity; credentials never in the ledger — `test/providers.test.ts`
- [x] #587 agent-browser adapter: read extraction + open+snapshot fallback + structured failures — `test/agent_browser.test.ts`
- [x] #590 web_fetch: html→markdown (readability+turndown), text/code + deterministic summary, pdf/office→markdown via markitdown — `test/web_fetch.test.ts`
- [x] #589 provider search + lazy disclosure (loaded ≤ selected pinned) — `test/plugin_search.test.ts`
- [x] #588 rt setup idempotent + doctor named guidance — `test/setup.test.ts`
- [x] #579 headless runner: JSON Lines + correlated log; gates never silently auto-sign; resume token — `test/headless.test.ts`
- [x] #553 MCP external client completes a minimal flow — `test/mcp_server.test.ts` (transport-independent caller; SDK stdio binding in CLI wiring)
- [x] Engine algorithms unit-pinned per docs 02 §治理与CI — hash chain, snapshot hash, freeze gate, open-loop, belief propagation, dispatch, transition matrix
- [x] #585 legacy host surface removed (codex/claude-code/hermes) — suite 1770→1391 green with re-scoped gates

## pi-host end-to-end (2026-10-31, issue #552 acceptance)

- **Real pi host session** (pi 0.73.1): the rt-core extension (`rt-core/pi-extension/index.ts`) mounted via `pi -e`; the extension factory ran the fake-research walk **inside the pi host process** — full chain (birth→chat→decompose→research→mid-chain re-entry→PAUSE→bury→NO-GO commit v0, deleted_nodes disclosed), marker at `.research-tree/e2e-marker.json`.
- **pi-subagents** installed alongside (nicobailon/pi-subagents 0.84.0 — the tintinweb master clone targets a newer pi API and fails `registerEntryRenderer` on 0.73.1; version note recorded). Both extensions loaded in the same process.
- Residual: the `subagents:ready` bus broadcast fires at session_start, which the keyless `-p` run aborts before — the spawn-through-subagents path needs a keyed session (provider provisioning, #588). Co-presence + clean co-load is verified; the dispatch mapping itself is pinned by `test/pi_dispatch.test.ts`.

## Kùzu deferral (disclosed, per pre-agreed risk path)

kuzu npm 0.11.3 segfaults with concurrent databases / hangs on close (measured 2026-10-30). The graph projection ships on SQLite adjacency behind the unchanged `GraphProjection` port; Kùzu adapter returns when the binding stabilizes. Accepted in PRs #582/#583.

## DSH / external-harness note

pi-only ruling (2026-10-30): DSH items removed from the T0 issue set at split time; #575 withdrawn. MCP exit (#553) is the product interface.

## Verdict

**T0 exit criteria met.** Milestone #5 (T0) closed; T1 wave opens.
