# rt-core-graph-projection

## Why

**Part 2/2 of the rt-core dual-store delivery** (issue #546; part 1 = `rt-core-event-log`, PR #582). This change ships the object-graph projection behind the `GraphProjection` port and closes #546.

## What changes

- `rt-core/src/graph/projection.ts`: SQLite adjacency tables (5 node tables + a
  keyed edge table) implementing `GraphProjection` — idempotent state-carrying
  upserts, existence-checked edges, **pending-edge queue** for forward
  references, deterministic `snapshotState`, bidirectional fork lineage.
- Dual-write engine tests (projection attached) + multi-store replay tests.
- Storage disclosure: the roadmap names Kùzu; the kuzu npm 0.11.x binding
  segfaults with concurrent open databases and hangs on close (measured
  2026-10-30) — per the pre-agreed risk path the projection ships on SQLite
  behind the unchanged port; the Kùzu adapter returns when the binding
  stabilizes.

## impact_scope

- new `rt-core/src/graph/projection.ts` (no existing callers — part 1 shipped
  the port with zero implementors)
- tests: `rt-core/test/{graph,graph.replay,engine.replay}.test.ts`
- openspec change files
