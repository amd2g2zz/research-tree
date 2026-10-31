# design — parallel-dag

ParallelStage rows persist in the ledger (migration v4); the tick() pass
computes the ready set (deps closed), cuts to maxConcurrency, and marks
in_progress. failStage increments retries; retries ≥ max → parked. Isolated
output paths prevent file conflicts between parallel stages.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Greedy cut without dependency checks (#531's failure mode — pinned).
- Shared output paths (file conflicts).
- Unbounded retry (parks after max).
