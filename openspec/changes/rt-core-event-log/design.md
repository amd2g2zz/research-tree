# design — rt-core-event-log

## Layout

New package `rt-core/` (pnpm, strict tsc, vitest):

- `src/events/canonical.ts` — canonical JSON (sorted keys) = hash-chain input.
- `src/events/schema.ts` — the 11-type vocabulary + declarative `EVENT_SPECS`
  + generic validation engine; `vocabulary.ts` is the public barrel.
- `src/store/ledger.ts` — better-sqlite3; migration registry; hash-chained
  `graph_events` (append within BEGIN IMMEDIATE-serialized transaction);
  `graphEvents(sinceSeq)`; `verifyGraphChain` (seq gaps + hash mismatches).
- `src/graph/projection.ts` — **part 2/2** (this PR ships the port only; the
  SQLite adjacency projection lands with `rt-core-graph-projection`).
- `src/store/ports.ts` — `EventLog` / `GraphProjection` ports.
- `src/store/engine.ts` — `EngineCore` dual-write mediator (log first,
  projection second; projection failure → `GraphProjectionError`, recovery =
  `resyncGraph()`).

## Storage decisions (disclosed)

- better-sqlite3 over node:sqlite (experimental in node 24).
- **Kùzu deferred**: kuzu npm 0.11.3 segfaults with concurrent open databases
  and hangs closing after heavy use (measured 2026-10-30; details in PR). The
  pre-agreed fallback (SQLite adjacency behind the same `GraphProjection` port)
  ships now; the Kùzu adapter is a drop-in replacement when the binding
  stabilizes. Effects on consumers: none — the port is the contract.
- kuzu npm removed from dependencies; `GraphStore` keeps the exact API shape
  (snapshot/count/lineage/rebuild) the roadmap's graph queries need.

## impact_scope

- New package only; no existing symbols touched (GitNexus impact N/A — the
  package has no upstream callers). `detect_changes` before push reconciles
  against the declared file list in evidence/impact-scope.json.
- CI: new `rt-core-gate` job (pnpm install → tsc --noEmit → vitest run), added
  to delivery-governance.yml; actions pinned by SHA per repo convention.

## rejected_designs

- node:sqlite as the driver (experimental status; better-sqlite3 is mature).
- Keeping kuzu npm as the shipped projection (native instability measured;
  re-introduction is a port swap, not a rewrite).
- String-built method dispatch for handlers (fragile; replaced by the typed
  strategy registry).
- Hand-written per-type validators (copy-paste; replaced by EVENT_SPECS).
- Repeated native open/close per test (kuzu-specific; moot after the SQLite
  pivot — per-file shared store + rebuild isolation kept as the test shape).

## Verification anchors

- Chain tamper-evidence (mutation + row loss) — pinned.
- Replay equality: rebuild from the log alone == live projection — pinned (CI).
- Idempotency: replaying any event twice leaves the snapshot unchanged.
- Forward-referenced edges materialize on endpoint arrival.
