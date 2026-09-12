## 1. Tests (RED first)

- [x] 1.1 RED: violation stream appends + persists; re-append is idempotent
- [x] 1.2 RED: sliding-window rate counts the last N turns, `0.0` when empty
- [x] 1.3 RED: ladder thresholds trigger the right response marker at each
      step; reminder/reload carry the bounded single-line injection entry
- [x] 1.4 RED: fail-open without records — no stream file, no receipt
      section, gate allows
- [x] 1.5 RED: #527 violations counted from the alignment event stream;
      #514 turn-shape verdicts and empty deltas counted from the record file
- [x] 1.6 RED: block step honored by the gate check (blocked at/above
      `DISCIPLINE_BLOCK_RATE`, allowed below and when absent)

## 2. Implementation

- [x] 2.1 discipline.py: violation stream store (append-only, idempotent),
      sliding-window rate query, response ladder with named thresholds,
      injection payload builder, gate check
- [x] 2.2 lifecycle_hook.py additive seam: optional import chain, event
      stream collection (alignment event log + turn-record file), PostToolUse/
      Stop branch, `discipline` receipt section
- [x] 2.3 __init__.py exports for the discipline module

## 3. Gate

- [x] 3.1 full suite + ruff + validate + governance + parity → PR
      feat/issue-525-discipline-telemetry → dev (do not merge)
