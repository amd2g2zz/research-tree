## 1. Tests (RED first)

- [x] 1.1 RED: open dependency ⇒ node never in select output (inverts the
      greedy cut even at top selection value)
- [x] 1.2 RED: closing the last dependency makes the dependent dispatchable
      in the same selection pass
- [x] 1.3 RED: dispatched nodes carry dependency conclusion digests in
      execution context
- [x] 1.4 RED: multi-dependency node converges only when ALL dependencies
      close
- [x] 1.5 RED: slot-level dependency blocks downstream slot roots until the
      upstream slot closes
- [x] 1.6 RED: cycle in depends_on rejected at merge/ingest time
- [x] 1.7 RED: unknown dependency rejected at ingest; legacy no-depends
      nodes behave exactly as today; ready set smaller than parallelism
      returns fewer (no backfill)

## 2. Implementation

- [x] 2.1 `NodeDependencyError` + node/slot additive `depends_on` fields
- [x] 2.2 ingest-time DAG validation (unknown / self / cyclic rejection,
      `_stable_topological_order` pattern)
- [x] 2.3 ready-set dispatch + dependency-context propagation in
      `select_research_actions`; slot-level root gating
- [x] 2.4 `__init__` export for `NodeDependencyError`

## 3. Gate

- [x] 3.1 full suite + ruff + delivery validate + openspec governance +
      skill-package parity → PR fix/issue-531-dag-driven-execution → dev
