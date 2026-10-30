## ADDED Requirements

### Requirement: the claim ledger round-trips through the engine API

A claim's `posterior`, `verify_tier` and `kill_edges` persist to the `claims`
table and project as graph events; reading the row back returns the identical
field set.

#### Scenario: claim upsert lands in row, log and projection
- **WHEN** an engine with an attached projection upserts a claim carrying two kill edges
- **THEN** the ledger row holds all fields, the log holds one `claim.upsert` and two `claim.kill_edge` records, and the claim node is queryable in the projection

#### Scenario: posterior update is a state write
- **WHEN** the same claim id is upserted with a new posterior
- **THEN** the row reflects it, `created_at` is unchanged, `updated_at` is refreshed

#### Scenario: soft delete keeps the row auditable
- **WHEN** a claim is soft-deleted with a timestamp
- **THEN** the row remains readable with `deleted_at` set (no physical delete)

### Requirement: schema-invalid ledger writes are rejected

Every surface write validates its payload; violations are named by field.

#### Scenario: enum violations are named
- **WHEN** a claim is written with an unknown `weight` or `verify_tier`
- **THEN** the write raises `LedgerIntegrityError` naming the field

#### Scenario: kill edges cannot be self-referential or malformed
- **WHEN** kill_edges contains the claim's own id, duplicates, or a non-list value
- **THEN** the write is rejected naming `kill_edges`

### Requirement: the five satellite tables provide validated CRUD

`sources`, `hypotheses`, `directions`, `experiments`, `decompositions` each
provide upsert/get/list with closed vocabularies and range checks.

#### Scenario: satellite round-trip
- **WHEN** one record is upserted and read back per satellite table
- **THEN** every declared field round-trips identically

#### Scenario: satellite vocabulary is closed
- **WHEN** a hypothesis is written with an unknown status
- **THEN** the write is rejected naming `status`

### Requirement: schema version advances additively

Schema v2 adds the six tables without altering v1 tables.

#### Scenario: v2 pin
- **WHEN** a ledger initializes on a fresh workspace
- **THEN** the migration registry records versions 1 and 2
