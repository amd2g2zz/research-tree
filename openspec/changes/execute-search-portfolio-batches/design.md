## Design

`MethodExecutionOutcome` is the typed adapter boundary for one selected
method/provider pair. It carries only stable query references, immutable
capture/receipt/checkpoint references when available, a finite acquisition
disposition, and bounded assessment metrics. Raw query text and private prompt
material are not accepted.

`PortfolioBatch` groups outcomes for one dependency-ready wave. The pure
`SearchPortfolioExecutor` first validates every outcome against the existing
`MethodRegistry`, then exposes unused available registrations as fallback
`MethodSelection` values with the `fallback` selection reason. It never writes a
ledger or dispatches a worker. If the registry has fewer than two independent
method/provider boundaries, the returned execution projection marks capability
degraded and the assessment reports `single-boundary` provenance.

`assess_acquisition_batch` folds each wave into `BatchCoverageAssessment`.
Failures choose `switch` when a fallback exists, `rewrite` for an exhausted
no-result, and `blocked` only when no typed alternative remains. Shallow or
partial evidence chooses `deepen`; unresolved implementation/oracle risk
chooses `experiment`; contradictions require a successor strategy and choose
`pivot`; a complete low-risk batch chooses `stop`. These values are bounded
policy inputs and do not grant lifecycle or completion authority.

The implementation intentionally keeps all values immutable and serializable so
#187 can bind them to canonical source-capture and coordinator lineage without
reintroducing a second persistence plane.
