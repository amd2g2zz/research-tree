## ADDED Requirements

### Requirement: the gate attempts baseline reconstruction from the event log before blocking

On a continuity-gate failure caused by a missing or stale record, the store
attempts one baseline reconstruction from the alignment graph's append-only
`response_recorded` event log (read-only; the graph is never written). The
recovery record is synthesized at the log's latest turn: grounded mirror from
the materialized graph state, delta from the event, `recorded_at` from the
event.

#### Scenario: deleted record file with an intact event log heals

- **WHEN** the turn-record file is deleted while the alignment event log
  holds `response_recorded` events whose turn axis is intact
- **THEN** the next `check_continuity` appends one reconstructed baseline
  record and returns `allowed` with `degraded: true` and a named recovery
  section instead of raising

#### Scenario: a single missing index with subsequent events heals

- **WHEN** the persisted records stop one turn short of the event log's
  latest turn (subsequent events present)
- **THEN** the missing baseline is reconstructed from the log and the next
  turn proceeds with the degraded marker

#### Scenario: the graph is never written by reconstruction

- **WHEN** a reconstruction succeeds or fails
- **THEN** the alignment graph database is only ever opened read-only

### Requirement: reconstruction failure stays fail-closed

A reconstruction that cannot ground a valid baseline raises today's
continuity-gate error, unchanged.

#### Scenario: empty event log blocks unchanged

- **WHEN** the continuity gate fails while the event log holds no
  `response_recorded` events
- **THEN** the original `ContinuityGateError` is raised unchanged

#### Scenario: corrupted event log blocks

- **WHEN** any `response_recorded` event row is unreadable or malformed JSON
- **THEN** the gate blocks with the original error

#### Scenario: contradictory histories block

- **WHEN** the event log's turn axis is non-monotonic, or its latest turn
  does not extend the record file (log behind the persisted index, or short
  of the next expected turn)
- **THEN** the gate blocks with the original error

#### Scenario: corrupt record file does not heal

- **WHEN** the record file violates its own schema (`invalid_turn_record`)
- **THEN** the gate blocks unchanged; no record is appended

### Requirement: reconstructed records carry an enforced marker

`reconstructed` is a schema-additive optional record field; its presence
rules are enforced by the schema so a reconstructed record can never
masquerade as an authored one.

#### Scenario: the marker persists and round-trips

- **WHEN** a reconstructed baseline record is appended and re-read
- **THEN** the parsed record reports `reconstructed` true and the persisted
  JSON carries `"reconstructed": true`

#### Scenario: the marker cannot be forged onto an authored record

- **WHEN** a record payload carries `reconstructed` with any value other
  than boolean `true`
- **THEN** the read or append raises a turn-record schema error

#### Scenario: authored payloads stay unchanged

- **WHEN** an authored record is appended
- **THEN** its persisted payload carries no `reconstructed` field

### Requirement: degraded mode is visible, never silent

A run continued on a reconstructed baseline reports the repair in the gate
verdict and the refresh receipt.

#### Scenario: the healed verdict names the repair

- **WHEN** `check_continuity` succeeds via reconstruction
- **THEN** the verdict carries `degraded: true`, a `recovery` section naming
  the healed turn and the event-log source, and the grounding carries
  `reconstructed: true`

#### Scenario: later turns stay visibly degraded

- **WHEN** a later `check_continuity` grounds on a reconstructed latest
  record
- **THEN** the verdict still reports `degraded: true` with the grounding
  marker

#### Scenario: the receipt reports reconstructed records

- **WHEN** `refresh_validation` runs over a record file holding
  reconstructed records
- **THEN** the verdict and the written receipt carry
  `reconstructed_count` and `degraded: true`; files without them keep the
  receipt shape exactly as before
