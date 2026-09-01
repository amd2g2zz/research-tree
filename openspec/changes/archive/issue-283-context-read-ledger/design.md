# Design

## Ledger and source boundary

`ContextReadLedger` stores a JSON ledger below the existing project run root.
Each record contains only a path relative to the workspace, SHA-256 digest,
byte/line range, consumer, phase, disposition, wave, and numeric usage fields;
it does not persist source content. Exact digest/range matches become `cached`
when the consumer is unchanged and `replayed` otherwise.

Discovery excludes dependency, cache, generated-package, and active-run roots.
An explicit read from an active root also fails until `context-seal` stores the
current digest. A later digest change revokes that admission.

## Budget and recovery

Budgets apply to the active wave and may cap each input disposition, tool or
process output, and the duplicate-read ratio. The read that exceeds a limit is
kept as evidence, then creates a resumable checkpoint. While paused, further
reads are rejected; `context-resume` opens a new wave. The receipt has
`execution_state: unknown`, `completion_authority: none`, and no pass field in
every state.

## Evaluation projection

`evaluate_context_cost` compares two receipts solely on duplicate reduction and
digest-range coverage retention. It reports `diagnostic_only: true`, semantic
quality `not_assessed`, and completion authority `none`, so evaluation harnesses
cannot confuse a lower-cost run with a better or completed research result.

## Host packaging

Both native adapters expose `context-record`, `context-seal`,
`context-receipt`, and `context-resume`; a budget exhaustion command returns
exit code 4 after printing the durable receipt. The dependency-free ledger is
included in every generated package and Hermes' isolated executable closure.
