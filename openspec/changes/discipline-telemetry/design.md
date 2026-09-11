# Design: discipline-telemetry

## Approach

The hook is the never-forgetting observer; the workflow already did the
measuring. #527 persists `turn_budget_violations`
(`{dimension, limit, observed}`) in the `response_recorded` event details of
the alignment event log; #514 persists `turn_shape` verdicts (violated with
named dimensions) and #497 requires a non-empty delta in the turn-record
file. The discipline seam consumes those emitted artifacts — it never
re-measures a turn — normalizes them into a canonical violation stream, and
escalates on the stream's sliding-window rate.

### Violation stream (discipline.py)

`DisciplineViolationStore(run_root)` appends one JSONL record per violation
to `<run_root>/discipline/violations.jsonl`. A record is
`{schema, turn_index, dimension, measured, cap, source, recorded_at}` with
`dimension` drawn from `DISCIPLINE_DIMENSIONS = {questions, chars, record,
other}`: #527's `max_questions`/`max_chars` normalize to `questions`/`chars`,
#514's `length`/`question_count`/`decision_count` shape violations map to
`chars`/`questions`/`other`, and a #497 empty-delta turn record is a
`record` violation. `source` names the emitter (`agent_turn_budget`,
`turn_shape`, `turn_record`). Appends are idempotent: the dedupe key is
`(source, turn_index, dimension, measured, cap)`, so re-reading the same
events on every hook fire never double-counts, while new turns append.
Records are bounded, validated, and the file is append-only — a single
violation is data, never rewritten.

### Sliding-window rate

`sliding_window_rate(records, window=DISCIPLINE_WINDOW_TURNS, turns_observed=…)`
counts the violation records whose `turn_index` falls in the last
`DISCIPLINE_WINDOW_TURNS` turn slots ending at the most recent observed turn
(the highest stream index, extended by the caller's turn axis when known —
the hook passes the alignment event count), divided by the full window.
The fixed denominator keeps a single violation at 1/10 — data, not a
verdict — while sustained violations accumulate toward the ladder. `0.0`
for an empty stream.

### Graduated response ladder

`resolve_discipline_response(rate)` walks named thresholds, each exported as
a module constant and pinned by tests at both boundaries:
`DISCIPLINE_REMINDER_RATE = 0.2` → `discipline_reminder`,
`DISCIPLINE_RELOAD_RATE = 0.4` → `discipline_reload`,
`DISCIPLINE_BLOCK_RATE = 0.6` → `discipline_block`; below the reminder
threshold the response is `receipt_only`. The reminder and reload steps ride
#530's tail-injection channel as a structured payload: a single-line,
bounded (`DISCIPLINE_INJECTION_MAX_CHARS`), fixed-slot (`slot:
"discipline"`) entry — the channel design is #530's; this change only emits
the payload it will carry. The reload line requests the SKILL discipline
section (contract-emission/round-discipline clauses) reload.

### Block gate (fail-closed only at the top step)

`check_discipline_gate(run_root)` is the seam a next-turn gate calls:
`{"status": "blocked", "reason": "discipline_block", ...}` when the
persisted stream shows a block-level rate, `{"status": "allowed", ...}`
otherwise. Absent or unreadable telemetry allows (fail-open observation);
only the top step is fail-closed. The hook itself stays a fail-open
observer — it names the verdict on the receipt, the gate honors it.

### Hook seam (additive)

`observe()` gains one branch for PostToolUse/Stop: collect emitted
violations (alignment event log read-only via SQLite URI mode; turn-record
file via the existing optional store import), append unseen ones, and — when
the stream exists — attach a `discipline` section
(`{rate, window, violations_in_window, recent, response, [injection],
[gate]}`) to both the persisted record and the returned receipt. The import
follows the #497 pattern (relative → bare → sentinel `None`), so standalone
skill-packaged execution, a missing run, or any read/parse failure degrades
to no telemetry: no measurements, no false violations, no section. The
#503/#509/#511 prompt-signal, re-entry, and user-move logic is untouched.
