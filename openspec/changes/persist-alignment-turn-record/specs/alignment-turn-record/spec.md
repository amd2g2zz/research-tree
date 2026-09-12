## ADDED Requirements

### Requirement: every pre-handoff alignment turn persists a turn record before responding

Each pre-handoff alignment turn SHALL append exactly one alignment-turn
record to the run's alignment workspace file
(`turn-records.jsonl`) BEFORE the agent's response is considered valid.
The record SHALL carry: `mirror` (the current understanding of the brief),
`gap` (the named consequential gap), `delta` (what changed on the graph:
a non-empty summary plus the touched alignment-graph node ids),
`user_move` (the classified user response class from the
`turn_contract` seam's response classes), and, when the engine emitted
them, the `contract_terms` and `traces` using the `turn_contract` seam
schema (reused, never duplicated). Validation SHALL be presence-and-schema
only (ADR-008) — never content quality.

#### Scenario: the record file exists and grows per turn

- **WHEN** a simulated 4+ turn alignment conversation appends one record per
  turn
- **THEN** the workspace file exists, grows by exactly one JSON line per
  turn, and every persisted record round-trips mirror, gap, delta,
  user-move, and (when present) the seam-schema contract terms and traces

#### Scenario: a record carrying contract terms verifies its traces

- **WHEN** a turn record is appended with `contract_terms` whose
  `required_traces` include a trace the turn did not leave
- **THEN** the append fails naming the exact missing term, and the file is
  unchanged

#### Scenario: the user move uses the seam response classes

- **WHEN** a record declares a `user_move` outside the `turn_contract`
  response classes
- **THEN** the append fails with a named schema error

### Requirement: the continuity gate fails closed before the next alignment turn

Before an alignment move is generated, the persisted record SHALL be loaded
and the move grounded in it. A missing, invalid, or stale record SHALL
BLOCK the next alignment turn (fail-closed, like checkpoint discipline):
- no record file and `next_turn > 1` blocks with `missing_turn_record`;
- a malformed record blocks with `invalid_turn_record`;
- a skipped exchange (`latest.turn_index < next_turn - 1`) blocks with
  `stale_turn_record`.
An adjacent latest record allows the turn and returns the grounding (the
latest mirror/gap/delta); a record already persisted for the current
exchange allows re-grounding (compaction/crash recovery). `append` SHALL
independently enforce the same adjacency so the file cannot grow out of
order.

#### Scenario: continuity holds across turns

- **WHEN** the gate is consulted before exchange N and the latest record is
  exchange N-1
- **THEN** the gate allows the move and returns the persisted grounding the
  move must be grounded in

#### Scenario: a deleted record blocks the next turn

- **WHEN** the record file is deleted (or orphaned by compaction) and the
  next alignment turn is attempted
- **THEN** the gate blocks with `missing_turn_record`

#### Scenario: a stale record blocks the next turn

- **WHEN** an exchange elapsed without a persisted record and the next turn
  is attempted
- **THEN** the gate blocks with `stale_turn_record`

#### Scenario: a corrupt record blocks the next turn

- **WHEN** the record file contains a line that violates the record schema
- **THEN** the gate blocks with `invalid_turn_record`

### Requirement: a turn with no persisted delta is a protocol violation

A turn that introduces no persisted delta SHALL be rejected: appending a
record whose `delta.summary` is empty or blank fails with a named protocol
violation and changes nothing on disk. The self-ask/self-answer pattern —
answering the agent's own question from stale context instead of waiting
for the user — produces no persisted delta and is therefore refused.

#### Scenario: a delta-less turn is rejected

- **WHEN** a turn record is appended with an empty or blank delta summary
- **THEN** the append fails naming the protocol violation and the record
  file is unchanged

### Requirement: lifecycle hooks refresh and validate the record file

`UserPromptSubmit` and `PostToolUse` hooks SHALL refresh and validate the
alignment turn-record file when an active run is involved (a record file
exists or the resolved run phase is `alignment`), surface the verdict
(`validated` / `missing` / `invalid`) on the hook result and the sanitized
record, and write a validation receipt next to the records. The refresh
SHALL be fail-open: it never blocks the host session, never raises into the
observe path, and leaves the existing prompt-signal, research re-entry
(#503), and binding behaviors unchanged. The refresh SHALL NOT create
workspace directories as a side effect.

#### Scenario: the hook validates the record file on prompt submit

- **WHEN** a prompt is submitted during an alignment-phase run with an
  existing record file
- **THEN** the hook result carries a `validated` verdict with the record
  count and last turn index, and a validation receipt is written next to
  the records

#### Scenario: after a compaction the refreshed file keeps continuity

- **WHEN** the record file is validated/refreshed by the hook and the next
  alignment turn consults the continuity gate
- **THEN** continuity holds (the gate allows and grounds in the record)

#### Scenario: a corrupted file fails validation and the gate blocks

- **WHEN** the hook refreshes a record file containing a schema-violating
  line
- **THEN** the verdict is `invalid` with a reason, and the continuity gate
  blocks the next alignment turn

#### Scenario: the hook stays fail-open outside the turn-record protocol

- **WHEN** a prompt or tool event arrives without an active run, or on a run
  that is not in the alignment phase and has no record file
- **THEN** no turn-record verdict is added and the observe behavior is
  byte-for-byte the pre-existing one
