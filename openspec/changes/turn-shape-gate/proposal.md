# Proposal: turn-shape-gate

## Why

issue #493 (confirmed): the one-decision-per-turn, short-round discipline is
SKILL prose only — nothing measures response shape, so the agent dumps
single long-form turns regardless of whether the user can absorb them. Per
the 2026-09-03 shape note under the #501 contract: the turn record gains
composition traces — length, decision count, and the #499 transformation
ratio slot — verified mechanically; what a compliant turn says stays
prompt-layer craft. One turn-record, three measured dimensions, checked
against the emitted contract — no separate gate system.

## What Changes

1. `measure_turn_shape()` (alignment_turn_record.py): pure measurement of one
   composed turn — length, decision_count, question_count, plus the #499
   `transformation_ratio` placeholder slot — returning a named verdict
   (compliant/violated with named dimensions) against three named constants:
   `MAX_TURN_LENGTH = 1000` (the SKILL round rule), `MAX_DECISION_POINTS = 1`,
   `MAX_QUESTIONS = 1`.
2. Turn-record schema 2: records carry an optional `turn_shape` section
   (schema 1 records stay readable — fail-closed continuity survives). The
   record persists regardless of verdict — flag-not-block, per the issue's
   "over-threshold turns get flagged or split".
3. `refresh_validation` receipt carries `last_turn_shape` so the next turn
   (and the operator) sees the previous turn's composition verdict.
4. Skill prose: the short-round rule now names the measured dimensions and
   the record-or-flag consequence (canonical sources + regenerated packages).

## Impact

- src/research_tree/alignment_turn_record.py: additive schema 2 + one pure
  function; no behavior change for records without turn_shape.
- tests: new scenarios; #497 receipt assertions extended with the additive
  `last_turn_shape` key.
- No canonical generation inputs touched; packages regenerated only for the
  skill prose line.
