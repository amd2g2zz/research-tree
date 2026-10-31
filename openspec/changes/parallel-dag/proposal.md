# parallel-dag

## Why

Issue #565 (T2 row 3, docs 02 §递归阶段化): heterogeneous parallel DAG — dependency-aware ready-set dispatch (≤4 concurrency), task-level retry, stage-level park, isolated output paths, orphan threads park without blocking the critical path. The mechanically testable inversion of the #531 greedy-cut failure mode.

## What changes

- `scheduler/parallel_dag.ts`: ParallelDagScheduler — persisted stage table (migration v4), dependency-aware ready-set dispatch (open dependency never dispatches; closing admits in the same pass), ≤4 concurrency cap, task-level retry, park on retries exhaust, isolated output paths per stage, orphan park without blocking critical.
- The ready-set cut delegates to the #550 scheduler semantics; this module adds persistence + retry/park state machine + isolated outputs.

## impact_scope

- `rt-core/src/scheduler/parallel_dag.ts` (new), `rt-core/src/store/ledger.ts` (migration v4)
- tests: `rt-core/test/parallel_dag.test.ts`
