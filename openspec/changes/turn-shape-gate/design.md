# Design: turn-shape-gate

## Approach

The turn record (#497) is the single carrier: it gains one optional
`turn_shape` section, measured by a pure function at composition time and
flagged — never silently dropped, never a separate gate system (#493 comment).

### Measurement

`measure_turn_shape(response_text, *, decision_count, question_count,
transformation_ratio=None)` → `{length, decision_count, question_count,
transformation_ratio, verdict, violations}`. Constants are named and exported:
`MAX_TURN_LENGTH = 1000` (SKILL "keep interactive turns under 1000
characters"), `MAX_DECISION_POINTS = 1`, `MAX_QUESTIONS = 1`. The verdict is
derived: `violated` iff any dimension exceeds its cap, with each violation
named (`length>1000: 1204`). `transformation_ratio` is carried verbatim — its
measurement and semantics are #499's; the slot exists so the record shape
does not change twice.

### Schema

- `SCHEMA_VERSION` 1 → 2. Schema 2 records may carry `turn_shape`; schema 1
  records (pre-#493) remain valid with it absent — the fail-closed
  continuity gate must survive old files.
- `append(turn_shape=...)` validates the section against its key set and
  cross-checks the verdict against the recorded violations (a "compliant"
  record with violations is itself a schema error).
- Records persist regardless of verdict: the issue orders flagged-or-split,
  and the record's continuity role is independent of composition quality.

### Surfacing

`refresh_validation` (the hook refresh) reports `last_turn_shape` — the
latest record's verdict — so the next turn grounds in both the content
(mirror/gap/delta) and the composition verdict of the previous exchange.

## impact_scope

- `AlignmentTurnRecord` (additive field), `AlignmentTurnRecordStore.append`
  (additive parameter), `refresh_validation` (additive receipt key)
- new: `measure_turn_shape`, `MAX_TURN_LENGTH`, `MAX_DECISION_POINTS`,
  `MAX_QUESTIONS`
- skill-src/SKILL.template.md + regenerated packages (prose line only)
- tests/test_alignment_turn_record.py + test_lifecycle_hook_turn_record.py:
  receipt equality assertions extended with the additive key

## rejected_designs

- **Blocking the next turn on shape violations**: the issue orders
  flagged-or-split; blocking is the #497 continuity gate's job (missing/stale
  records), not composition quality. A violated record stays the grounding.
- **Separate agent_turn_shape event stream**: one turn-record, three measured
  dimensions — no second artifact (per the #493 shape note).
- **Quote-ratio or regex policing of the text**: content quality is
  prompt-layer craft (#501); the engine measures only countable shape.
- **Hard-coding the 1000 cap inside prose only**: it is a named, exported
  constant the tests pin, so the prose rule and the measurement cannot drift.
