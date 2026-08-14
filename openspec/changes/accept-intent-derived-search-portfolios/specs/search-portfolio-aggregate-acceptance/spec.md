## ADDED Requirements

### Requirement: Search Portfolio parent acceptance composes verified child boundaries

The #83 parent acceptance SHALL depend on verified groups 74, 75, and 77 and
retain group 15 as its durable-acquisition supporting group. It
SHALL exercise their public planning, execution, durable-lineage, correction,
and human-reopen behavior from one current-baseline command. It MUST NOT
introduce a second portfolio persistence path, rewrite a child contract, or
accept a child receipt whose declared source revision is not reachable from the
integration baseline.

#### Scenario: Child behavior is aggregated at a current parent head
- **WHEN** group 27 is recorded as verified
- **THEN** its exact command runs the planning, execution, capture,
  worker-finish, coordinator, and lineage suites together, and its dependency
  receipts resolve to source revisions reachable from the parent baseline

#### Scenario: The planner receipt was squash-merged
- **WHEN** a group-74 receipt references a source commit outside `dev` after
  its pull request used a squash merge
- **THEN** the exact registered group-74 command is rerun at the reachable
  merge commit before group 27 consumes the receipt

### Requirement: Historical direct-query comparison is deterministic and non-executable

The parent acceptance SHALL publish one deterministic comparison fixture for a
declared normalized input. It SHALL derive rediscovery, coverage, depth, and
decision-closure deltas from bounded public observation data. The retired
direct-query side MUST be static historical data only and MUST NOT provide a
runtime reader, import path, CLI command, fallback, migration, or executable
adapter.

#### Scenario: A fixture reports improved portfolio coverage
- **WHEN** the fixture declares retired and portfolio observation sets for the
  same normalized input
- **THEN** the acceptance test recomputes every published delta and rejects a
  mismatched count, coverage ratio, depth rank, or closure result

#### Scenario: A reader attempts to revive direct-query behavior
- **WHEN** the parent comparison fixture is inspected
- **THEN** it contains no raw query or prompt material, executable legacy
  reference, or claim of live-provider causality or release approval

### Requirement: Search Portfolio governance identifies only current surfaces

The group-27 issue map and delivery matrix SHALL identify the parent acceptance
change, current SearchPortfolio/source-capture/coordinator modules, and real
public Python methods. They MUST NOT name retired `acquisition.py`, `methods.py`,
or a nonexistent `research-tree run plan-search` command. Group-27 rollback
MUST preserve current-only behavior.

#### Scenario: Delivery metadata is validated
- **WHEN** the governance registry is checked for #83
- **THEN** it maps group 27 to the parent acceptance change, retains supporting
  group 15 plus delivered groups 74, 75, and 77, and exposes no retired module
  or CLI surface
