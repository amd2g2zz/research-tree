# mcp-server

## Why

Issue #553 (T0 row 7, 产品不变式: MCP 是出口; roadmap T0 row 7). External harnesses consume rt without touching internals — the seam is the deliverable schema (charter §8). **pi 独占裁定注**: MCP is the product exit interface, not a harness compatibility layer; the #575 external-harness field test was withdrawn with that ruling.

## What changes

- `mcp/server.ts`: `createMcpServer` returns the transport-independent `McpToolCaller` (the official SDK binds the same handler to a stdio transport in the CLI wiring):
  - `rt.start` — begin/continue a task (opens the machine phase);
  - `rt.status` — phase + ledger digest + draft/version pointers;
  - `rt.correct` — steering input routed through the same correction path as chat (no privileged channel; the action lands as an engine fact);
  - `rt.verdict` — report + 底稿 paths + version metadata when committed.
- Projection-only: no state merge into the harness (LoopX/DSH lesson).

## impact_scope

- `rt-core/src/mcp/server.ts` (new), `rt-core/package.json` (@modelcontextprotocol/sdk, zod)
- tests: `rt-core/test/mcp_server.test.ts`
