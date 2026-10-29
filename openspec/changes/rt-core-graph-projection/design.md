# design — rt-core-graph-projection

## Layout

- Node tables `nodes_claim/stage/evidence/artifact/version` (id PK, scalar
  columns; booleans stored as 0/1 — better-sqlite3 binds no booleans).
- Edge table `edges(rel, src, dst)` with rel discriminator (KILL_EDGE /
  STAGE_DEPENDS_ON / CONTAINS / EVIDENCE_FOR / ARTIFACT_FOR / FORKED_FROM).
- Fork semantics: edges run **child → parent**; `forkParent` reads `dst` for a
  `src`, `forkChildren` reads `src` for a `dst`.
- Pending edges: in-memory Map keyed `${table}:${id}` per missing endpoint;
  `upsertNode` materializes its bucket; idempotent (dedup + INSERT OR IGNORE).
- Handler registry: `Record<GraphEventType, ProjectionHandler>` — the compiler
  enforces coverage of the 11-type vocabulary (strategy pattern, no string
  dispatch).

## impact_scope

- new `rt-core/src/graph/projection.ts`; tests `graph`, `graph.replay`,
  `engine.replay` — GitNexus impact N/A (no upstream callers; the port shipped
  unimplemented in part 1).

## rejected_designs

- kuzu npm as shipped storage (native instability measured; the port makes the
  Kùzu adapter a drop-in when the binding matures — no consumer changes).
- One edge table per relation (six near-identical tables; the discriminator
  column keeps lineage queries one-liners).
- Dropping forward-referenced edges (real v2 flows reference claims before
  their upsert; the pending queue preserves them).
