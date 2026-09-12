## ADDED Requirements

### Requirement: the hook maintains a persistent violation stream per run

The lifecycle hook SHALL append each emitted agent-side discipline violation
to an append-only per-run JSONL stream — one record
`{turn_index, dimension, measured, cap, source}` per violation, with
`dimension` drawn from the canonical vocabulary `questions` / `chars` /
`record` / `other` — and SHALL NOT duplicate the measurement logic of the
emitters it consumes (#527 agent turn budget, #514 turn shape, #497 turn
record delta compliance). Appends SHALL be idempotent: re-observing the
same emitted violation never double-counts it.

#### Scenario: the violation stream appends and persists

- **WHEN** the hook observes an emitted violation on a run and then a later
  hook observation re-reads the same event stream
- **THEN** the stream file under the run's `discipline/` directory contains
  the violation exactly once with its turn index, dimension, measured
  value, cap, and source, and a fresh store reads the same records

#### Scenario: agent turn budget violations are counted from the event stream

- **WHEN** a recorded turn exceeds the emitted agent turn budget and the
  hook observes the run afterwards
- **THEN** the stream carries the #527 violation normalized to the
  canonical dimension with the measured value and cap, sourced
  `agent_turn_budget`, and the receipt's `discipline` section reports the
  sliding-window rate and recent violations

### Requirement: the violation rate is a sliding-window query over the stream

The discipline module SHALL expose a sliding-window violation rate over the
last `DISCIPLINE_WINDOW_TURNS` turn slots (a named exported constant),
computed from the persisted records with a fixed denominator so a single
violation stays data and not a verdict, and SHALL return `0.0` for an empty
stream.

#### Scenario: the sliding window counts recent turns only

- **WHEN** violations accumulate in the most recent window turns and older
  turns slide past the window as the run's turn axis advances
- **THEN** the rate counts only the records inside the window and the
  empty-stream rate is `0.0`

### Requirement: the response ladder escalates through named thresholds

The discipline module SHALL resolve the observed rate to exactly one
response — `receipt_only` below `DISCIPLINE_REMINDER_RATE`,
`discipline_reminder` at/above it, `discipline_reload` at/above
`DISCIPLINE_RELOAD_RATE`, and `discipline_block` at/above
`DISCIPLINE_BLOCK_RATE` — with every threshold an exported named constant.
The reminder and reload steps SHALL carry a structured injection payload
(single line, bounded, fixed slot) for the hook's tail-injection channel
owned by #530; the reload payload requests the SKILL discipline section
reload.

#### Scenario: ladder thresholds trigger the right response marker

- **WHEN** the violation rate sits just below, between, and above each
  named threshold
- **THEN** the resolved responses are `receipt_only`,
  `discipline_reminder`, `discipline_reload`, and `discipline_block`
  respectively, the reminder and reload steps carry the bounded single-line
  injection entry with the `discipline` slot, and the block step carries a
  blocked gate verdict instead of an injection

### Requirement: telemetry is fail-open, fail-closed only at the block step

Absence of telemetry SHALL produce no measurements and no false violations:
a run without emitted violations or a hook without the discipline module
yields no `discipline` receipt section, no stream file, and an allowed gate.
Only the top ladder step is fail-closed: a next-turn gate check SHALL report
`blocked` when the persisted stream shows a block-level rate and `allowed`
otherwise (including an absent or unreadable stream).

#### Scenario: fail-open without records

- **WHEN** the hook observes a run that has emitted no violations (no turn
  records, no alignment event log, no stream)
- **THEN** no violation records are created, the receipt carries no
  `discipline` section, and the gate check allows

#### Scenario: the block step is honored by a gate check

- **WHEN** the persisted stream's sliding-window rate reaches
  `DISCIPLINE_BLOCK_RATE` and a next-turn gate check runs
- **THEN** the check reports `blocked` with reason `discipline_block`,
  while a stream below the threshold or an absent stream reports `allowed`
