# Design: Oracle Slot Closure

`OracleService` persists typed artifacts through the existing SQLite-backed
`RunLedger`. Every artifact carries exact immutable parent references. The
service validates the lineage before each append, so a mismatched or stale
specification, attempt, input, result, or round cannot become evidence.

`SlotClosureAssessor` is a separate pure evaluator facade over the same ledger.
Only its configured core evaluator identity can issue an assessment. A passed
assessment requires an applicable passed OracleRun, explicit counterevidence
disposition, no active contradiction, independent provenance groups, fallback,
and reversal condition. It returns a token derived from the assessment content;
failed or inconclusive assessments have no token and include typed successors.

The assessor never mutates Decision Ledger or lifecycle state. It records an
append-only assessment and the future coordinator (#57) remains the only owner
of run completion.
