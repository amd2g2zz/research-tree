## ADDED Requirements

### Requirement: Portfolio plans retain exact canonical intent lineage

The runtime SHALL persist a strict portfolio only when the intent model,
working brief, strategy, decision map, and method registry are current
artifacts in the same run. The portfolio SHALL retain bounded subquestion,
query-reference, method-selection, and parent-reference fields.

#### Scenario: A plan is persisted
- **WHEN** a typed intent-derived plan is submitted with current root artifacts
- **THEN** one active `search-portfolio` artifact records the exact five-root
  lineage and exposes every subquestion/query/method boundary without raw query
  text

#### Scenario: A root revision is stale
- **WHEN** a caller submits an older intent, strategy, target, or registry
  revision
- **THEN** the service rejects the plan without appending a portfolio

### Requirement: Every execution batch has source and finding lineage

Each recorded method outcome and batch SHALL be parent-linked to its portfolio
and to any committed capture, succeeded receipt, checkpoint, and finding pack
references it claims. A captured assessment SHALL require at least one current
capture and finding lineage.

#### Scenario: A complete batch is recorded
- **WHEN** outcomes reference current capture/receipt/checkpoint artifacts and
  a finding pack
- **THEN** the ledger contains outcome, batch, assessment, and decision artifacts
  whose parent graph reaches the exact portfolio and source evidence

#### Scenario: A stale capture is supplied
- **WHEN** a capture revision is superseded or belongs to another attempt
- **THEN** the assessment is rejected before any assessment or decision row is
  appended

### Requirement: Acquisition dispatch and worker finish are canonical

An acquisition dispatch SHALL require a current active portfolio, selected query
variant, accepted method boundary, and current strategy/decision-map binding.
The lease SHALL retain the portfolio reference. An acquisition
`worker_finished` HostEvent SHALL additionally prove current capture, receipt,
checkpoint, finding, and matching recorded assessment references.

#### Scenario: An acquisition omits its portfolio
- **WHEN** a worker item is marked `acquisition` without `search_portfolio_ref`
- **THEN** coordinator dispatch rejects it with `search_portfolio_required`

#### Scenario: A worker finishes with an unrecorded assessment
- **WHEN** the HostEvent contains ordinary outcome text or an assessment from
  another portfolio/attempt
- **THEN** canonical ingestion rejects it without writing the event projection

#### Scenario: A valid worker finish is replayed
- **WHEN** the same fully bound HostEvent is submitted after a restart
- **THEN** the original event is returned idempotently and no duplicate event
  or projection is appended

### Requirement: Replan and authority decisions fail closed

The coordinator SHALL persist a typed `portfolio-decision`. A pivot SHALL carry
an exact successor strategy whose parent is the superseded strategy. A
requester-controlled authority/safety/outcome change SHALL remain blocked and
require an explicit human reopen.

#### Scenario: Contradictory evidence pivots inside authority
- **WHEN** a batch assessment is `pivot` and a parent-linked successor strategy
  is provided
- **THEN** the decision records the pivot, successor reference, and reason while
  preserving the superseded strategy

#### Scenario: Evidence changes a human-only outcome
- **WHEN** the assessment is `blocked` with `requires_requester_reopen`
- **THEN** the decision status is `awaiting-human-reopen` and no autonomous
  successor authority is created

### Requirement: Corrections invalidate the complete portfolio graph

The runtime MUST ensure portfolio plans, batches, outcomes, assessments,
decisions, leases, host-event projections, and future descendants use ordinary
canonical parent edges so the transitive correction closure quarantines them
together.

#### Scenario: A requester correction supersedes the strategy
- **WHEN** a correction affects an authority ancestor of an active portfolio
- **THEN** the portfolio graph is quarantined, stale dispatch/assessment/event
  operations fail closed, and immutable evidence history remains addressable
