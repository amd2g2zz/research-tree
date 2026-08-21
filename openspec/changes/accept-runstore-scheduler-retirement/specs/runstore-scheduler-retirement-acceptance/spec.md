## ADDED Requirements

### Requirement: Parent acceptance consumes reachable scheduler-removal receipts

The #175 parent acceptance SHALL depend on verified groups 62 and 76. Before
the parent receipt is accepted, each child command receipt's source revision
MUST be reachable from the parent baseline.

#### Scenario: Parent verifies child evidence

- **WHEN** the parent acceptance test inspects groups 62 and 76
- **THEN** both records are verified and each source revision is an ancestor of
  the parent `HEAD`

### Requirement: Parent acceptance preserves the current-only retirement

The #175 parent evidence SHALL keep `src/research_tree/scheduler.py` and
`docs/specs/RT-010.md` absent. It MUST NOT introduce a scheduler replacement,
compatibility path, migration, dual write, or user-data operation.

#### Scenario: Parent verifies completed absence

- **WHEN** the parent acceptance command runs after both child merges
- **THEN** the child structural absence suite and the parent ownership test
  pass without recreating the retired module or contract
