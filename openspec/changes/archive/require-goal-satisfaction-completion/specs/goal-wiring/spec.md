# Goal Wiring Specification — Goal Satisfaction Completion Gate Deltas

## ADDED Requirements

### Requirement: Completion is gated on per-oracle goal satisfaction registrations

Each success oracle of the run's confirmed StrategyProjection MUST carry exactly one
`goal_satisfaction` completion-input registration, payload `{schema:1, oracle_id, verdict ∈
{satisfied, partial, unmet, waived}, evidence_refs: [<ArtifactRef>], waiver_reason}`,
issuer `coordinator`. `satisfied`/`partial` MUST cite at least one evidence reference that
resolves to a current run ledger artifact of an admissible evidence kind (finding pack,
slot-closure assessment, goal-contribution assessment). `waived` MUST carry a non-empty
`waiver_reason`; `satisfied`/`partial`/`unmet` MUST carry `waiver_reason: null`. `unmet` is
an explicit verdict: admissible to register, but never covers an oracle.

#### Scenario: All oracles satisfied passes the gate

- **WHEN** every success oracle of the confirmed projection carries one satisfied
  registration whose evidence resolves to a current run finding pack
- **THEN** the goal_satisfaction diagnostic passes, the completion record's manifold
  records `goal_satisfaction_refs` in projection oracle order, and complete() completes
  the run unchanged otherwise.

#### Scenario: Waived without a reason is rejected at registration

- **WHEN** a `waived` verdict is registered without a `waiver_reason`
- **THEN** the registration is rejected naming `waiver_reason`
- **AND** the run ledger is unchanged.

#### Scenario: Satisfied without resolvable evidence is not coverage

- **WHEN** a satisfied registration's evidence references no longer resolve to a current
  admissible-kind run artifact (stale revision, foreign run, quarantined, or kind outside
  the admissible set)
- **THEN** the oracle is uncovered: the diagnostic fails `oracle_uncovered` naming the
  oracle, and complete() raises CompletionBlockedError.

#### Scenario: Non-waived verdict with a waiver_reason is rejected at registration

- **WHEN** a satisfied/partial/unmet verdict carries a non-null `waiver_reason`
- **THEN** the registration is rejected naming `waiver_reason`.

#### Scenario: Satisfied/partial without evidence is rejected at registration

- **WHEN** a satisfied/partial verdict carries empty `evidence_refs`
- **THEN** the registration is rejected naming `evidence_refs`.

#### Scenario: Unmet is admissible but never covers

- **WHEN** an `unmet` verdict is registered for a projection oracle
- **THEN** the registration is admissible, the gate fails `oracle_uncovered` naming the
  oracle, and complete() raises CompletionBlockedError.

### Requirement: The gate fails closed on unknown, duplicate, or uncovered goal state

The `goal_satisfaction` manifold diagnostic MUST fail closed: a run whose confirmation
record does not resolve to a confirmed projection (pre-#427 run, superseded or corrupt
confirmation) MUST NOT pass the gate. A projection oracle with more than one valid
registration MUST fail `oracle_duplicate`; one with zero registrations, an `unmet` verdict,
or evidence that no longer resolves MUST fail `oracle_uncovered` with the uncovered oracle
id list.

#### Scenario: A run without a resolvable confirmed projection fails closed

- **WHEN** `strategy_projection.latest_confirmed` returns None for a run at the completion
  boundary (pre-#427 run, superseded confirmation, or unresolvable confirmation event)
- **THEN** the diagnostic fails `goal_satisfaction_unknown`, the run MUST NOT complete,
  and complete() raises CompletionBlockedError.

#### Scenario: Duplicate per-oracle registrations fail the gate

- **WHEN** two distinct registration artifacts name the same projection oracle
- **THEN** the diagnostic fails `oracle_duplicate` naming the oracle.

#### Scenario: Missing registration is uncovered

- **WHEN** a projection oracle has no goal_satisfaction registration
- **THEN** the diagnostic fails `oracle_uncovered` listing the oracle, and
  complete() raises CompletionBlockedError.

### Requirement: why_not_complete names every uncovered oracle

`why_not_complete` MUST keep its existing output shape and, for an `oracle_uncovered` fail,
append `resolve:goal_satisfaction:<oracle_id>` per uncovered oracle to `next_actions`
alongside the generic `resolve:goal_satisfaction` obligation entry.

#### Scenario: Per-oracle resolve entries are appended

- **WHEN** the run has two success oracles, oracle-1 satisfied (resolvable evidence) and
  oracle-2 without any registration
- **THEN** next_actions lists exactly `resolve:goal_satisfaction` and
  `resolve:goal_satisfaction:oracle-2`
- **AND** no `resolve:goal_satisfaction:oracle-1` entry exists for the covered oracle.

#### Scenario: Duplicate and unknown fails do not name oracles in next_actions

- **WHEN** the diagnostic fails `oracle_duplicate` or `goal_satisfaction_unknown`
- **THEN** next_actions carries the generic `resolve:goal_satisfaction` entry only.
