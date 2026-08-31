## ADDED Requirements

### Requirement: Canonical portfolio lineage is immutable and evidence-bound

The coordinator SHALL persist an immutable SearchPortfolio lineage only from
the settled SearchPortfolio and PortfolioExecution values plus exact current
capture, receipt, checkpoint, and finding ArtifactRefs for one run and
attempt.  The persisted artifact SHALL retain intent revision, subquestions,
query variants, method boundaries, outcomes, assessment, durable evidence, and
the resulting disposition; it SHALL parent every resolved input so correction
invalidation remains transitive.

#### Scenario: A captured batch is persisted
- **WHEN** a coordinator receives one portfolio execution and exact committed
  capture, successful receipt, checkpoint, and finding refs for its attempt
- **THEN** it appends one canonical lineage artifact whose parents and payload
  prove the intent-to-assessment chain without raw query text

#### Scenario: A lineage reference is stale or mismatched
- **WHEN** a supplied evidence reference is stale, foreign, missing, or does
  not match the execution's stable reference identifiers
- **THEN** the coordinator rejects the persistence without changing the ledger

### Requirement: Portfolio-backed worker finish requires canonical lineage

The canonical HostEvent ingress SHALL require a portfolio-backed work item's
`worker_finished` event to carry an exact current portfolio lineage reference.
It SHALL verify the referenced artifact belongs to the event run and attempt,
matches the dispatched portfolio id, and covers the event's durable capture,
receipt, checkpoint, and finding evidence before accepting the event.

#### Scenario: A worker claims completion without portfolio lineage
- **WHEN** a work item declares a portfolio id and its worker-finished event
  omits or forges the lineage reference
- **THEN** the coordinator rejects the event without accepting the worker
  claim

#### Scenario: A worker finishes with its persisted lineage
- **WHEN** a portfolio-backed worker-finished event references the exact
  current lineage and its required durable evidence
- **THEN** the existing HostEvent ingress accepts a non-authoritative event
  projection while the coordinator retains the validated lineage

### Requirement: Assessment next actions preserve authority boundaries

The coordinator SHALL accept an in-authority `pivot` only with a
CorrectionEvent whose strategy binding resolves to the exact strategy parent
of the canonical lineage. It SHALL invoke `apply_correction()` so the
established #153 stale-state-quarantine path contains the affected portfolio
descendants. An assessment that requires requester reopening SHALL create a
pending human-decision reopen record and SHALL NOT autonomously correct,
replan, change the requester outcome, or grant completion authority.

#### Scenario: Contradictory evidence permits autonomous pivot
- **WHEN** a persisted assessment is `pivot` inside confirmed authority
- **THEN** the coordinator applies the matching CorrectionEvent and the
resulting stale-state-quarantine contains the persisted lineage

#### Scenario: A requester-controlled outcome changes
- **WHEN** a persisted assessment requires requester reopening
- **THEN** the coordinator records a pending human-decision reopen and does
not create an autonomous correction or replan
