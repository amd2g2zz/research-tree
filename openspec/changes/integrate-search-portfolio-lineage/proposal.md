## Why
The typed SearchPortfolio planner and batch executor describe a bounded research wave, but intent, query, method, capture, finding, assessment, and next-decision lineage remain an in-memory projection. A worker can therefore finish without a canonical portfolio assessment or leave a stale portfolio usable after correction.

## What Changes
- Persist method registrations and intent-derived plans through `RunLedger`, binding exact intent, working-brief, strategy, decision-map, and registry revisions.
- Persist each dependency-ready batch, method outcome, source capture, receipt, checkpoint, finding, coverage assessment, and typed stop/replan decision as parent-linked canonical artifacts.
- Require acquisition dispatches to reference a current active portfolio, selected query variant, and accepted method boundary, and include the portfolio in the attempt lease lineage.
- Require acquisition `worker_finished` HostEvents to carry committed capture, receipt, checkpoint, finding, and a current assessment whose method, provider, attempt, and portfolio bindings match the lease.
- Feed persisted assessment projections into `AdaptiveResearchPolicy` as non-authoritative continuation inputs; the coordinator remains the only writer of replan/stop decisions.
- Preserve autonomous pivots inside confirmed authority while requester-controlled authority/safety/outcome changes remain blocked pending human reopening.
- Use the existing transitive correction closure so portfolio, batch, assessment, decision, lease, event, and projection descendants become stale together and cannot be dispatched or consumed.

## Non-Goals

- Do not change immutable SearchPortfolio, MethodRegistry, outcome, batch, or assessment semantics established by #185/#186.
- Do not add a legacy acquisition fallback, RunStore write path, or adapter revision authority.
- Do not grant worker or policy code lifecycle, closure, readiness, delivery, or completion authority.
- Do not close parent issue #83.
