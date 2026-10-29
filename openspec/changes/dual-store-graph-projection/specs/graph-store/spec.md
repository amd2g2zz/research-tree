## ADDED Requirements

### Requirement: the graph event log is append-only and hash-chained

The workspace-global `graph_events` table assigns a dense, monotonically increasing
`seq`; each record's `prev_hash` equals the previous record's `content_hash` and its
`content_hash` covers the full record payload. Genesis `prev_hash` is 64 zeros.

#### Scenario: appends are dense and chained
- **WHEN** three graph events are appended
- **THEN** their seqs are 1, 2, 3 and each record's `prev_hash` equals the prior record's `content_hash`

#### Scenario: unknown event types are rejected
- **WHEN** `append_graph_event` is called with an event type outside the vocabulary
- **THEN** the append fails with `GraphEventError` and the log is unchanged

#### Scenario: payload schema is enforced per type
- **WHEN** a `claim.upsert` event carries a `posterior` outside [0, 1] or an unknown `weight`
- **THEN** the append fails with `GraphEventError`

### Requirement: the chain is tamper-evident

`verify_graph_chain` detects both in-place payload mutation and deleted rows.

#### Scenario: mutated payload is detected
- **WHEN** a stored `payload_json` row is modified in place and `verify_graph_chain` runs
- **THEN** it raises `LedgerIntegrityError` naming the seq

#### Scenario: deleted row is detected
- **WHEN** a middle row is deleted and `verify_graph_chain` runs
- **THEN** it raises `LedgerIntegrityError` for the seq gap

### Requirement: the object graph is a replayable projection

`GraphStore.rebuild(events)` wipes the store and folds the event log into an identical
state; applying any event twice leaves the state unchanged (idempotent).

#### Scenario: rebuild equals incremental state
- **WHEN** store A applies events incrementally and store B rebuilds from the same list
- **THEN** `snapshot_state()` of both stores is equal

#### Scenario: replay from the log alone rebuilds the live graph
- **WHEN** a coordinator with an attached store has appended events, and a fresh store
  rebuilds from `ledger.graph_events()` alone
- **THEN** the fresh snapshot equals the attached store's snapshot

### Requirement: fork lineage is a first-class bidirectional query

`fork.edge` events materialize `FORKED_FROM` edges; both directions resolve in one query.

#### Scenario: child resolves its source version
- **WHEN** a fork edge links child `t2:0` to parent `t1:0`
- **THEN** `fork_parent("t2:0")` returns `"t1:0"`

#### Scenario: parent resolves its descendants
- **WHEN** two fork edges point at the same parent
- **THEN** `fork_children(parent)` returns both child ids

### Requirement: the coordinator dual-writes and self-heals

With a store attached, `append_graph_event` lands in log then projection; projection
failure is fail-closed; `resync_graph()` restores the projection from the log alone.

#### Scenario: dual write
- **WHEN** a coordinator with an attached store appends a claim event
- **THEN** the claim is queryable in the store and the record is in the ledger log

#### Scenario: drift is repaired by resync
- **WHEN** the attached store is polluted with a state that the log does not contain
- **THEN** `resync_graph()` restores a snapshot equal to a fresh rebuild from the log

#### Scenario: coordinators without a graph store behave as before
- **WHEN** a coordinator is constructed without `graph_store` and appends graph events
- **THEN** only the event log is written and no projection error can occur
