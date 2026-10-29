# rt-core-event-log

## Why

**Part 1/2 of the rt-core dual-store delivery** (split for the CI hard review limit; part 2 ships the graph projection behind the same port and closes #546).

Issue #546 (T0 row 1), rt-core TypeScript implementation. **Language ruling
2026-10-30 (user): the v2 engine is full TypeScript** — the merged Python
implementation (PR #581) is superseded; its schema, event vocabulary, hash-chain
design and acceptance mapping are the spec for this change (issue #546 reopened).

Two stores, one truth:

- **SQLite stays the sole authority**: rt-core's own database carries the
  append-only, hash-chained `graph_events` table (schema v1 — parity with the
  Python implementation's v8): dense global `seq`,
  `content_hash = sha256(prev_hash ‖ canonical_record)`, tamper-evident via
  `verifyGraphChain()`. Driver: better-sqlite3 (node:sqlite is experimental).
- **The object graph is a replayable projection** behind the `GraphProjection`
  port. Storage note (disclosed): the roadmap names Kùzu, but the kuzu npm
  0.11.x binding segfaults with concurrent open databases and hangs on close
  after heavy use (measured 2026-10-30) — per the pre-agreed risk path the
  projection ships on **SQLite adjacency tables behind the same port**; the
  Kùzu adapter returns when the binding is stable. Replay test: rebuild from
  the log alone reproduces the identical snapshot.

## Design patterns (per user feedback: 合理的设计模式)

- **Ports & adapters**: `EventLog` / `GraphProjection` interfaces; `LedgerStore`
  and `GraphStore` are adapters; `EngineCore` (dual-write mediator, fail-closed)
  depends on the ports only — fakes and future implementations (Kùzu adapter,
  queue-backed log) plug in without touching the mediator.
- **Table-driven schemas (specification pattern)**: one declarative
  `EVENT_SPECS` table + a generic validation engine; compiler-enforced coverage
  of all 11 event types; no per-type validator copy-paste.
- **Strategy registry**: projection handlers are an explicit
  `Record<GraphEventType, ProjectionHandler>` — no string-built method dispatch.
- **Versioned migration registry**: `MIGRATIONS` ordered by version; #547 adds
  v2 (six ledger tables) without touching v1.
- **Pending-edge work queue**: edge events whose endpoints are not yet upserted
  are keyed per endpoint and materialized when the endpoint arrives
  (forward references are normal in the v2 model).

## impact_scope

- new package `rt-core/` (no existing symbols — GitNexus impact N/A; the graph
  is additive): `src/events/{canonical,schema,vocabulary}.ts`,
  `src/graph/projection.ts`, `src/store/{ledger,engine,ports}.ts`
- `.gitignore` (node_modules), `.github/workflows/delivery-governance.yml`
  (new rt-core job: pnpm + tsc + vitest)
- tests: `rt-core/test/{events,graph,graph.replay,engine,engine.replay}.test.ts`
- openspec change files; `pyproject.toml`/`uv.lock` untouched (legacy Python frozen)
