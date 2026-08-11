# Add Oracle Slot Closure

## Why

Worker-authored validation text cannot prove that validation ran against the
current evidence or that an independent evaluator reviewed it. Issue #56
introduces immutable, evaluator-owned Oracle artifacts and closure assessments.

## What Changes

- Add revision-bound `OracleSpec`, `OracleAttempt`, and `OracleRun` artifacts.
- Add evaluator-owned `SlotClosureAssessment` artifacts and closure tokens.
- Preserve legacy Finding Pack validation text as non-authoritative history.
- Emit typed successors for failed or inconclusive validation.

## Non-Goals

- No coordinator lifecycle, host adapter, command execution, or delivery work.
- No migration that rewrites existing Finding Packs.
