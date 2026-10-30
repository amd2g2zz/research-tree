# design — stage-scheduler

Pure state-model functions — deterministic, no I/O, no clock dependency
(12h cap takes elapsedMs/capMs from the caller). The #551 state machine wires
this to the ledger and the graph projection.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Selection-value greedy cut without dependency checks (#531's failure mode —
  the ready-set cut IS the fix, pinned by tests).
- Deleting stale claims on refutation (append-only reopen, 翻案靠重开).
- Hard-coding the 12h cap inside the scheduler (caller supplies it — the
  budget is a product invariant surfaced in config).
- Full EVSI implementation at T0 (placeholder scorer with the A3 signature;
  #557 drops in).
