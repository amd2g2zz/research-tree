## ADDED Requirements

### Requirement: the graph event log is append-only and hash-chained

The workspace-global `graph_events` table assigns a dense, monotonically
increasing `seq`; each record's `prev_hash` equals the previous record's
`content_hash` and its `content_hash` covers the full record payload. Genesis
`prev_hash` is 64 zeros.

#### Scenario: appends are dense and chained
- **WHEN** three graph events are appended
- **THEN** their seqs are 1, 2, 3 and each record's `prev_hash` equals the prior record's `content_hash`

#### Scenario: unknown event types are rejected
- **WHEN** `appendGraphEvent` is called with an event type outside the vocabulary
- **THEN** the append fails with `GraphEventError` and the log is unchanged

#### Scenario: payload schema is enforced per type
- **WHEN** a `claim.upsert` event carries a `posterior` outside [0, 1] or an unknown `weight`
- **THEN** the append fails with `GraphEventError`

### Requirement: the chain is tamper-evident

`verifyGraphChain` detects both in-place payload mutation and deleted rows.

#### Scenario: mutated payload is detected
- **WHEN** a stored `payload_json` row is modified in place and `verifyGraphChain` runs
- **THEN** it throws `LedgerIntegrityError` naming the seq

#### Scenario: deleted row is detected
- **WHEN** a middle row is deleted and `verifyGraphChain` runs
- **THEN** it throws `LedgerIntegrityError` for the seq gap
