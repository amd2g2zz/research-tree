
Changes: 22 files, 39 symbols
Affected processes: 11
Risk level: high

Changed symbols:
  Class ParallelDagScheduler → rt-core/src/scheduler/parallel_dag.ts
  Method completeStage → rt-core/src/scheduler/parallel_dag.ts
  Method failStage → rt-core/src/scheduler/parallel_dag.ts
  Method stageStatus → rt-core/src/scheduler/parallel_dag.ts
  Interface Migration → rt-core/src/store/ledger.ts
  Const MIGRATIONS → rt-core/src/store/ledger.ts
  Function chainHash → rt-core/src/store/ledger.ts
  Class LedgerStore → rt-core/src/store/ledger.ts
  Property databasePath → rt-core/src/store/ledger.ts
  Property database → rt-core/src/store/ledger.ts
  Method constructor → rt-core/src/store/ledger.ts
  Method appendGraphEvent → rt-core/src/store/ledger.ts
  Function append → rt-core/src/store/ledger.ts
  Interface WorkerDeps → webui-server/src/research_worker.ts
  Function buildSynthPrompt → webui-server/src/research_worker.ts
... and 24 more

Affected execution flows:
  • UpdateGain → Grams (3 steps) — changed: updateGain
  • Harvest → Connect (6 steps) — changed: appendGraphEvent, append
  • Dispatch → ParseAttachments (6 steps) — changed: dispatch
  • Dispatch → ProjectHomeError (4 steps) — changed: dispatch
  • Harvest → GraphEventError (8 steps) — changed: appendGraphEvent
  • Harvest → IsMapping (7 steps) — changed: appendGraphEvent
  • Append → CanonicalJson (4 steps) — changed: append, chainHash
  • Harvest → NodeKey (6 steps) — changed: appendGraphEvent
  • ContinueResearch → GraphEventError (5 steps) — changed: appendGraphEvent
  • ContinueResearch → IsMapping (6 steps) — changed: appendGraphEvent
... and 1 more
