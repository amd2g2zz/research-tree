# wire-context-ledger-production Specification Delta

## ADDED Requirements

### Requirement: Governed runs run under a declared-budget read ledger

Every governed senior-user-ux-v2 Track B run SHALL create a
`ContextReadLedger` at `<workspace>/.research-tree/runs/<run id>/context/read-ledger.json`
whose budget is declared at admission, SHALL record its evidence reads
through that ledger, and SHALL NOT pass when the declared budget is
exhausted: an exhausted budget SHALL stop the run on the ledger's resumable
unknown checkpoint with an unmet `oracle-context-discipline` verdict and a
blocked completion gate.

#### Scenario: Ledger created with the admission-declared budget

- **WHEN** a governed Track B run executes
- **THEN** the run root contains `context/read-ledger.json` whose `run_id`
  matches the run, whose budget equals the declared budget, and whose reads
  include the run's cell-receipt reads recorded after sealing

#### Scenario: Budget exhaustion is a resumable unknown, never a pass

- **WHEN** recorded reads exceed the budget declared at admission
- **THEN** the ledger status is `budget_exceeded` with a checkpoint marked
  `resumable` and `execution_state: unknown`, the context-discipline oracle
  registers `unmet`, the completion gate blocks, and the receipt status is
  `failed`

### Requirement: Ledger receipts are completion-gate-visible evidence

The governed run SHALL wrap the ledger receipt into a registered finding
pack (`pack-context-evidence`) whose evidence standards and claim groundings
carry the `es-budget-receipt` token, and the `oracle-context-discipline`
goal-satisfaction registration SHALL cite that pack so the completion gate
can see the budget receipt.

#### Scenario: Context pack grounds the budget receipt

- **WHEN** the governed run registers its goal satisfactions
- **THEN** `pack-context-evidence` carries `es-budget-receipt` in
  `evidence_standard_ids` and in its claim groundings, the ledger status,
  wave, read counts, token totals, declared budget, and checkpoint are
  encoded in the pack tokens, and the context-discipline registration cites
  the pack with a `satisfied` verdict when the ledger stayed active

### Requirement: Runs are admitted against the registered baseline

Run start SHALL cross-check the run's declared baseline (run name and the
three role scores) against the digest-sealed registry
`evaluation/baselines/senior-user-ux-v2-baseline.json` before any run state
is created. A mismatch, or a missing, unreadable, invalid, or digest-broken
registry, SHALL fail closed with a canonical admission reason; a match SHALL
persist a `context-admission-record` artifact carrying the cross-check and
the declared context budget.

#### Scenario: Declared baseline matches the registry

- **WHEN** the declared run name equals the registered baseline run name and
  all three role scores equal the registered values
- **THEN** the run proceeds and persists one `context-admission-record`
  artifact whose payload carries the admitted cross-check, the registry
  digest, and the declared context budget

#### Scenario: Declared baseline diverges from the registry

- **WHEN** the declared run name differs from the registry, or any declared
  role score differs from the registered value
- **THEN** the run is blocked before any run state exists with the canonical
  reason `baseline-run-name-mismatch` or
  `baseline-role-score-mismatch:<role>`

#### Scenario: Registry is missing or digest-broken

- **WHEN** the registry file is absent, unreadable, invalid, or its
  `content_digest` does not seal the `baseline` payload
- **THEN** the run is blocked with `baseline-registry-missing`,
  `baseline-registry-unreadable`, `baseline-registry-invalid`, or
  `baseline-registry-digest-mismatch`
