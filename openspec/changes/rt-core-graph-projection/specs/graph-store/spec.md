## ADDED Requirements

### Requirement: the object graph is a replayable projection

`GraphStore.rebuild(events)` wipes the projection and folds the event log into
an identical state; applying any event twice leaves the state unchanged.

#### Scenario: rebuild equals incremental state
- **WHEN** store A applies events incrementally and store B rebuilds from the same list
- **THEN** `snapshotState()` of both stores is equal

#### Scenario: replay from the log alone rebuilds the live graph
- **WHEN** an engine with an attached projection has appended events, and a
  fresh store rebuilds from the ledger event log alone
- **THEN** the fresh snapshot equals the attached store's snapshot

### Requirement: fork lineage is a first-class bidirectional query

`fork.edge` events materialize `FORKED_FROM` edges (child → parent); both
directions resolve in one query.

#### Scenario: child resolves its source version
- **WHEN** a fork edge links child `t2:0` to parent `t1:0`
- **THEN** `forkParent("t2:0")` returns `"t1:0"`

#### Scenario: parent resolves its descendants
- **WHEN** two fork edges point at the same parent
- **THEN** `forkChildren(parent)` returns both child ids

### Requirement: forward-referenced edges materialize when endpoints arrive

An edge event whose endpoint is not yet registered is deferred, not dropped.

#### Scenario: kill edge to a later claim materializes
- **WHEN** a `claim.kill_edge` names a claim id that is upserted afterwards
- **THEN** the KILL_EDGE edge exists once the endpoint arrives

### Requirement: the engine dual-writes and self-heals

With a projection attached, `appendGraphEvent` lands in log then projection;
projection failure is fail-closed; `resyncGraph()` rebuilds the projection from
the log alone.

#### Scenario: dual write
- **WHEN** an engine with an attached projection appends a claim event
- **THEN** the claim is queryable in the projection and the record is in the log

#### Scenario: drift is repaired by resync
- **WHEN** the attached projection is polluted with state the log does not contain
- **THEN** `resyncGraph()` restores a snapshot equal to a fresh rebuild from the log

#### Scenario: engines without a projection behave as before
- **WHEN** an engine is constructed without a projection and appends graph events
- **THEN** only the event log is written and no projection error can occur
