# Alpha2 Compatibility Matrix

| Surface | Alpha1 reader | Alpha2 writer | Legacy disposition |
| --- | --- | --- | --- |
| round/RunStore | read and import | no new writes | imported, then read-only |
| alignment database | read and import | coordinator event/artifact writes | imported, no completion authority |
| recursive tree state | read as projection | coordinator owns Slot/run transitions | rebuildable projection |
| native checkpoint | read and reconcile | HostEvent adapter only | read-only during cutover |
| Hermes checkpoint | read and reconcile | HostEvent adapter only | read-only during cutover |
| human-brief delivery | read and classify | human-research-report only | legacy_unverified |
| validation_result.status | read as observation | OracleRun verdict only | non-authoritative |
| missing OracleAttempt | no alpha1 equivalent | persist exact spec/action execution binding before OracleRun | reject as unbound validation |
| OracleRun bare result artifact ids | read as legacy observation | emit exact artifact revision/hash refs | reject from canonical oracle ledger |
| single Slot token as run P0 closure | read as legacy observation | emit deterministic P0ClosureAggregate | reject as incomplete run closure |
| RunStore Decision Ledger entry | import exact target/finding parents and legacy option semantics | emit DecisionLedgerEntry v1 with exact Blueprint/Finding/Insight refs | legacy_unverified until refs and observation basis resolve |
| recursive convergence projection | read as non-authoritative diagnostic | emit ConvergenceRecord v1 from canonical decision/closure state | never import completion or empty-frontier status |
| package schemas | validate old package | emit package manifest v1 | host-specific compatibility aliases |

The migration implementation SHALL turn this matrix into executable checks. A
row cannot be marked supported without a fixture, command, and evidence
reference.
